"""Neutral flags (docs/data-contract.md §4, SPEC §6). Facts only; every flag carries its numbers.

A flag is computed only when every input field is confident; otherwise the inputs are reported as `unreadable`.
Keys are recomputed from the raw names here (not read from the DB), so a normalizer change only needs a re-flag.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field, fields
from datetime import date, timedelta

from .keys import normalize_key
from .model import CONFIDENT, Money, Record
from .store import StoredRecord

CURRENCY_MISMATCH = "para birimi farklı"
RATIO_THRESHOLD_PCT = 95          # ratio >= 0.95
REPEAT_MIN_IKNS = 3
REPEAT_WINDOW_DAYS = 365          # bulletin dates in [d - 365 days, d]

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
        results[s.id] = res
    return results
