"""Neutral flags (docs/data-contract.md §4, SPEC §6). Facts only; every flag carries its numbers.

A flag is computed only when every input field is confident; otherwise the inputs are reported as `unreadable`.
Keys are recomputed from the raw names here (not read from the DB), so a normalizer change only needs a re-flag.
"""
from __future__ import annotations

import bisect
import math
import statistics
from dataclasses import dataclass, field, fields
from datetime import date, timedelta

import logging

from . import indicators as ind
from . import structural
from . import peers
from .keys import normalize_key, turkish_lower
from .model import CONFIDENT, Money, Record
from .store import StoredRecord

CURRENCY_MISMATCH = "para birimi farklı"
PART_CODES = ("tek_teklif", "diger_teklifler_elendi", "bedel_orani", "tekrarlayan_eslesik", "idare_orani")
MIN_GROUP_N = 100                 # a usul_turu group needs >= 100 records, else the all-records rate is used
P_FLOOR = 0.001                   # no part exceeds ln(1000) = 6.9 points
BUGUN_CUTOFF = 3.0                # Bugün shows score >= 3.0 (about ln 20); the site applies it


def all_group(btype: str) -> str:
    """Per-type fallback group key, e.g. "mal/hepsi"."""
    return f"{btype}/hepsi"


def group_key(btype: str, usul: str | None) -> str | None:
    return f"{btype}/{usul}" if usul else None
RATIO_THRESHOLD_PCT = 97          # ratio >= 0.97 (ihalent's low_discount: kırım < 3%)
REPEAT_MIN_IKNS = 3
REPEAT_WINDOW_DAYS = 365          # bulletin dates in [d - 365 days, d]
IDARE_WINDOW_DAYS = 30            # idare/peer stats: tenders dated in (d - 30 days, d]
IDARE_MIN_N = 5                   # an idare-level rate needs >= 5 awards (tenders) in the window
PEER_MIN_N = 20                   # a peer group needs >= 20 awards, excluding the idare itself
IDARE_RATIO = 2                   # idare_orani: idare share >= 2x peer share
ELENEN_PEER_MIN_N = 5             # peer mean of elenen_orani needs >= 5 eligible peer awards
PAYI_MIN_AWARDS = 5               # yuklenici_payi needs >= 5 awards of the idare in the 365-day window
PAYI_WINDOW_DAYS = 365
BEDEL_PEER_MIN_N = 20             # peer median of bedel_orani needs >= 20 peer awards with a ratio

log = logging.getLogger("ihale")

_MODEL_ORDER = [f.name for f in fields(Record)]


# ------------------------------------------------------------------ Turkish suffix for "%NN'…"
_UNIT_SUFFIX = {  # last spoken word → third-person possessive suffix (as in "%97'si")
    0: "ı",   # sıfır
    1: "i",   # bir
    2: "si",  # iki
    3: "ü",   # üç
    4: "ü",   # dört
    5: "i",   # beş
    6: "sı",  # altı
    7: "si",  # yedi
    8: "i",   # sekiz
    9: "u",   # dokuz
}
_TENS_SUFFIX = {
    1: "u",   # on
    2: "si",  # yirmi
    3: "u",   # otuz
    4: "ı",   # kırk
    5: "si",  # elli
    6: "ı",   # altmış
    7: "i",   # yetmiş
    8: "i",   # seksen
    9: "ı",   # doksan
}


