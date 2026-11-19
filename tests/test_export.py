import json
from datetime import date, datetime

from ihale import config
from ihale.export import TR_TZ, export_all
from ihale.flags import compute_flags
from ihale.model import Money
from ihale.store import Store

from rec_helpers import rec

# Verbatim from docs/data-contract.md §5 (shape only is compared).
CONTRACT_META = json.loads("""
{"schema": 1, "generated_at": "2026-11-18T21:30:00+03:00", "latest_date": "2026-11-18",
 "dates": ["2026-11-18", "2026-11-17"],
 "counts": {"2026-11-18": {"records": 626, "flagged": 240, "tek_gecerli_teklif": 200, "bedel_orani": 60, "tekrarlayan_yuklenici": 5, "unreadable": 4}}}
""")
CONTRACT_DAY = json.loads("""
{"schema": 1, "date": "2026-11-18", "types": ["mal"],
 "tenders": [
  {"id": "2026-11-18-mal-A-3",
   "ikn": "2026/1766844", "title": "17 KALEM TEMİZLİK MALZEMESİ ALIMI", "konu": "17 Kalem Temizlik Malzemesi Alımı",
   "type": "mal", "section": "A", "usul": "Açık", "tur": "Mal alımı",
   "idare": {"name": "ANTALYA İL SAĞLIK", "key": "antalya il sağlık"},
   "yuklenici": {"name": "Emir Limited Şirketi", "key": "emir ltd"},
   "ihale_tarihi": "2026-10-21", "sozlesme_tarihi": "2026-11-16", "sozlesme_suresi": "16.11.2026 - 31.12.2026",
   "yaklasik_maliyet": {"amount": 2894258.50, "currency": "TRY"},
   "esas_kisim_yaklasik_maliyet": null,
   "sozlesme_bedeli": {"amount": 2767200.00, "currency": "TRY"},
   "toplam_teklif": 2, "gecerli_teklif": 2,
   "kisim": {"records_in_ikn": 1},
   "source": {"date": "2026-11-18", "type": "mal", "file": "BULTEN_18112026_MAL_SONUC.pdf", "page": 18},
   "unreadable": [],
   "flags": [{"code": "bedel_orani", "value": 0.956, "text": "Sözleşme bedeli yaklaşık maliyetin %95'i"}]}
 ]}
""")


def shape(x):
    """Recursive key structure; scalars collapse to their kind (null/number/string distinguished loosely)."""
    if isinstance(x, dict):
        return {k: shape(v) for k, v in x.items()}
    if isinstance(x, list):
        return [shape(x[0])] if x else []
    return None


def load_all(day=date(2026, 11, 18)):
    store = Store()
    stored = store.all_records()
    res = compute_flags(stored)
    store.set_flags({i: (r.flags, r.unreadable, r.kisim_n) for i, r in res.items()})
    return store


def exported(out):
    return (json.loads((out / "meta.json").read_text(encoding="utf-8")),
            lambda d: json.loads((out / "days" / f"{d}.json").read_text(encoding="utf-8")))


def test_export_matches_contract_shape():
    r = rec(3, ikn="2026/1766844", idare="ANTALYA İL SAĞLIK", yuklenici="Emir Limited Şirketi",
            bedel=2767200.0, maliyet=2894258.5, toplam=2, gecerli=2)
    r.title, r.konu = "17 KALEM TEMİZLİK MALZEMESİ ALIMI", "17 Kalem Temizlik Malzemesi Alımı"
    Store().replace_day(date(2026, 11, 18), "mal", [r])
    store = load_all()
    out = export_all(store, now=datetime(2026, 11, 18, 21, 30, tzinfo=TR_TZ))
    meta, day = exported(out)
    assert out == config.data_dir() / "export"
    d = day("2026-11-18")
    # shape: every key of the contract example, nothing else (flags/unreadable lists compared by element shape)
    assert shape(d) == shape(CONTRACT_DAY)
    assert shape(meta)["counts"]["2026-11-18"].keys() == shape(CONTRACT_META)["counts"]["2026-11-18"].keys()
    assert set(meta) == set(CONTRACT_META)
    t = d["tenders"][0]
    expected = CONTRACT_DAY["tenders"][0]
    expected["flags"][0]["value"] = t["flags"][0]["value"]
    assert t == expected
    assert meta["generated_at"] == "2026-11-18T21:30:00+03:00"
    assert meta["latest_date"] == "2026-11-18" and meta["dates"] == ["2026-11-18"]
    assert meta["counts"]["2026-11-18"] == {"records": 1, "flagged": 1, "tek_gecerli_teklif": 0, "bedel_orani": 1,
                                            "tekrarlayan_yuklenici": 0, "unreadable": 0}


