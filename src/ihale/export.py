"""Export to JSON for the site (docs/data-contract.md §5): <data>/export/meta.json and days/<date>.json."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config
from .keys import normalize_key
from .model import Money
from .store import Store, StoredRecord

SCHEMA = 1
TR_TZ = timezone(timedelta(hours=3))   # Turkey is on permanent UTC+3 (no tzdata needed on Windows)
FLAG_CODES = ("tek_gecerli_teklif", "bedel_orani", "tekrarlayan_yuklenici")


def istanbul_now() -> datetime:
    return datetime.now(TR_TZ)


def export_dir() -> Path:
    return config.data_dir() / "export"


def _money(m: Money | None) -> dict | None:
    if m is None:
        return None
    out = {"amount": m.amount, "currency": m.currency}
    if m.alt is not None:
        out["alt"] = {"amount": m.alt.amount, "currency": m.alt.currency}
    return out


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def tender_json(s: StoredRecord) -> dict:
    r = s.record
    day = r.bulletin_date.isoformat()
    return {
        "id": f"{day}-{r.bulletin_type}-{r.section}-{r.seq}",
        "ikn": r.ikn, "title": r.title, "konu": r.konu,
        "type": r.bulletin_type, "section": r.section, "usul": r.ihale_usulu, "tur": r.ihale_turu,
        "idare": {"name": r.idare, "key": normalize_key(r.idare)},
        "yuklenici": {"name": r.yuklenici, "key": normalize_key(r.yuklenici)},
        "ihale_tarihi": _iso(r.ihale_tarihi), "sozlesme_tarihi": _iso(r.sozlesme_tarihi),
        "sozlesme_suresi": r.sozlesme_suresi,
        "yaklasik_maliyet": _money(r.yaklasik_maliyet),
        "esas_kisim_yaklasik_maliyet": _money(r.esas_kisim_yaklasik_maliyet),
        "sozlesme_bedeli": _money(r.sozlesme_bedeli),
        "toplam_teklif": r.toplam_teklif, "gecerli_teklif": r.gecerli_teklif,
        "kisim": {"records_in_ikn": s.kisim_n or 1},
        "source": {"date": day, "type": r.bulletin_type, "file": r.source_file, "page": r.page_start},
        "unreadable": s.unreadable or [],
        "flags": s.flags or [],
        "score": s.score or 0, "score_parts": s.score_parts or [],
        "idare_stats": s.idare_stats,
    }


def _write_json(path: Path, obj) -> None:
    """Atomic: a half-written file must never be built or deployed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def export_all(store: Store | None = None, out: Path | None = None, now: datetime | None = None) -> Path:
    """Write meta.json and one days/<date>.json per stored date. Flags must have been computed (`flag`)."""
    store = store or Store()
    out = Path(out) if out else export_dir()
    by_day: dict[str, list[StoredRecord]] = {}
    for s in store.all_records():   # ordered by date, type, section, seq
        by_day.setdefault(s.record.bulletin_date.isoformat(), []).append(s)

    counts = {}
    for day, recs in by_day.items():
        tenders = [tender_json(s) for s in recs]
        _write_json(out / "days" / f"{day}.json", {
            "schema": SCHEMA, "date": day,
            "types": sorted({t["type"] for t in tenders}), "tenders": tenders})
        c = {"records": len(tenders), "flagged": sum(1 for t in tenders if t["flags"])}
        for code in FLAG_CODES:
            c[code] = sum(1 for t in tenders if any(f["code"] == code for f in t["flags"]))
        c["unreadable"] = sum(1 for t in tenders if t["unreadable"])
        counts[day] = c

    # drop day files for dates no longer stored
    days_dir = out / "days"
    if days_dir.exists():
        for p in days_dir.glob("*.json"):
            if p.stem not in by_day:
                p.unlink()

    dates = sorted(by_day, reverse=True)
    _write_json(out / "meta.json", {
        "schema": SCHEMA, "generated_at": (now or istanbul_now()).isoformat(timespec="seconds"),
        "latest_date": dates[0] if dates else None, "dates": dates, "counts": counts})
    return out