def possessive_suffix(n: int) -> str:
    """Suffix (i/ı/u/ü, with buffer s after a vowel) following the number n as read aloud, e.g. 97 → 'si'."""
    if n < 0:
        raise ValueError("negative")
    if n == 0:
        return _UNIT_SUFFIX[0]
    if n % 1_000_000 == 0:
        return "u"      # milyon
    if n % 1000 == 0:
        return "i"      # bin
    if n % 100 == 0:
        return "ü"      # yüz
    if n % 10:
        return _UNIT_SUFFIX[n % 10]
    return _TENS_SUFFIX[(n // 10) % 10]


TYPO_NOTE = " · Bültendeki iki rakam arasındaki fark tam bir 10'un katı; kaynakta yazım hatası olabilir."
LARGE_NOTE = " · Fark olağan dışı büyük; rakamlar bültende bu şekilde yazıyor, kaynağı kontrol edin."
LARGE_RATIO = 1.5


def source_check(ratio: float | None) -> str | None:
    """'typo' when the ratio is within +-1% of a power of ten other than 1 (10, 100 ... or 0.1, 0.01 ...);
    'large' for any other ratio > 1.5; else None."""
    if ratio is None or ratio <= 0:
        return None
    for k in range(-6, 7):
        if k and abs(ratio / 10 ** k - 1) <= 0.01 + 1e-9:
            return "typo"
    return "large" if ratio > LARGE_RATIO else None


def money_tr(kurus: int, currency: str) -> str:
    """406700 → '4.067,00 TRY' (Turkish separators)."""
    return f"{kurus // 100:,}".replace(",", ".") + f",{kurus % 100:02d} {currency}"


def percent_tr(total: int, est: int) -> str:
    """total/est as a percent floored to one decimal with a decimal comma ('100,9'); more decimals (up to 4)
    only while the figure would still read as exactly 100 although total > est."""
    for d in range(1, 5):
        v = total * 100 * 10 ** d // est
        if v != 100 * 10 ** d or d == 4:
            break
    s = str(v).rjust(d + 1, "0")
    return f"{s[:-d]},{s[-d:]}"


def percent_possessive(n: int) -> str:
    """'%97'si', '%100'ü', ..."""
    return f"%{n}'{possessive_suffix(n)}"


# ------------------------------------------------------------------ results
@dataclass
class FlagResult:
    flags: list[dict] = field(default_factory=list)
    unreadable: list = field(default_factory=list)   # field names and {"field", "reason"} objects
    kisim_n: int = 1
    score: float = 0.0
    score_raw: float = 0.0
    value_weight: float = 1.0
    score_parts: list = field(default_factory=list)
    idare_stats: dict | None = None
    indicators: dict | None = None
    structural: dict | None = None     # {"id", "text"} of the matching structural rule (§4.1.1)
    usul_group: str | None = None      # "<type>/<usul group>" used for the base rates (None = unknown)
    btype: str = ""                    # bulletin type of the record
    bedel_try: float | None = None     # this record's TRY bedel in major units (materiality weight)
    cond: set = field(default_factory=set)         # parts whose condition holds, ignoring structural exclusions
    computable: set = field(default_factory=set)   # parts whose inputs are all confident

    @property
    def part_codes(self) -> list[str]:
        return [p["code"] if isinstance(p, dict) else p for p in self.score_parts]


def _estimate(r: Record) -> tuple[str, Money] | None:
    for name in ("esas_kisim_yaklasik_maliyet", "yaklasik_maliyet"):
        if r.confident(name):
            return name, getattr(r, name)
    return None


def _dedupe_key(s: StoredRecord) -> tuple:
    r = s.record
    b = r.sozlesme_bedeli
    return (r.ikn, normalize_key(r.yuklenici), b.kurus if b else None, b.currency if b else None)


def _low_confidence_fields(r: Record) -> set[str]:
    """Fields the parser attempted that are doubtful or failed. Known-empty (None at full confidence) is not."""
    out = set()
    for name, conf in r.confidence.items():
        if name not in _MODEL_ORDER or r.confident(name):
            continue
        if getattr(r, name) is None and conf >= CONFIDENT:
            continue
        out.add(name)
    return out


@dataclass
class _Tender:
    date: date
    idare_key: str
    turu: str
    il: str | None
    sector: str
    tek: bool | None          # tek_gecerli_teklif (either flag); None = unknown
    elen: float | None = None  # elenen_orani when toplam >= 2
    usul: str | None = None    # usul_turu code; None = unknown
    ratio: float | None = None  # bedel_orani value (sum of lots / estimate), None = not computable


def _ratio(r: Record, members: list[StoredRecord]) -> float | None:
    """bedel_orani value: sum of the ikn's deduped bedels / estimate; None when not computable (same rules as the flag)."""
    est = _estimate(r)
    if est is None or est[1].kurus <= 0:
        return None
    if any(not m.record.confident("sozlesme_bedeli") or m.record.sozlesme_bedeli.currency != est[1].currency
           for m in members):
        return None
    return sum(m.record.sozlesme_bedeli.kurus for m in members) / est[1].kurus


def _tenders(stored: list[StoredRecord], groups: dict) -> dict[str, list[_Tender]]:
    """Awards (distinct ikn; a record without a confident ikn is its own award) per sector, sorted by date.

    Only awards with a confident idare and a confident gecerli_teklif enter the rates. Kısmi lots of one ikn
    are one award, so a 109-lot tender does not outvote everything else.
    """
    by_id: dict = {}
    for s in stored:
        r = s.record
        if not r.confident("idare"):
            continue
        ik = normalize_key(r.idare)
        if not ik:
            continue
        tid = (r.bulletin_type, r.ikn) if r.confident("ikn") else ("rec", s.id)
        counts_ok = r.confident("gecerli_teklif") and r.confident("toplam_teklif")
        tek = (r.gecerli_teklif == 1) if counts_ok else None
        elen = ind.elenen_orani(r.toplam_teklif, r.gecerli_teklif) if counts_ok else None
        usul = ind.usul_group(r.idare, ind.usul_turu(r.ihale_usulu) if r.confident("ihale_usulu") else None)
        ratio = _ratio(r, list(groups[r.ikn].values()) if r.confident("ikn") else [s])
        t = by_id.get(tid)
        if t is None:
            by_id[tid] = _Tender(r.bulletin_date, ik, peers.idare_turu(r.idare), peers.il_of(r.idare),
                                 r.bulletin_type, tek, elen, usul, ratio)
        else:
            t.date = min(t.date, r.bulletin_date)
            if t.ratio is None:
                t.ratio = ratio
            if t.usul is None:
                t.usul = usul
            if t.tek is None:
                t.tek, t.elen = tek, elen
    out: dict[str, list[_Tender]] = {}
    for t in by_id.values():
        if t.tek is not None or t.ratio is not None:
            out.setdefault(t.sector, []).append(t)
    for v in out.values():
        v.sort(key=lambda t: t.date)
    return out


class _Window:
    """Accumulators [awards, tek awards, eligible awards for elenen, sum of elenen] per scope, one (sector, date)."""

    def __init__(self, tenders: list[_Tender], d: date, usul: str | None = None, days: int = IDARE_WINDOW_DAYS):
        """`usul` restricts the window to awards of that usul_turu (like with like)."""
        self.days = days
        dates = [t.date for t in tenders]
        lo = bisect.bisect_right(dates, d - timedelta(days=days))
        hi = bisect.bisect_right(dates, d)
        self.idare: dict[str, list] = {}
        self.turu_il: dict[tuple, list] = {}
        self.turu: dict[str, list] = {}
        self.all = [0, 0, 0, 0.0]
        # bedel_orani values per scope, split by idare key so the own idare can be left out of its peers
        self.rat: dict[tuple, dict[str, list[float]]] = {}
        self._median_cache: dict = {}
        for t in tenders[lo:hi]:
            if usul is not None and t.usul != usul:
                continue
            if t.ratio is not None:
                for scope in (("all",), ("turu", t.turu), ("turu_il", t.turu, t.il)):
                    self.rat.setdefault(scope, {}).setdefault(t.idare_key, []).append(t.ratio)
            if t.tek is None:
                continue
            for acc in (self.idare.setdefault(t.idare_key, [0, 0, 0, 0.0]), self.all,
                        self.turu.setdefault(t.turu, [0, 0, 0, 0.0]),
                        self.turu_il.setdefault((t.turu, t.il), [0, 0, 0, 0.0])):
                acc[0] += 1
                acc[1] += 1 if t.tek else 0
                if t.elen is not None:
                    acc[2] += 1
                    acc[3] += t.elen

    def peer_ratio_median(self, ik: str, turu: str, il: str | None) -> tuple[float | None, int]:
        """(median bedel_orani, n) of the peer chain, own idare excluded; first scope with n >= 20."""
        key = (ik, turu, il)
        if key not in self._median_cache:
            result: tuple = (None, 0)
            scopes = ([("turu_il", turu, il)] if il else []) + [("turu", turu), ("all",)]
            for sc in scopes:
                vals = [v for k, lst in self.rat.get(sc, {}).items() if k != ik for v in lst]
                if len(vals) >= BEDEL_PEER_MIN_N:
                    result = (round(statistics.median(vals), 6), len(vals))
                    break
            self._median_cache[key] = result
        return self._median_cache[key]


def _candidates(win: _Window, turu: str, il: str | None) -> list[tuple[str, list]]:
    out = []
    if il:
        out.append(("turu_il", win.turu_il.get((turu, il), [0, 0, 0, 0.0])))
    out.append(("turu", win.turu.get(turu, [0, 0, 0, 0.0])))
    out.append(("sector", win.all))
    return out


def _lc(label: str | None) -> str | None:
    """Lower-case the first letter (Turkish): 'Açık' -> 'açık'; '4734/3-g (DMO)' stays."""
    return label if not label else turkish_lower(label[0]) + label[1:]


def idare_stats(win: _Window, idare_name: str, sector: str, usul: str) -> tuple[dict, bool]:
    """(stats for export, idare_orani fires), within one usul_turu: `win` holds only awards of that usul."""
    ik = normalize_key(idare_name)
    turu, il = peers.idare_turu(idare_name), peers.il_of(idare_name)
    own = win.idare.get(ik, [0, 0, 0, 0.0])
    own_n, own_tek = own[0], own[1]
    stats = {"records": own_n, "tek_gecerli_teklif": None, "window_days": win.days,
             "idare_turu": turu, "il": il, "usul_turu": usul, "usul_label": ind.usul_label(usul), "peer": None}
    if own_n >= IDARE_MIN_N:
        stats["tek_gecerli_teklif"] = round(own_tek / own_n, 4)
    cands = _candidates(win, turu, il)
    peer_n = peer_tek = 0
    for scope, acc in cands:
        if acc[0] - own_n >= PEER_MIN_N:
            peer_n, peer_tek = acc[0] - own_n, acc[1] - own_tek
            stats["peer"] = {"label": peers.peer_label(scope, turu, il, sector, _lc(ind.usul_label(usul))), "records": peer_n,
                             "tek_gecerli_teklif": round(peer_tek / peer_n, 4)}
            break
    fires = (own_n >= IDARE_MIN_N and stats["peer"] is not None and own_tek > 0
             and own_tek * peer_n >= IDARE_RATIO * peer_tek * own_n)
    return stats, fires


def _elenen_peer(win: _Window, idare_name: str) -> dict:
    """Mean elenen_orani of the peer chain (all procedures), own idare excluded, eligible awards only."""
    ik = normalize_key(idare_name)
    turu, il = peers.idare_turu(idare_name), peers.il_of(idare_name)
    own = win.idare.get(ik, [0, 0, 0, 0.0])
    for _, acc in _candidates(win, turu, il):
        n = acc[2] - own[2]
        if n >= ELENEN_PEER_MIN_N:
            return {"peer": round((acc[3] - own[3]) / n, 4), "n": n}
    return {"peer": None, "n": 0}


class _PayiIndex:
    """Per idare key: deduped awards over time, for yuklenici_payi (TRY bedel share, 365-day window)."""

    def __init__(self, stored: list[StoredRecord]):
        seen: set = set()
        self.by_idare: dict[str, list[tuple]] = {}
        for s in stored:
            r = s.record
            if not r.confident("idare"):
                continue
            ik = normalize_key(r.idare)
            if not ik:
                continue
            tid = (r.bulletin_type, r.ikn) if r.confident("ikn") else ("rec", s.id)
            yk = normalize_key(r.yuklenici) if r.confident("yuklenici") else None
            b = r.sozlesme_bedeli if r.confident("sozlesme_bedeli") and r.sozlesme_bedeli.currency == "TRY" else None
            kurus = b.kurus if b else None
            key = (ik, tid, yk, kurus)
            if key in seen:
                continue
            seen.add(key)
            self.by_idare.setdefault(ik, []).append((r.bulletin_date, tid, yk, kurus))
        for v in self.by_idare.values():
            v.sort(key=lambda e: e[0])
        self._cache: dict = {}

    def window(self, ik: str, d: date):
        """(awards n, total TRY kurus, {yuklenici key: kurus})."""
        key = (ik, d)
        if key not in self._cache:
            rows = self.by_idare.get(ik, [])
            lo_d = d - timedelta(days=PAYI_WINDOW_DAYS)
            tids, total, per = set(), 0, {}
            for dt, tid, yk, kurus in rows:
                if lo_d <= dt <= d:
                    tids.add(tid)
                    if kurus is not None and yk is not None:
                        total += kurus
                        per[yk] = per.get(yk, 0) + kurus
            self._cache[key] = (len(tids), total, per)
        return self._cache[key]


def compute_flags(stored: list[StoredRecord]) -> dict[int, FlagResult]:
    """Flags for every stored record (id → result). Pure: no DB access."""
    return compute_flags_full(stored)[0]


def _score_all(results: dict[int, FlagResult]) -> dict:
    """Rarity-weighted, value-weighted score (§4.1).

    p(part, group) = records in the group where the part's condition holds (ignoring structural exclusions)
    / records in the group where the part is computable. A part whose computable count in the group is < 100 uses
    the all-records rate ("hepsi"); p is floored at 0.001. points = ln(1/p); score_raw = sum of points;
    score = score_raw x w, w = clamp(1 + 0.5 log10(bedel_TRY / group median TRY bedel), 0.5, 1.5), 1 when the
    bedel is missing or not TRY. Returns the part_rates table for meta.json.
    """
    cond: dict[str, dict[str, int]] = {}
    comp: dict[str, dict[str, int]] = {}
    sizes: dict[str, int] = {}
    bedels: dict[str, list[float]] = {}
    for res in results.values():
        for g in {all_group(res.btype), res.usul_group} - {None}:
            sizes[g] = sizes.get(g, 0) + 1
            c1 = cond.setdefault(g, dict.fromkeys(PART_CODES, 0))
            c2 = comp.setdefault(g, dict.fromkeys(PART_CODES, 0))
            for code in res.cond:
                c1[code] += 1
            for code in res.computable:
                c2[code] += 1
            if res.bedel_try is not None:
                bedels.setdefault(g, []).append(res.bedel_try)

    def rate(g: str, code: str) -> float:
        return cond[g][code] / comp[g][code] if comp[g][code] else 0.0

    medians = {g: statistics.median(v) for g, v in bedels.items()}
    for res in results.values():
        parts, total = [], 0.0
        for code in res.score_parts:
            g = res.usul_group if res.usul_group and comp[res.usul_group][code] >= MIN_GROUP_N else all_group(res.btype)
            p = max(rate(g, code), P_FLOOR)
            points = round(math.log(1 / p), 2)
            total += points
            parts.append({"code": code, "points": points, "p": round(p, 4), "p_group": g})
        w = 1.0
        if res.bedel_try is not None:
            g = (res.usul_group if res.usul_group and len(bedels.get(res.usul_group, ())) >= MIN_GROUP_N
                 else all_group(res.btype))
            med = medians.get(g)
            if med and med > 0:
                w = min(1.5, max(0.5, 1 + 0.5 * math.log10(res.bedel_try / med)))
        res.score_parts, res.score_raw = parts, round(total, 2)
        res.value_weight = round(w, 3)
        res.score = round(total * w, 2)
    return {g: {**{c: round(rate(g, c), 4) for c in PART_CODES}, "n": sizes[g],
                "n_computable": dict(comp[g]),
                "bedel_median_try": round(medians[g], 2) if g in medians else None}
            for g in sorted(sizes)}


def kisim_groups(stored: list[StoredRecord]) -> dict[str, dict[tuple, StoredRecord]]:
    """ikn → deduped records of that tender (kısmi lots), keyed by (ikn, yüklenici key, bedel)."""
    groups: dict[str, dict[tuple, StoredRecord]] = {}
    for s in stored:
        if s.record.confident("ikn"):
            groups.setdefault(s.record.ikn, {}).setdefault(_dedupe_key(s), s)
    return groups


def compute_flags_full(stored: list[StoredRecord]) -> tuple[dict[int, FlagResult], dict]:
    """(flags/score per record id, part_rates table for meta.json)."""
    groups = kisim_groups(stored)

    # repeat-contractor history: (idare key, yüklenici key) → sorted [(date, ikn)]
    hist: dict[tuple[str, str], list[tuple[date, str]]] = {}
    for s in stored:
        r = s.record
        if r.confident("ikn") and r.confident("idare") and r.confident("yuklenici"):
            ik, yk = normalize_key(r.idare), normalize_key(r.yuklenici)
            if ik and yk:
                hist.setdefault((ik, yk), []).append((r.bulletin_date, r.ikn))
    for v in hist.values():
        v.sort()

    tenders = _tenders(stored, groups)
    payi_idx = _PayiIndex(stored)
    windows: dict[tuple, _Window] = {}

    results: dict[int, FlagResult] = {}
    for s in stored:
        r = s.record
        res = FlagResult()
        unread: set[str] = _low_confidence_fields(r)
        reasons: list[dict] = []
        members = list(groups[r.ikn].values()) if r.confident("ikn") else [s]
        res.kisim_n = len(members)

        # --- tek_teklif / diger_teklifler_elendi (both need toplam_teklif and gecerli_teklif)
        counts_ok = True
        for name in ("toplam_teklif", "gecerli_teklif"):
            if not r.confident(name):
                unread.add(name)
                counts_ok = False
        if counts_ok:
            if r.toplam_teklif == 1:
                res.flags.append({"code": "tek_teklif", "value": 1, "text": "Tek teklif verildi"})
            elif r.toplam_teklif > 1 and r.gecerli_teklif == 1:
                res.flags.append({
                    "code": "diger_teklifler_elendi", "value": r.toplam_teklif,
                    "text": f"{r.toplam_teklif} teklif verildi, yalnızca kazananınki geçerli sayıldı"})

        # --- bedel_orani
        ratio_val = None
        check = None
        est = _estimate(r)
        ok = True
        if est is None:
            unread.add("yaklasik_maliyet")
            ok = False
        elif est[1].kurus <= 0:
            unread.add(est[0])
            ok = False
        if ok:
            if any(not m.record.confident("sozlesme_bedeli") for m in members):
                unread.add("sozlesme_bedeli")
                ok = False
            elif any(m.record.sozlesme_bedeli.currency != est[1].currency for m in members):
                reasons.append({"field": "sozlesme_bedeli", "reason": CURRENCY_MISMATCH})
                ok = False
        elif not r.confident("sozlesme_bedeli"):
            unread.add("sozlesme_bedeli")
        if ok:
            total = sum(m.record.sozlesme_bedeli.kurus for m in members)
            est_k = est[1].kurus
            ratio_val = total / est_k
            check = source_check(ratio_val)
            if total * 100 >= est_k * RATIO_THRESHOLD_PCT:
                pct = total * 100 // est_k          # floor: 0.999 → 99
                if len(members) == 1:
                    lead = "Sözleşme bedeli"
                else:
                    lead = f"Bu ihalenin {len(members)} kısmının toplam bedeli"
                if total > est_k:
                    text = (f"{lead} yaklaşık maliyetin {money_tr(total - est_k, est[1].currency)} üzerinde "
                            f"(%{percent_tr(total, est_k)})")
                else:
                    text = f"{lead} yaklaşık maliyetin {percent_possessive(pct)}"
                flag = {"code": "bedel_orani", "value": total / est_k, "text": text}
                if check == "typo":
                    flag["source_check"], flag["text"] = "typo", text + TYPO_NOTE
                elif check == "large":
                    flag["source_check"], flag["text"] = "large", text + LARGE_NOTE
                res.flags.append(flag)

        # --- tekrarlayan_yuklenici
        inputs_ok = True
        for name in ("ikn", "idare", "yuklenici"):
            if not r.confident(name):
                unread.add(name)
                inputs_ok = False
        if inputs_ok:
            ik, yk = normalize_key(r.idare), normalize_key(r.yuklenici)
            if ik and yk:
                series = hist.get((ik, yk), [])
                d = r.bulletin_date
                lo = bisect.bisect_left(series, (d - timedelta(days=REPEAT_WINDOW_DAYS), ""))
                hi = bisect.bisect_right(series, (d, "￿"))
                n = len({ikn for _, ikn in series[lo:hi]})
                if n >= REPEAT_MIN_IKNS:
                    res.flags.append({
                        "code": "tekrarlayan_yuklenici", "value": n,
                        "text": f"Bu yüklenici son 12 ayda bu idareden {n} sözleşme aldı (bu dahil)"})

        res.unreadable = [f for f in _MODEL_ORDER if f in unread] + reasons

        # --- idare_orani + score (§4.1) and indicators (§4.2)
        idare_fires = False
        idare_raw = False
        elen_peer = {"peer": None, "n": 0}
        bedel_peer = (None, 0)
        idare_computable = False
        usul_code = ind.usul_turu(r.ihale_usulu) if r.confident("ihale_usulu") else None
        usul = ind.usul_group(r.idare if r.confident("idare") else None, usul_code)   # DMO 3-g split off
        rule = None
        ik = normalize_key(r.idare) if r.confident("idare") else None
        if ik:
            wkey = (r.bulletin_type, r.bulletin_date, None)
            if wkey not in windows:
                windows[wkey] = _Window(tenders.get(r.bulletin_type, []), r.bulletin_date)
            elen_peer = _elenen_peer(windows[wkey], r.idare)
            rule = structural.match(r.idare, usul_code)
            if rule:
                res.structural = {"id": rule.id, "text": rule.reason_tr}
            if usul:     # idare comparison runs within the record's procedure group
                ukey = (r.bulletin_type, r.bulletin_date, usul)
                if ukey not in windows:
                    windows[ukey] = _Window(tenders.get(r.bulletin_type, []), r.bulletin_date, usul)
                res.idare_stats, idare_fires = idare_stats(windows[ukey], r.idare, r.bulletin_type, usul)
                idare_computable = res.idare_stats["records"] >= IDARE_MIN_N and res.idare_stats["peer"] is not None
                idare_raw = idare_fires
                if rule and structural.OWN_PEER_GROUP in rule.effects:
                    res.idare_stats["peer"] = None
                    res.idare_stats["peer_note"] = structural.PEER_NOTE
                    idare_fires = False
                elif ratio_val is not None:     # per-procedure peer chain, like idare_stats
                    bedel_peer = windows[ukey].peer_ratio_median(ik, peers.idare_turu(r.idare), peers.il_of(r.idare))
        have = {f["code"] for f in res.flags}
        if check == "typo":
            have.discard("bedel_orani")      # probable source typo: shown, but no points, no partner, not in p
        # conditions and computability, ignoring structural exclusions (the base rates must not lose them)
        cond = {c for c in ("tek_teklif", "diger_teklifler_elendi", "bedel_orani") if c in have}
        if idare_raw:
            cond.add("idare_orani")
        if "tekrarlayan_yuklenici" in have and cond:
            cond.add("tekrarlayan_eslesik")
        comp = set()
        if counts_ok:
            comp |= {"tek_teklif", "diger_teklifler_elendi"}
        if ratio_val is not None and check != "typo":
            comp.add("bedel_orani")
        if idare_computable:
            comp.add("idare_orani")
        if inputs_ok:
            comp.add("tekrarlayan_eslesik")
        res.cond, res.computable = cond, comp
        b = r.sozlesme_bedeli
        res.bedel_try = b.kurus / 100 if r.confident("sozlesme_bedeli") and b.currency == "TRY" and b.kurus > 0 else None
        if res.structural and structural.NO_SINGLE_BID_POINTS in rule.effects:
            have -= {"tek_teklif", "diger_teklifler_elendi"}      # still shown as flags, but no points
        parts = {c for c in ("tek_teklif", "diger_teklifler_elendi", "bedel_orani") if c in have}
        if idare_fires:
            parts.add("idare_orani")
        if "tekrarlayan_yuklenici" in have and parts:     # a bare repeat earns nothing (the flag is still shown)
            parts.add("tekrarlayan_eslesik")
        res.score_parts = [c for c in PART_CODES if c in parts]      # codes for now; _score_all adds the points
        res.btype = r.bulletin_type
        res.usul_group = group_key(r.bulletin_type, usul)
        res.indicators = _indicators(r, ik, counts_ok, elen_peer, payi_idx, ratio_val, bedel_peer, check)
        results[s.id] = res
    return results, _score_all(results)


def _indicators(r: Record, ik: str | None, counts_ok: bool, elen_peer: dict, payi_idx: "_PayiIndex",
                ratio_val: float | None = None, bedel_peer: tuple = (None, 0), check: str | None = None) -> dict:
    elen = ind.elenen_orani(r.toplam_teklif, r.gecerli_teklif) if counts_ok else None
    karar = None
    if r.confident("ihale_tarihi") and r.confident("sozlesme_tarihi"):
        karar = ind.karar_suresi_gun(r.ihale_tarihi, r.sozlesme_tarihi)
        if karar is None:
            log.warning("%s %s-%s: sozlesme_tarihi %s is before ihale_tarihi %s; karar_suresi_gun left null",
                        r.bulletin_date, r.section, r.seq, r.sozlesme_tarihi, r.ihale_tarihi)
    code = ind.usul_turu(r.ihale_usulu) if r.confident("ihale_usulu") else None
    payi = payi_n = None
    if ik and r.confident("yuklenici"):
        n, total, per = payi_idx.window(ik, r.bulletin_date)
        payi_n = n
        yk = normalize_key(r.yuklenici)
        if n >= PAYI_MIN_AWARDS and total > 0 and yk in per:
            payi = round(per[yk] / total, 4)
    return {
        "elenen_orani": None if elen is None else round(elen, 4),
        "elenen_orani_peer": elen_peer["peer"] if elen is not None else None,
        "elenen_orani_peer_n": elen_peer["n"] if elen is not None else None,
        "karar_suresi_gun": karar,
        "usul_turu": code, "acik_olmayan": ind.acik_olmayan(code),
        "yuklenici_payi": payi, "yuklenici_payi_n": payi_n,
        # the real value with its peer context (no threshold is ever exported); same number the flag uses
        "bedel_orani": ratio_val,
        "source_check": check,
        "bedel_orani_peer_median": bedel_peer[0] if ratio_val is not None else None,
        "bedel_orani_peer_n": bedel_peer[1] if ratio_val is not None and bedel_peer[0] is not None else None,
    }
