"""Research history database (private, never exported): the backfilled bulletins parsed with the SAME parser and flag
code as the pipeline, into `<data>/research/history.db`. ihale.db, the site and D1 are never touched.

Which bulletins: every cached SONUC pdf whose day is NOT in ihale.db (the daily/rolling store). A (day, type) that was
parsed once (a `runs` row, also with 0 records) is skipped on re-runs, so the command is idempotent and cheap; flags are
recomputed over the whole history.db only when something new was parsed (or --reflag). The flags see only the days in
history.db: sample days are sparse, so the idare-history based parts are weaker there. Descriptive use only.

"sample" days are the dates of the backfill plan file (`backfill-plan.txt`); "walk" days are the rest.
"""
from __future__ import annotations

import json
import logging
import statistics
import time
from datetime import date
from pathlib import Path

from . import backfill_history, config, ekap, pipeline
from .flags import compute_flags_full
from .store import Store

log = logging.getLogger("ihale")
TYPES = ("mal", "hizmet", "yapim")


def db_path() -> Path:
    return config.data_dir() / "research" / "history.db"


def _cached_days() -> list[tuple[date, str]]:
    root = config.bulletins_dir()
    out = []
    for d in sorted(root.glob("????-??-??")):
        try:
            day = date.fromisoformat(d.name)
        except ValueError:
            continue
        for t in TYPES:
            if pipeline.find_sonuc_pdf(day, t, root) is not None:
                out.append((day, t))
    return out


def sample_days() -> set[date]:
    p = backfill_history.plan_path()
    if not p.is_file():
        return set()
    return {e.day for e in backfill_history.load_plan(p)}


def sync(reflag: bool = False, limit: int | None = None, max_seconds: float | None = None) -> dict:
    """Parse what is not parsed yet, then (re)flag. Returns counts. `max_seconds`: stop STARTING new bulletins after
    that long (the rest stays pending for the next call); every bulletin is one atomic transaction, so a kill is safe."""
    t0 = time.monotonic()
    main_days = set(Store().dates())
    hs = Store(db_path())
    done = {(r["bulletin_date"], r["bulletin_type"]) for r in hs.runs()}
    todo = [(d, t) for d, t in _cached_days() if d not in main_days and (d.isoformat(), t) not in done]
    if limit:
        todo = todo[:limit]
    parsed = failed = 0
    for d, t in todo:
        if max_seconds is not None and time.monotonic() - t0 > max_seconds:
            break
        try:
            pipeline.parse_and_store(d, t, hs)
            parsed += 1
        except Exception as e:  # noqa: BLE001  (a bad old pdf must not stop the rest)
            failed += 1
            log.error("history parse %s %s failed: %s: %s", d, t, type(e).__name__, e)
    if parsed or reflag:
        results, part_rates = compute_flags_full(hs.all_records())
        hs.set_meta("part_rates", part_rates)
        hs.set_flags({i: {"flags": r.flags, "unreadable": r.unreadable, "kisim_n": r.kisim_n, "score": r.score,
                          "score_parts": r.score_parts, "idare_stats": r.idare_stats, "indicators": r.indicators,
                          "structural": r.structural, "score_raw": r.score_raw, "value_weight": r.value_weight}
                         for i, r in results.items()})
    log.info("history-parse: %d parsed, %d failed, %d already done", parsed, failed, len(done))
    return {"parsed": parsed, "failed": failed, "already": len(done), "pending": len(todo) - parsed - failed}


def _median(xs):
    return round(statistics.median(xs), 3) if xs else None


def report(path: Path | None = None) -> list[dict]:
    """One row per (year, kind[sample|walk], type). `records` / `warnings` count parsed records; the base rates are per
    AWARD (distinct ikn, a record without a confident ikn is its own award), using the pipeline's own flags/indicators:
    tek_teklif share of awards with both bid counts readable; diger_teklifler_elendi share of the awards with >= 2 bids
    and both counts readable; median of the bedel_orani indicator (sum of lots / estimate) over awards where it exists."""
    hs = Store(path or db_path())
    samp = sample_days()
    rows: dict[tuple, dict] = {}
    seen: set[tuple] = set()
    for s in hs.all_records():
        r = s.record
        key = (r.bulletin_date.year, "sample" if r.bulletin_date in samp else "walk", r.bulletin_type)
        x = rows.setdefault(key, {"days": set(), "records": 0, "warnings": 0, "n": 0, "tek": 0, "n2": 0, "elendi": 0,
                                  "ratio": []})
        x["days"].add(r.bulletin_date)
        x["records"] += 1
        x["warnings"] += len(r.warnings)
        aw = (key, r.ikn) if r.confident("ikn") else (key, s.id)
        if aw in seen:
            continue
        seen.add(aw)
        codes = {f["code"] for f in (s.flags or [])}
        if r.confident("toplam_teklif") and r.confident("gecerli_teklif"):
            x["n"] += 1
            x["tek"] += "tek_teklif" in codes
            if r.toplam_teklif and r.toplam_teklif >= 2:
                x["n2"] += 1
                x["elendi"] += "diger_teklifler_elendi" in codes
        v = (s.indicators or {}).get("bedel_orani")
        if v is not None:
            x["ratio"].append(v)
    out = []
    for k in sorted(rows):
        x = rows[k]
        out.append({"year": k[0], "kind": k[1], "type": k[2], "days": len(x["days"]), "records": x["records"],
                    "warnings": x["warnings"], "awards_with_counts": x["n"],
                    "tek_teklif_share": round(x["tek"] / x["n"], 3) if x["n"] else None,
                    "awards_2plus_bids": x["n2"],
                    "diger_elendi_share": round(x["elendi"] / x["n2"], 3) if x["n2"] else None,
                    "bedel_ym_median": _median(x["ratio"]), "ratio_n": len(x["ratio"])})
    return out


def write_report() -> Path:
    out = db_path().with_name("history-report.json")
    out.write_text(json.dumps(report(), ensure_ascii=False, indent=1), encoding="utf-8")
    return out
