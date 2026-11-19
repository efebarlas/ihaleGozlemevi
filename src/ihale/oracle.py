"""Oracle candidates for Günün sorusu (docs/data-contract.md §5.1, SPEC §9.1).

Writes `<data>/oracle/candidates.json`: 3-5 tender pairs where the current score is least certain. Local only: never
deployed or committed. This module never touches `oracle/log.jsonl` (the spec owner's file).
"""
from __future__ import annotations

from datetime import datetime
from itertools import combinations
from pathlib import Path

from . import config
from .export import _write_json, istanbul_now, tender_json
from .store import Store

MIN_SCORE, MAX_SCORE = 1, 3          # the band around the Bugün cut-off (score >= 2)
MAX_SCORE_GAP = 1
MIN_PAIRS, MAX_PAIRS = 3, 5
POOL_LIMIT = 400                     # pair search is quadratic: keep the highest-bedel records (deterministic)
QUESTION = "Hangisi bir muhabirin zamanına daha çok değer?"


def oracle_dir() -> Path:
    return config.data_dir() / "oracle"


def _try_amount(t: dict) -> float:
    b = t.get("sozlesme_bedeli")
    return b["amount"] if b and b.get("currency") == "TRY" else 0.0


def _single_swap(pa: set, pb: set) -> bool:
    return len(pa - pb) == 1 and len(pb - pa) == 1


def _parts_text(parts) -> str:
    return " + ".join(parts) if parts else "(işaret yok)"


def select_pairs(tenders: list[dict]) -> list[tuple[dict, dict]]:
    """Deterministic selection over day-export tender dicts (see §5.1).

    Pool: 1 <= score <= 3, one representative per ikn (the highest TRY bedel; kısmi lots are near-duplicates).
    Eligible pair: scores differ by <= 1 and the score_parts sets differ. Rank: single-swap first, then equal
    scores, then higher combined TRY bedel, then ids. Greedy, each record used at most once, up to 5 pairs.
    """
    best: dict = {}
    for t in tenders:
        if not (MIN_SCORE <= t["score"] <= MAX_SCORE):
            continue
        k = t["ikn"] or t["id"]
        cur = best.get(k)
        if cur is None or (_try_amount(t), t["id"]) > (_try_amount(cur), cur["id"]):
            best[k] = t
    pool = sorted(best.values(), key=lambda t: (-_try_amount(t), t["id"]))[:POOL_LIMIT]

    ranked = []
    for a, b in combinations(pool, 2):
        if abs(a["score"] - b["score"]) > MAX_SCORE_GAP:
            continue
        pa, pb = set(a["score_parts"]), set(b["score_parts"])
        if pa == pb:
            continue
        ranked.append(((not _single_swap(pa, pb), abs(a["score"] - b["score"]),
                        -(_try_amount(a) + _try_amount(b)), a["id"], b["id"]), a, b))
    ranked.sort(key=lambda x: x[0])

    used: set = set()
    out: list[tuple[dict, dict]] = []
    for _, a, b in ranked:
        if a["id"] in used or b["id"] in used:
            continue
        used.update((a["id"], b["id"]))
        a, b = sorted((a, b), key=lambda t: t["id"])
        out.append((a, b))
        if len(out) == MAX_PAIRS:
            break
    return out


def _describe(a: dict, b: dict) -> tuple[str, str]:
    pa, pb = set(a["score_parts"]), set(b["score_parts"])
    if a["score"] == b["score"]:
        why = f"aynı skor ({a['score']}), farklı işaret karışımı: "
    else:
        why = f"skorlar {a['score']} ve {b['score']}, farklı işaret karışımı: "
    why += f"{_parts_text(a['score_parts'])} / {_parts_text(b['score_parts'])}"
    if _single_swap(pa, pb):
        (x,), (y,) = sorted(pa - pb), sorted(pb - pa)
        would = f"{x} ağırlığı ile {y} ağırlığı arasındaki sıra"
    else:
        would = (f"{_parts_text(a['score_parts'])} ile {_parts_text(b['score_parts'])} "
                 "karışımlarının göreli ağırlıkları")
    return why, would


def build_candidates(tenders: list[dict], day: str | None, now: datetime | None = None) -> dict:
    pairs = select_pairs(tenders)
    out = {"schema": 1, "date": day, "generated_at": (now or istanbul_now()).isoformat(timespec="seconds"),
           "pairs": []}
    for i, (a, b) in enumerate(pairs, 1):
        why, would = _describe(a, b)
        out["pairs"].append({"pair_id": f"{day}-{i}", "why": why, "would_change": would,
                             "question": QUESTION, "a": a, "b": b})
    if len(pairs) < MIN_PAIRS:
        out["note"] = (f"Yalnızca {len(pairs)} aday çift bulundu: skoru 1–3 arasında olan ve işaret karışımı "
                       "farklı yeterli kayıt yok.")
    return out


def write_candidates(store: Store | None = None, out: Path | None = None, now: datetime | None = None) -> Path:
    """Write candidates.json for the latest stored date. Returns its path."""
    store = store or Store()
    days = store.dates()
    day = days[-1].isoformat() if days else None
    tenders = [tender_json(s) for s in store.all_records() if day and s.record.bulletin_date.isoformat() == day]
    path = (Path(out) if out else oracle_dir()) / "candidates.json"
    _write_json(path, build_candidates(tenders, day, now))
    return path
