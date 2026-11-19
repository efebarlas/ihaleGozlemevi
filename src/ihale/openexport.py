"""Open-standard exports, private until G-Public (SPEC §1 "Borrowed from abroad").

* OCDS 1.1 release package per bulletin day: `<data>/exports/ocds/<date>.json`
* FollowTheMoney entities per bulletin day:   `<data>/exports/ftm/<date>.ijson`

Both are NEVER deployed: they live outside `export/` (the site's only input) and nothing in `site/` refers to them.
Persons stay as printed here, because the export is private (the public site masks them; SPEC §6.1).

Dependencies: none beyond the standard library. `ocdskit` is not used because its dependency chain pulls in `requests`
and `certifi` (MPL-2.0), which the license gate forbids; `followthemoney` is not used because it needs PyICU, which does
not build here. Tests validate against the vendored OCDS 1.1.5 JSON Schema and the FtM schema property list.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from . import config, indicators as ind
from .export import istanbul_now
from .keys import normalize_key
from .sitegen.persons import is_natural_person
from .store import Store, StoredRecord

# Placeholder: a registered OCDS prefix is a G-Public item (request one from OCP before publishing).
OCID_PREFIX = "ocds-ihalegoz"
EKAP_URL = "https://ekap.kik.gov.tr/EKAP/Ilan/BultenIndirme.aspx"
BID_EXTENSION = "https://raw.githubusercontent.com/open-contracting-extensions/ocds_bid_extension/v1.1.5/extension.json"
TYPE_LABEL = {"mal": "Mal", "hizmet": "Hizmet", "yapim": "Yapım"}
CATEGORY = {"mal": "goods", "hizmet": "services", "yapim": "works"}
FTM_TYPE = {"mal": "U", "hizmet": "S", "yapim": "W"}      # TED-style contract type letters
METHOD = {"acik": "open", "belli_istekliler": "selective", "dogrudan_temin": "direct"}   # pazarlık/istisna → limited


def exports_dir() -> Path:
    return config.data_dir() / "exports"


def _hash(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _dt(d: date) -> str:
    return f"{d.isoformat()}T00:00:00+03:00"


def record_id(r) -> str:
    return f"{r.bulletin_date.isoformat()}-{r.bulletin_type}-{r.section}-{r.seq}"


def source_title(r) -> str:
    return (f"Kamu İhale Bülteni, {r.bulletin_date:%d.%m.%Y}, {TYPE_LABEL.get(r.bulletin_type, r.bulletin_type)} – "
            f"Sonuç İlanları, s. {r.page_start}")


def _ocid(s: StoredRecord) -> str:
    r = s.record
    ident = r.ikn.replace("/", "-") if r.confident("ikn") else f"rec-{record_id(r)}"
    return f"{OCID_PREFIX}-{ident}"


def _money(m) -> dict:
    return {"amount": m.amount, "currency": m.currency}


def _parties(r) -> tuple[dict | None, dict | None]:
    buyer = supplier = None
    if r.confident("idare") and normalize_key(r.idare):
        buyer = {"id": f"ihalegoz-idare-{_hash(normalize_key(r.idare))}", "name": r.idare}
    if r.confident("yuklenici") and normalize_key(r.yuklenici):
        supplier = {"id": f"ihalegoz-yuklenici-{_hash(normalize_key(r.yuklenici))}", "name": r.yuklenici}
    return buyer, supplier


def _period(text: str | None) -> dict | None:
    m = re.fullmatch(r"\s*(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(\d{2})\.(\d{2})\.(\d{4})\s*", text or "")
    if not m:
        return None
    try:
        a = date(int(m[3]), int(m[2]), int(m[1]))
        b = date(int(m[6]), int(m[5]), int(m[4]))
    except ValueError:
        return None
    return {"startDate": _dt(a), "endDate": _dt(b)} if a <= b else None


def _release(day: date, recs: list[StoredRecord]) -> dict:
    first = recs[0].record
    ocid = _ocid(recs[0])
    parties: dict[str, dict] = {}
    awards, contracts = [], []
    for s in recs:
        r = s.record
        buyer, supplier = _parties(r)
        if buyer:
            parties.setdefault(buyer["id"], {**buyer, "roles": ["buyer", "procuringEntity"]})
        if supplier:
            parties.setdefault(supplier["id"], {**supplier, "roles": ["supplier"]})
        rid = record_id(r)
        doc = {"id": f"{rid}-bulten", "documentType": "awardNotice", "title": source_title(r),
               "description": f"{source_title(r)}; kayıt {rid}; PDF'yi EKAP Bülten İndirme sayfasından indirin.",
               "url": EKAP_URL, "format": "application/pdf", "language": "tr",
               "datePublished": _dt(r.bulletin_date)}
        award = {"id": rid, "status": "active", "documents": [doc]}
        if r.confident("sozlesme_tarihi"):
            award["date"] = _dt(r.sozlesme_tarihi)
        if r.confident("sozlesme_bedeli"):
            award["value"] = _money(r.sozlesme_bedeli)
        if supplier:
            award["suppliers"] = [dict(supplier)]
        awards.append(award)
        contract = {"id": rid, "awardID": rid, "status": "active"}
        if r.confident("sozlesme_tarihi"):
            contract["dateSigned"] = _dt(r.sozlesme_tarihi)
        if r.confident("sozlesme_bedeli"):
            contract["value"] = _money(r.sozlesme_bedeli)
        period = _period(r.sozlesme_suresi) if r.confident("sozlesme_suresi") else None
        if period:
            contract["period"] = period
        contracts.append(contract)

    tender: dict = {"id": first.ikn if first.confident("ikn") else record_id(first), "status": "complete",
                    "mainProcurementCategory": CATEGORY.get(first.bulletin_type)}
    if first.confident("title"):
        tender["title"] = first.title
    if first.confident("konu"):
        tender["description"] = first.konu
    buyer, _ = _parties(first)
    if buyer:
        tender["procuringEntity"] = dict(buyer)
    code = ind.usul_turu(first.ihale_usulu) if first.confident("ihale_usulu") else None
    if first.confident("ihale_usulu"):
        tender["procurementMethodDetails"] = first.ihale_usulu          # verbatim
    if code and code.startswith("dogrudan_temin"):
        method = "direct"
    else:
        method = METHOD.get(code) or ("limited" if code and code != "diger" else None)
    if method:
        tender["procurementMethod"] = method                            # the schema's codelist is closed
    if first.confident("toplam_teklif"):
        tender["numberOfTenderers"] = first.toplam_teklif
    est = first.esas_kisim_yaklasik_maliyet if first.confident("esas_kisim_yaklasik_maliyet") else None
    est = est or (first.yaklasik_maliyet if first.confident("yaklasik_maliyet") else None)
    if est:
        tender["value"] = _money(est)
    if first.confident("ihale_tarihi"):
        tender["tenderPeriod"] = {"endDate": _dt(first.ihale_tarihi)}
    tender = {k: v for k, v in tender.items() if v is not None}

    release: dict = {"ocid": ocid, "id": f"{ocid}-{day.isoformat()}", "date": _dt(day), "tag": ["award", "contract"],
                     "initiationType": "tender", "language": "tr", "parties": list(parties.values()),
                     "tender": tender, "awards": awards, "contracts": contracts}
    if buyer:
        release["buyer"] = dict(buyer)
    if first.confident("toplam_teklif") and first.confident("gecerli_teklif"):
        t, g = first.toplam_teklif, first.gecerli_teklif
        release["bids"] = {"statistics": [        # bid statistics extension: the count of valid bids
            {"id": "1", "measure": "bids", "value": t},
            {"id": "2", "measure": "validBids", "value": g},
            {"id": "3", "measure": "disqualifiedBids", "value": max(t - g, 0)}]}
    return release


def _group_by_tender(records: list[StoredRecord]) -> list[list[StoredRecord]]:
    groups: dict = {}
    for s in records:
        r = s.record
        key = (r.bulletin_type, r.ikn) if r.confident("ikn") else ("rec", record_id(r))
        groups.setdefault(key, []).append(s)
    return list(groups.values())


def ocds_package(day: date, records: list[StoredRecord], now: datetime | None = None) -> dict | None:
    """OCDS 1.1 release package for one bulletin day, or None when the day has no records."""
    if not records:
        return None
    releases = [_release(day, g) for g in _group_by_tender(records)]
    return {
        "uri": f"urn:ihalegozlemevi:ocds:{day.isoformat()}",
        "version": "1.1",
        "extensions": [BID_EXTENSION],
        "publishedDate": (now or istanbul_now()).isoformat(timespec="seconds"),
        "publisher": {"name": "İhale Gözlemevi (özel dışa aktarım)", "uri": "https://github.com/efebarlas/ihaleGozlemevi"},
        "releases": releases,
    }


# ---------------------------------------------------------------- FollowTheMoney
def _ent(id_: str, schema: str, **props) -> dict:
    return {"id": id_, "schema": schema,
            "properties": {k: [str(x) for x in (v if isinstance(v, list) else [v])] for k, v in props.items()
                           if v not in (None, "", [])}}


_COMPANY_FORM = re.compile(r"\b(ltd|as|ort|koll|kom)\b|şirket|sirket|ortak girişim|kooperatif|birliği|holding|limited|anonim")


def _is_company(name: str) -> bool:
    return bool(_COMPANY_FORM.search(normalize_key(name) or ""))


def ftm_entities(records: list[StoredRecord]) -> list[dict]:
    """FollowTheMoney entities (PublicBody, Company/LegalEntity, Person, Contract, ContractAward), sorted by schema, id."""
    ents: dict[str, dict] = {}
    for group in _group_by_tender(records):
        first = group[0].record
        cid = f"ihalegoz-ihale-{_hash(_ocid(group[0]))}"
        buyer, _ = _parties(first)
        amounts = [s.record.sozlesme_bedeli for s in group if s.record.confident("sozlesme_bedeli")]
        cur = {m.currency for m in amounts}
        total = sum(m.kurus for m in amounts) / 100 if len(cur) == 1 else None
        dates = [s.record.sozlesme_tarihi for s in group if s.record.confident("sozlesme_tarihi")]
        if buyer:
            ents[buyer["id"]] = _ent(buyer["id"], "PublicBody", name=buyer["name"], country="tr",
                                     publisher="Kamu İhale Bülteni (EKAP)")
        ents[cid] = _ent(
            cid, "Contract", title=first.title if first.confident("title") else first.konu or first.ikn,
            description=first.konu if first.confident("konu") else None,
            authority=buyer["id"] if buyer else None, type=FTM_TYPE.get(first.bulletin_type),
            contractDate=min(dates).isoformat() if dates else None,
            procedureNumber=first.ikn if first.confident("ikn") else None,
            procedure=first.ihale_usulu if first.confident("ihale_usulu") else None,
            method=ind.usul_turu(first.ihale_usulu) if first.confident("ihale_usulu") else None,
            numberAwards=len(group), status="awarded", language="tr",
            amount=f"{total:.2f}" if total is not None else None, currency=next(iter(cur)) if len(cur) == 1 else None,
            notes=source_title(first), sourceUrl=EKAP_URL, publisher="Kamu İhale Bülteni (EKAP)")
        for s in group:
            r = s.record
            _, sup = _parties(r)
            if not sup:
                continue
            if sup["id"] not in ents:
                schema = ("Person" if is_natural_person(sup["name"])
                          else "Company" if _is_company(sup["name"]) else "LegalEntity")
                ents[sup["id"]] = _ent(sup["id"], schema, name=sup["name"], country="tr",
                                       publisher="Kamu İhale Bülteni (EKAP)")
            rid = record_id(r)
            bids = (f"Toplam teklif: {r.toplam_teklif}; geçerli teklif: {r.gecerli_teklif}"
                    if r.confident("toplam_teklif") and r.confident("gecerli_teklif") else None)
            ents[f"ihalegoz-ihale-ilan-{_hash(rid)}"] = _ent(
                f"ihalegoz-ihale-ilan-{_hash(rid)}", "ContractAward", contract=cid, supplier=sup["id"],
                amount=f"{r.sozlesme_bedeli.amount:.2f}" if r.confident("sozlesme_bedeli") else None,
                currency=r.sozlesme_bedeli.currency if r.confident("sozlesme_bedeli") else None,
                lotNumber=r.seq, documentNumber=r.ikn if r.confident("ikn") else None,
                documentType="Sonuç ilanı", summary=bids,
                date=r.sozlesme_tarihi.isoformat() if r.confident("sozlesme_tarihi") else None,
                recordId=rid, sourceUrl=EKAP_URL, publisher="Kamu İhale Bülteni (EKAP)", role="supplier")
    order = {"PublicBody": 0, "Company": 1, "LegalEntity": 1, "Person": 2, "Contract": 3, "ContractAward": 4}
    return sorted(ents.values(), key=lambda e: (order[e["schema"]], e["id"]))


# ---------------------------------------------------------------- writing
def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def export_open(store: Store | None = None, days: list[date] | None = None, out: Path | None = None,
                now: datetime | None = None) -> list[Path]:
    """Write OCDS + FtM files for `days` (default: the latest stored day). Returns the written paths."""
    store = store or Store()
    out = Path(out) if out else exports_dir()
    all_records = store.all_records()
    by_day: dict[date, list[StoredRecord]] = {}
    for s in all_records:
        by_day.setdefault(s.record.bulletin_date, []).append(s)
    if days is None:
        days = [max(by_day)] if by_day else []
    written = []
    for day in sorted(days):
        recs = by_day.get(day, [])
        pkg = ocds_package(day, recs, now)
        if pkg is None:
            continue
        p = out / "ocds" / f"{day.isoformat()}.json"
        _atomic(p, json.dumps(pkg, ensure_ascii=False, indent=1) + "\n")
        written.append(p)
        q = out / "ftm" / f"{day.isoformat()}.ijson"
        _atomic(q, "".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in ftm_entities(recs)))
        written.append(q)
    return written
