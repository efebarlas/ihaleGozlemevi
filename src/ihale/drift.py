"""Drift monitoring (M5d; SPEC §6.1 "Anticipate gaming"). Log-only: never published, never scored.

Compares each idare's procedure mix, score parts and volume over the last 7 days with its own earlier history
(per bulletin type) and writes a weekly summary to `<data>/logs/drift-<ISO week>.json` and `.txt`. A shift is listed
only with enough awards on both sides; it says "look here", not that anything is wrong. The 80% D1 usage warning
lives in `sitegen.d1` and is repeated in the summary header.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from . import config, indicators as ind
from .keys import normalize_key
from .store import StoredRecord

log = logging.getLogger("ihale.drift")

RECENT_DAYS = 7
MIN_RECENT = 5            # awards in the last week
MIN_PRIOR = 10            # awards in the earlier history
SHARE_JUMP = 0.20         # absolute change in a procedure share
VOLUME_RATIO = 2.0        # weekly volume vs the idare's own earlier weekly average (or its inverse)


def _awards(stored: list[StoredRecord]) -> dict[tuple, dict]:
    """(type, idare key) -> {tid: {"date", "non_open", "p21b", "istisna", "parts"}} (one per ikn)."""
    out: dict[tuple, dict] = defaultdict(dict)
    for s in stored:
        r = s.record
        ik = normalize_key(r.idare) if r.confident("idare") else None
        if not ik:
            continue
        tid = (r.bulletin_type, r.ikn) if r.confident("ikn") else ("rec", s.id)
        code = ind.usul_turu(r.ihale_usulu) if r.confident("ihale_usulu") else None
        a = out[(r.bulletin_type, ik)].get(tid)
        if a is None:
            out[(r.bulletin_type, ik)][tid] = {
                "date": r.bulletin_date,
                "non_open": None if code is None else code not in ind.OPEN_USUL,
                "p21b": None if code is None else code == "pazarlik_21b",
                "istisna": None if code is None else (code.startswith("istisna") and not s.structural),
                "parts": len(s.score_parts or []),
                "name": r.idare}
    return out


def _share(items: list[dict], key: str):
    vals = [a[key] for a in items if a[key] is not None]
    return (sum(1 for v in vals if v) / len(vals)) if len(vals) >= 3 else None


def compute(stored: list[StoredRecord], as_of: date | None = None) -> dict:
    as_of = as_of or max((s.record.bulletin_date for s in stored), default=date.today())
    cut = as_of - timedelta(days=RECENT_DAYS)
    shifts = []
    for (typ, ik), aw in _awards(stored).items():
        recent = [a for a in aw.values() if cut < a["date"] <= as_of]
        prior = [a for a in aw.values() if a["date"] <= cut]
        if len(recent) < MIN_RECENT or len(prior) < MIN_PRIOR:
            continue
        name = next(iter(aw.values()))["name"]
        span_weeks = max(1.0, ((cut - min(a["date"] for a in prior)).days + 1) / 7)
        row = {"idare": name, "type": typ, "recent_n": len(recent), "prior_n": len(prior), "changes": []}
        for key, label in (("non_open", "açık dışı usul payı"), ("p21b", "pazarlık 21/b payı"), ("istisna", "istisna payı")):
            a, b = _share(recent, key), _share(prior, key)
            if a is not None and b is not None and abs(a - b) >= SHARE_JUMP:
                row["changes"].append({"what": label, "recent": round(a, 3), "prior": round(b, 3)})
        weekly = len(prior) / span_weeks
        if weekly > 0 and (len(recent) / weekly >= VOLUME_RATIO or len(recent) / weekly <= 1 / VOLUME_RATIO):
            row["changes"].append({"what": "haftalık hacim", "recent": len(recent), "prior": round(weekly, 1)})
        pa = sum(a["parts"] for a in recent) / len(recent)
        pb = sum(a["parts"] for a in prior) / len(prior)
        if abs(pa - pb) >= 0.5:
            row["changes"].append({"what": "kayıt başına puan bileşeni", "recent": round(pa, 2), "prior": round(pb, 2)})
        if row["changes"]:
            shifts.append(row)
    shifts.sort(key=lambda r: (-len(r["changes"]), r["type"], r["idare"]))
    return {"as_of": as_of.isoformat(), "recent_days": RECENT_DAYS, "shifts": shifts,
            "note": "Log only. A shift means 'look here', not that anything is wrong."}


def _d1_line() -> str:
    try:
        from .sitegen import d1
        p = config.data_dir() / "d1-usage.json"
        used = json.loads(p.read_text(encoding="utf-8")).get("rows_written", 0) if p.is_file() else 0
        pct = 100 * used / d1.D1_DAILY_LIMIT
        warn = "  WARNING: over 80% of the free daily D1 limit" if pct >= 80 else ""
        return f"D1 rows written on the last deploy day: {used} ({pct:.0f}% of {d1.D1_DAILY_LIMIT}){warn}"
    except Exception as e:  # noqa: BLE001
        return f"D1 usage unavailable ({type(e).__name__})"


def weekly_path(as_of: date) -> Path:
    y, w, _ = as_of.isocalendar()
    return config.data_dir() / "logs" / f"drift-{y}-W{w:02d}.json"


def write_weekly(stored: list[StoredRecord], as_of: date | None = None, force: bool = False) -> Path | None:
    """Write this ISO week's summary once (returns None when it already exists and not forced)."""
    res = compute(stored, as_of)
    path = weekly_path(date.fromisoformat(res["as_of"]))
    if path.exists() and not force:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = [f"Drift summary as of {res['as_of']} (last {RECENT_DAYS} days vs each idare's own earlier history)",
             _d1_line(), f"{len(res['shifts'])} idare/type pairs with a shift", ""]
    for r in res["shifts"][:50]:
        lines.append(f"{r['idare']} [{r['type']}] recent n={r['recent_n']}, prior n={r['prior_n']}")
        for c in r["changes"]:
            lines.append(f"    {c['what']}: {c['recent']} (earlier {c['prior']})")
    path.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("drift summary written: %s (%d shifts)", path, len(res["shifts"]))
    return path
