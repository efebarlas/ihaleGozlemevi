"""İdare and Yüklenici dossier files for the site (M4; SPEC §6.1, §6.2).

`export/idare/<slug>.json` and `export/yuklenici/<slug>.json`. Facts only: a firm's file has no score, rank or rate
(SPEC §6.1), and natural-person yüklenicis get no file and appear only as PERSON_LABEL.
"""
from __future__ import annotations

import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from . import flags, indicators as ind, peers
from .keys import normalize_key
from .sitegen.persons import PERSON_LABEL, is_natural_person
from .slugs import SlugMap, tr_sort_key
from .store import StoredRecord

SCHEMA = 1
TOP_N = 10
ALL_HISTORY_DAYS = 36500

PROCEDURE_CATEGORIES = [
    {"code": "acik", "label": "Açık"},
    {"code": "pazarlik_21b", "label": "Pazarlık 21/b"},
    {"code": "pazarlik_diger", "label": "Pazarlık (diğer)"},
    {"code": "istisna_3g", "label": "İstisna 3/g"},
    {"code": "istisna_3e", "label": "İstisna 3/e"},
    {"code": "istisna_diger", "label": "İstisna (diğer)"},
    {"code": "diger", "label": "Diğer"},
]


def procedure_category(usul_code: str | None) -> str:
    if usul_code == "acik":
        return "acik"
    if usul_code == "pazarlik_21b":
        return "pazarlik_21b"
    if usul_code and usul_code.startswith("pazarlik"):
        return "pazarlik_diger"
    if usul_code == "istisna_3g":
        return "istisna_3g"
    if usul_code == "istisna_3e":
        return "istisna_3e"
    if usul_code and usul_code.startswith("istisna"):
        return "istisna_diger"
    return "diger"


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _money(m) -> dict | None:
    return None if m is None else {"amount": m.amount, "currency": m.currency}


def _try_amount(s: StoredRecord) -> float:
    b = s.record.sozlesme_bedeli
    return b.amount if s.record.confident("sozlesme_bedeli") and b.currency == "TRY" else 0.0


def _try_known(s: StoredRecord) -> bool:
    return s.record.confident("sozlesme_bedeli") and s.record.sozlesme_bedeli.currency == "TRY"


def _dedupe(recs: list[StoredRecord]) -> list[StoredRecord]:
    """Drop repeated (ikn, yüklenici key, bedel) rows so a duplicated award is counted once."""
    seen, out = set(), []
    for s in recs:
        k = flags._dedupe_key(s) if s.record.confident("ikn") else ("id", s.id)
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _tid(s: StoredRecord):
    r = s.record
    return (r.bulletin_type, r.ikn) if r.confident("ikn") else ("rec", s.id)


def _common_name(names: list[str]) -> str:
    c = Counter(names)
    top = max(c.values())
    return sorted(n for n, k in c.items() if k == top)[0]


def _iso_week(d: date) -> tuple[str, str]:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}", (d - timedelta(days=d.weekday())).isoformat()


def _sort_recs(recs):
    return sorted(recs, key=lambda s: (s.record.bulletin_date, s.record.bulletin_type, s.record.section,
                                       s.record.seq))