def test_every_record_included_flagged_or_not_and_ids():
    Store().replace_day(date(2026, 11, 18), "mal", [
        rec(1, ikn="2026/1", gecerli=1, toplam=1),
        rec(2, ikn="2026/2", yuklenici="B"),
        rec(1, ikn="2026/3", yuklenici="C", section="B", conf={"gecerli_teklif": 0.1})])
    out = export_all(load_all())
    meta, day = exported(out)
    ts = day("2026-11-18")["tenders"]
    assert [t["id"] for t in ts] == ["2026-11-18-mal-A-1", "2026-11-18-mal-A-2", "2026-11-18-mal-B-1"]
    assert [bool(t["flags"]) for t in ts] == [True, False, False]
    assert "gecerli_teklif" in ts[2]["unreadable"]
    assert meta["counts"]["2026-11-18"]["records"] == 3 and meta["counts"]["2026-11-18"]["unreadable"] == 1
    assert meta["counts"]["2026-11-18"]["flagged"] == 1


def test_dates_descending_types_and_stale_day_removed():
    s = Store()
    s.replace_day(date(2026, 11, 17), "mal", [rec(1, day=date(2026, 11, 17))])
    s.replace_day(date(2026, 11, 18), "mal", [rec(1)])
    s.replace_day(date(2026, 11, 18), "hizmet", [rec(1, type_="hizmet", ikn="2026/7")])
    out = export_all(load_all())
    meta, day = exported(out)
    assert meta["dates"] == ["2026-11-18", "2026-11-17"] and meta["latest_date"] == "2026-11-18"
    assert day("2026-11-18")["types"] == ["hizmet", "mal"]
    s.replace_day(date(2026, 11, 17), "mal", [])
    export_all(load_all())
    assert not (out / "days" / "2026-11-17.json").exists()


def test_unicode_not_escaped_and_money_alt():
    r = rec(1, idare="ŞANLIURFA İL ÖZEL İDARESİ")
    r.yaklasik_maliyet = Money(4740750000, "TRY", Money(107247500, "EUR"))
    Store().replace_day(date(2026, 11, 18), "mal", [r])
    out = export_all(load_all())
    raw = (out / "days" / "2026-11-18.json").read_text(encoding="utf-8")
    assert "ŞANLIURFA İL ÖZEL İDARESİ" in raw and chr(92) + "u" not in raw
    t = json.loads(raw)["tenders"][0]
    assert t["yaklasik_maliyet"] == {"amount": 47407500.0, "currency": "TRY",
                                     "alt": {"amount": 1072475.0, "currency": "EUR"}}


def test_empty_store_exports_empty_meta():
    out = export_all(Store())
    meta, _ = exported(out)
    assert meta["dates"] == [] and meta["latest_date"] is None and meta["counts"] == {}


def test_reason_objects_survive_export():
    r = rec(1, maliyet=100.0)
    r.sozlesme_bedeli = Money(15405000, "EUR")
    Store().replace_day(date(2026, 11, 18), "mal", [r])
    out = export_all(load_all())
    t = exported(out)[1]("2026-11-18")["tenders"][0]
    assert {"field": "sozlesme_bedeli", "reason": "para birimi farklı"} in t["unreadable"]
