"""IMCO-style idare scorecard (M5c; docs/m5c-scorecard-draft.md). Computation only; a derived view, never stored.

Per (bulletin type, idare): three sub-indices (competition, transparency, rule compliance), each the mean of its
components' percentiles against the idare's peer group (turu+il -> turu -> all idares of the type, the first group
with >= 30 other eligible idares for that component). Index = mean of the sub-indices (needs >= 2 of 3). Framed as
"risk, not cases": every component carries its value, percentile, n and peer label. Nothing refers to a yüklenici.
Structural exclusions (structural table, M5g rules) never raise a rule-compliance component.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from . import flags, indicators as ind, peers
from .keys import normalize_key
from .store import StoredRecord

MIN_AWARDS = 10              # an idare needs >= 10 awards of a type for a scorecard
MIN_COMPONENT = 5            # a component needs >= 5 awards that can tell
PEER_MIN_IDARES = 30
LOW_SAMPLE = 20              # "düşük örnek" note below this many awards
DOWNLOADER_COVERAGE = 0.5

SUBS = (
    ("competition", "Rekabet", ("tek_gecerli", "elenen", "downloader_bid_ratio")),
    ("transparency", "Şeffaflık", ("missing_estimate", "unreadable", "non_open")),
    ("rule_compliance", "Usul uyumu", ("pazarlik_21b", "istisna")),
)
COMPONENT_LABELS = {
    "tek_gecerli": "Tek geçerli teklif payı",
    "elenen": "Elenen teklif oranı (ortalama)",
    "downloader_bid_ratio": "Doküman indiren / teklif veren oranı (ortalama)",
    "missing_estimate": "Yaklaşık maliyeti okunamayan pay",
    "unreadable": "Okunamayan alan içeren pay",
    "non_open": "Açık / belli istekliler dışı usul payı",
    "pazarlik_21b": "Pazarlık 21/b payı",
    "istisna": "İstisna usul payı (yapısal açıklaması olanlar hariç)",
}


@dataclass
class _Award:
    tek: bool | None = None
    elen: float | None = None
    dl: float | None = None
    missing_est: bool = False
    unreadable: bool = False
    non_open: bool | None = None
    p21b: bool | None = None
    istisna: bool | None = None          # istisna and not structurally explained
    istisna_raw: bool | None = None


def _awards(stored: list[StoredRecord]) -> dict[tuple, dict]:
    """(type, idare key) -> {tid: _Award}; one award per ikn, merging its rows."""
    out: dict[tuple, dict] = defaultdict(dict)
    for s in stored:
        r = s.record
        ik = normalize_key(r.idare) if r.confident("idare") else None
        if not ik:
            continue
        tid = (r.bulletin_type, r.ikn) if r.confident("ikn") else ("rec", s.id)
        a = out[(r.bulletin_type, ik)].setdefault(tid, _Award())
        counts_ok = r.confident("gecerli_teklif") and r.confident("toplam_teklif")
        if a.tek is None and counts_ok:
            a.tek = r.gecerli_teklif == 1
            a.elen = ind.elenen_orani(r.toplam_teklif, r.gecerli_teklif)
        if flags._estimate(r) is None:
            a.missing_est = True
        if s.unreadable:
            a.unreadable = True
        code = ind.usul_turu(r.ihale_usulu) if r.confident("ihale_usulu") else None
        if code is not None and a.non_open is None:
            a.non_open = code not in ind.OPEN_USUL
            a.p21b = code == "pazarlik_21b"
            a.istisna_raw = code.startswith("istisna")
            a.istisna = a.istisna_raw and not s.structural
        dl = (s.indicators or {}).get("downloader_bid_ratio")
        if dl is not None and a.dl is None:
            a.dl = dl
    return out


def _values(awards: list[_Award]) -> dict[str, dict]:
    """component -> {"value", "n"} for one idare (None when below its minimum)."""
    def share(vals):
        vals = [v for v in vals if v is not None]
        return (sum(1 for v in vals if v) / len(vals), len(vals)) if len(vals) >= MIN_COMPONENT else None

    def mean(vals):
        vals = [v for v in vals if v is not None]
        return (sum(vals) / len(vals), len(vals)) if len(vals) >= MIN_COMPONENT else None

    n = len(awards)
    dl = [a.dl for a in awards if a.dl is not None]
    raw = {
        "tek_gecerli": share([a.tek for a in awards]),
        "elenen": mean([a.elen for a in awards]),
        "downloader_bid_ratio": (sum(dl) / len(dl), len(dl)) if len(dl) >= max(MIN_COMPONENT, DOWNLOADER_COVERAGE * n) else None,
        "missing_estimate": (sum(a.missing_est for a in awards) / n, n),
        "unreadable": (sum(a.unreadable for a in awards) / n, n),
        "non_open": share([a.non_open for a in awards]),
        "pazarlik_21b": share([a.p21b for a in awards]),
        "istisna": share([a.istisna for a in awards]),
    }
    return {k: ({"value": round(v[0], 4), "n": v[1]} if v else None) for k, v in raw.items()}


def _percentile(v: float, peers_: list[float]) -> float:
    less = sum(1 for x in peers_ if x < v)
    eq = sum(1 for x in peers_ if x == v)
    return round(100 * (less + 0.5 * eq) / len(peers_), 1)


def compute(stored: list[StoredRecord]) -> dict[str, dict]:
    """idare key -> {type: scorecard block}. Only idares with >= MIN_AWARDS awards of that type."""
    awards = _awards(stored)
    names: dict[str, str] = {}
    for s in stored:
        r = s.record
        if r.confident("idare"):
            ik = normalize_key(r.idare)
            if ik:
                names.setdefault(ik, r.idare)
    elig: dict[tuple, dict] = {}
    for (typ, ik), aw in awards.items():
        if len(aw) >= MIN_AWARDS:
            name = names[ik]
            elig[(typ, ik)] = {"vals": _values(list(aw.values())), "n": len(aw),
                               "turu": peers.idare_turu(name), "il": peers.il_of(name)}
    out: dict[str, dict] = defaultdict(dict)
    for (typ, ik), e in sorted(elig.items()):
        peers_of = {k: v for k, v in elig.items() if k[0] == typ and k[1] != ik}
        subs, sub_idx = {}, []
        for code, label, comps in SUBS:
            cdata, pcts = {}, []
            for c in comps:
                v = e["vals"].get(c)
                if v is None:
                    cdata[c] = None
                    continue
                scopes = ([("turu_il", e["turu"], e["il"])] if e["il"] else []) + [("turu", e["turu"], None), ("all", None, None)]
                got = None
                for sc, turu, il in scopes:
                    grp = [p["vals"][c]["value"] for k, p in peers_of.items() if p["vals"].get(c) is not None
                           and (sc == "all" or (p["turu"] == turu and (sc == "turu" or p["il"] == il)))]
                    if len(grp) >= PEER_MIN_IDARES:
                        got = {"label": peers.peer_label(sc if sc != "all" else "sector", e["turu"], e["il"], typ),
                               "idares": len(grp), "percentile": _percentile(v["value"], grp)}
                        break
                cdata[c] = {"value": v["value"], "n": v["n"], "peer": got,
                            "percentile": got["percentile"] if got else None}
                if got:
                    pcts.append(got["percentile"])
            idx = round(sum(pcts) / len(pcts), 1) if pcts else None
            subs[code] = {"label": label, "index": idx, "components": cdata}
            if idx is not None:
                sub_idx.append(idx)
        index = round(sum(sub_idx) / len(sub_idx), 1) if len(sub_idx) >= 2 else None
        out[ik][typ] = {"n": e["n"], "index": index, "low_sample": e["n"] < LOW_SAMPLE, "sub": subs,
                        "turu": e["turu"], "il": e["il"]}
    return dict(out)
