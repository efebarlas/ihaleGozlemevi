"""Neutral flags (docs/data-contract.md §4, SPEC §6). Facts only; every flag carries its numbers.

A flag is computed only when every input field is confident; otherwise the inputs are reported as `unreadable`.
Keys are recomputed from the raw names here (not read from the DB), so a normalizer change only needs a re-flag.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field, fields
from datetime import date, timedelta

from . import peers
from .keys import normalize_key
from .model import CONFIDENT, Money, Record
from .store import StoredRecord

CURRENCY_MISMATCH = "para birimi farklı"
RATIO_THRESHOLD_PCT = 97          # ratio >= 0.97 (ihalent's low_discount: kırım < 3%)
REPEAT_MIN_IKNS = 3
REPEAT_WINDOW_DAYS = 365          # bulletin dates in [d - 365 days, d]
IDARE_WINDOW_DAYS = 30            # idare/peer stats: tenders dated in (d - 30 days, d]
IDARE_MIN_N = 5                   # an idare-level rate needs >= 5 awards (tenders) in the window
PEER_MIN_N = 20                   # a peer group needs >= 20 awards, excluding the idare itself
IDARE_RATIO = 2                   # idare_orani: idare share >= 2x peer share

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


def percent_possessive(n: int) -> str:
    """'%97'si', '%100'ü', ..."""
    return f"%{n}'{possessive_suffix(n)}"


# ------------------------------------------------------------------ results
@dataclass
class FlagResult:
    flags: list[dict] = field(default_factory=list)
    unreadable: list = field(default_factory=list)   # field names and {"field", "reason"} objects
    kisim_n: int = 1
    score: int = 0
    score_parts: list = field(default_factory=list)
    idare_stats: dict | None = None


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
    tek: bool | None


def _tenders(stored: list[StoredRecord]) -> dict[str, list[_Tender]]:
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
        tek = (r.gecerli_teklif == 1) if r.confident("gecerli_teklif") else None
        t = by_id.get(tid)
        if t is None:
            by_id[tid] = _Tender(r.bulletin_date, ik, peers.idare_turu(r.idare), peers.il_of(r.idare),
                                 r.bulletin_type, tek)
        else:
            t.date = min(t.date, r.bulletin_date)
            if t.tek is None:
                t.tek = tek
    out: dict[str, list[_Tender]] = {}
    for t in by_id.values():
        if t.tek is not None:
            out.setdefault(t.sector, []).append(t)
    for v in out.values():
        v.sort(key=lambda t: t.date)
    return out


class _Window:
    """Counts [awards, tek awards] in one (sector, date) window."""

    def __init__(self, tenders: list[_Tender], d: date):
        dates = [t.date for t in tenders]
        lo = bisect.bisect_right(dates, d - timedelta(days=IDARE_WINDOW_DAYS))
        hi = bisect.bisect_right(dates, d)
        self.idare: dict[str, list[int]] = {}
        self.turu_il: dict[tuple, list[int]] = {}
        self.turu: dict[str, list[int]] = {}
        self.all = [0, 0]
        for t in tenders[lo:hi]:
            tek = 1 if t.tek else 0
            for acc in (self.idare.setdefault(t.idare_key, [0, 0]), self.all,
                        self.turu.setdefault(t.turu, [0, 0]),
                        self.turu_il.setdefault((t.turu, t.il), [0, 0])):
                acc[0] += 1
                acc[1] += tek


def idare_stats(win: _Window, idare_name: str, sector: str) -> tuple[dict, bool]:
    """(stats dict for export, idare_orani fires)."""
    ik = normalize_key(idare_name)
    turu, il = peers.idare_turu(idare_name), peers.il_of(idare_name)
    own_n, own_tek = win.idare.get(ik, [0, 0])
    stats = {"records": own_n, "tek_gecerli_teklif": None, "window_days": IDARE_WINDOW_DAYS,
             "idare_turu": turu, "il": il, "peer": None}
    if own_n >= IDARE_MIN_N:
        stats["tek_gecerli_teklif"] = round(own_tek / own_n, 4)
    candidates = []
    if il:
        candidates.append(("turu_il", win.turu_il.get((turu, il), [0, 0])))
    candidates.append(("turu", win.turu.get(turu, [0, 0])))
    candidates.append(("sector", win.all))
    peer_n = peer_tek = 0
    for scope, (n, tek) in candidates:
        if n - own_n >= PEER_MIN_N:
            peer_n, peer_tek = n - own_n, tek - own_tek
            stats["peer"] = {"label": peers.peer_label(scope, turu, il, sector), "records": peer_n,
                             "tek_gecerli_teklif": round(peer_tek / peer_n, 4)}
            break
    fires = (own_n >= IDARE_MIN_N and stats["peer"] is not None and own_tek > 0
             and own_tek * peer_n >= IDARE_RATIO * peer_tek * own_n)
    return stats, fires


def compute_flags(stored: list[StoredRecord]) -> dict[int, FlagResult]:
    """Flags for every stored record (id → result). Pure: no DB access."""
    # ikn groups (kısmi): deduped by (ikn, yüklenici key, bedel)
    groups: dict[str, dict[tuple, StoredRecord]] = {}
    for s in stored:
        if s.record.confident("ikn"):
            groups.setdefault(s.record.ikn, {}).setdefault(_dedupe_key(s), s)

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

    tenders = _tenders(stored)
    windows: dict[tuple, _Window] = {}

    results: dict[int, FlagResult] = {}
    for s in stored:
        r = s.record
        res = FlagResult()
        unread: set[str] = _low_confidence_fields(r)
        reasons: list[dict] = []
        members = list(groups[r.ikn].values()) if r.confident("ikn") else [s]
        res.kisim_n = len(members)

        # --- tek_gecerli_teklif
        if not r.confident("gecerli_teklif"):
            unread.add("gecerli_teklif")
        elif r.gecerli_teklif == 1:
            text = "Tek geçerli teklif"
            if r.confident("toplam_teklif") and r.toplam_teklif > 1:
                text += f" ({r.toplam_teklif} teklif, 1 geçerli)"
            res.flags.append({"code": "tek_gecerli_teklif", "value": 1, "text": text})

        # --- bedel_orani
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
            if total * 100 >= est_k * RATIO_THRESHOLD_PCT:
                pct = total * 100 // est_k          # floor: 0.999 → 99
                if len(members) == 1:
                    lead = "Sözleşme bedeli"
                else:
                    lead = f"Bu ihalenin {len(members)} kısmının toplam bedeli"
                if total > est_k:
                    text = f"{lead} yaklaşık maliyetin üzerinde (%{pct})"
                else:
                    text = f"{lead} yaklaşık maliyetin {percent_possessive(pct)}"
                res.flags.append({"code": "bedel_orani", "value": total / est_k, "text": text})

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

        # --- idare_orani + score (§4.1)
        idare_fires = False
        if r.confident("idare") and normalize_key(r.idare):
            wkey = (r.bulletin_type, r.bulletin_date)
            if wkey not in windows:
                windows[wkey] = _Window(tenders.get(r.bulletin_type, []), r.bulletin_date)
            res.idare_stats, idare_fires = idare_stats(windows[wkey], r.idare, r.bulletin_type)
        have = {f["code"] for f in res.flags}
        parts = [c for c in ("tek_gecerli_teklif", "bedel_orani") if c in have]
        if "tekrarlayan_yuklenici" in have and parts:
            parts.append("tekrarlayan_yuklenici")
        if idare_fires:
            parts.append("idare_orani")
        weights = {"tek_gecerli_teklif": 1, "bedel_orani": 1, "tekrarlayan_yuklenici": 2, "idare_orani": 1}
        res.score_parts = parts
        res.score = sum(weights[p] for p in parts)
        results[s.id] = res
    return results