def build(stored: list[StoredRecord], out: Path, slug_map: SlugMap | None = None) -> tuple[list[dict], list[dict]]:
    """Write idare/ and yuklenici/ files under `out`; return (idare_index, yuklenici_index) for meta.json."""
    slug_map = slug_map or SlugMap()
    by_idare: dict[str, list[StoredRecord]] = defaultdict(list)
    by_yuk: dict[str, list[StoredRecord]] = defaultdict(list)
    idare_names: dict[str, list[str]] = defaultdict(list)
    yuk_names: dict[str, list[str]] = defaultdict(list)
    for s in stored:
        r = s.record
        ik = normalize_key(r.idare) if r.confident("idare") else None
        yk = normalize_key(r.yuklenici) if r.confident("yuklenici") else None
        if ik:
            by_idare[ik].append(s)
            idare_names[ik].append(r.idare)
        if yk:
            by_yuk[yk].append(s)
            yuk_names[yk].append(r.yuklenici)

    idare_name = {k: _common_name(v) for k, v in idare_names.items()}
    yuk_name = {k: _common_name(v) for k, v in yuk_names.items()}
    person_keys = {k for k, n in yuk_name.items() if is_natural_person(n)}
    yuk_keys = [k for k in by_yuk if k not in person_keys]

    slug_map.issue_all("idare", by_idare)
    slug_map.issue_all("yuklenici", yuk_keys)
    slug_map.save()
    islug = lambda k: slug_map.slug("idare", k)          # noqa: E731
    yslug = lambda k: slug_map.slug("yuklenici", k)      # noqa: E731

    # tek-geçerli shares per usul group over the whole stored history, beside the peer group's
    kg = flags.kisim_groups(stored)
    tenders = flags._tenders(stored, kg)
    latest = max((s.record.bulletin_date for s in stored), default=None)
    groups_of: dict[str, set] = defaultdict(set)
    for typ, ts in tenders.items():
        for t in ts:
            if t.usul and t.tek is not None:
                groups_of[t.idare_key].add((typ, t.usul))
    windows: dict[tuple, flags._Window] = {}

    def window(typ, usul):
        if (typ, usul) not in windows:
            windows[(typ, usul)] = flags._Window(tenders.get(typ, []), latest, usul, days=ALL_HISTORY_DAYS)
        return windows[(typ, usul)]

    def display_yuk(s: StoredRecord) -> tuple[str | None, str | None]:
        r = s.record
        if not r.confident("yuklenici"):
            return None, None
        yk = normalize_key(r.yuklenici)
        if not yk:
            return None, None
        if yk in person_keys:
            return PERSON_LABEL, None
        return r.yuklenici, yslug(yk)

    idare_index, written = [], {"idare": set(), "yuklenici": set()}
    for ik in sorted(by_idare):
        recs = _sort_recs(by_idare[ik])
        name = idare_name[ik]
        dd = _dedupe(recs)
        totals = {}
        for typ in sorted({s.record.bulletin_type for s in recs}):
            tr = [s for s in dd if s.record.bulletin_type == typ]
            vals = [_try_amount(s) for s in tr if _try_known(s)]
            totals[typ] = {"records": sum(1 for s in recs if s.record.bulletin_type == typ),
                           "awards": len({_tid(s) for s in recs if s.record.bulletin_type == typ}),
                           "try_total": round(sum(vals), 2),
                           "median_bedel_try": round(statistics.median(vals), 2) if vals else None}

        weeks: dict[str, dict] = {}
        week_awards: dict[tuple, set] = defaultdict(set)
        for s in dd:
            r = s.record
            code = ind.usul_turu(r.ihale_usulu) if r.confident("ihale_usulu") else None
            cat = procedure_category(code)
            wk, start = _iso_week(r.bulletin_date)
            w = weeks.setdefault(wk, {"week": wk, "start": start, "counts": {}, "try": {}})
            week_awards[(wk, cat)].add(_tid(s))
            w["try"][cat] = round(w["try"].get(cat, 0.0) + _try_amount(s), 2)
        for (wk, cat), tids in week_awards.items():
            weeks[wk]["counts"][cat] = len(tids)
        procedure_mix = [weeks[k] for k in sorted(weeks)]

        shares = []
        for typ, usul in sorted(groups_of.get(ik, ())):
            stats, _ = flags.idare_stats(window(typ, usul), name, typ, usul)
            shares.append({"group": f"{typ}/{usul}", "type": typ, "usul_turu": usul,
                           "label": stats["usul_label"], "records": stats["records"],
                           "tek_gecerli_teklif": stats["tek_gecerli_teklif"], "peer": stats["peer"]})

        timeline = []
        for s in recs:
            r = s.record
            yname, yslug_ = display_yuk(s)
            timeline.append({
                "id": f"{r.bulletin_date.isoformat()}-{r.bulletin_type}-{r.section}-{r.seq}",
                "date": r.bulletin_date.isoformat(), "type": r.bulletin_type, "konu": r.konu or r.title,
                "yuklenici": yname, "yuklenici_slug": yslug_, "bedel": _money(r.sozlesme_bedeli),
                "flags": [f["code"] for f in (s.flags or [])], "score": s.score or 0.0})

        agg: dict[str, dict] = {}
        person_awards = set()
        for s in dd:
            r = s.record
            if not r.confident("yuklenici"):
                continue
            yk = normalize_key(r.yuklenici)
            if not yk:
                continue
            if yk in person_keys:
                person_awards.add(_tid(s))
                continue
            a = agg.setdefault(yk, {"awards": set(), "try": 0.0})
            a["awards"].add(_tid(s))
            a["try"] += _try_amount(s)
        rows = [{"name": yuk_name[k], "slug": yslug(k), "count": len(a["awards"]), "try_total": round(a["try"], 2)}
                for k, a in agg.items()]
        top_count = sorted(rows, key=lambda x: (-x["count"], -x["try_total"], x["name"]))[:TOP_N]
        top_try = sorted(rows, key=lambda x: (-x["try_total"], -x["count"], x["name"]))[:TOP_N]

        slug = islug(ik)
        _write(out / "idare" / f"{slug}.json", {
            "schema": SCHEMA, "slug": slug, "name": name, "key": ik,
            "idare_turu": peers.idare_turu(name), "il": peers.il_of(name),
            "totals": totals, "procedure_categories": PROCEDURE_CATEGORIES, "procedure_mix": procedure_mix,
            "tek_gecerli_by_group": shares, "timeline": timeline,
            "top_yuklenici_by_count": top_count, "top_yuklenici_by_try": top_try,
            "natural_person_awards": len(person_awards)})
        written["idare"].add(slug)
        idare_index.append({"slug": slug, "name": name, "records": len(recs)})

    yuk_index = []
    for yk in sorted(yuk_keys):
        recs = _sort_recs(by_yuk[yk])
        per_idare: dict[str, dict] = {}
        awards = []
        for s in recs:
            r = s.record
            ik = normalize_key(r.idare) if r.confident("idare") else None
            awards.append({
                "id": f"{r.bulletin_date.isoformat()}-{r.bulletin_type}-{r.section}-{r.seq}",
                "date": r.bulletin_date.isoformat(), "type": r.bulletin_type,
                "idare": {"name": r.idare if ik else None, "slug": islug(ik) if ik else None},
                "konu": r.konu or r.title, "bedel": _money(r.sozlesme_bedeli), "usul": r.ihale_usulu})
        for s in _dedupe(recs):
            r = s.record
            ik = normalize_key(r.idare) if r.confident("idare") else None
            if not ik:
                continue
            a = per_idare.setdefault(ik, {"awards": set(), "try": 0.0})
            a["awards"].add(_tid(s))
            a["try"] += _try_amount(s)
        totals = sorted(({"idare": idare_name[k], "slug": islug(k), "count": len(a["awards"]),
                          "try_total": round(a["try"], 2)} for k, a in per_idare.items()),
                        key=lambda x: (-x["count"], -x["try_total"], x["idare"]))
        slug = yslug(yk)
        _write(out / "yuklenici" / f"{slug}.json", {
            "schema": SCHEMA, "slug": slug, "name": yuk_name[yk], "key": yk,
            "awards": awards, "totals_per_idare": totals})
        written["yuklenici"].add(slug)
        yuk_index.append({"slug": slug, "name": yuk_name[yk], "records": len(recs)})

    for kind in ("idare", "yuklenici"):       # drop files of slugs that no longer have data
        d = out / kind
        if d.exists():
            for p in d.glob("*.json"):
                if p.stem not in written[kind]:
                    p.unlink()
    idare_index.sort(key=lambda x: tr_sort_key(x["name"]))
    yuk_index.sort(key=lambda x: tr_sort_key(x["name"]))
    return idare_index, yuk_index
