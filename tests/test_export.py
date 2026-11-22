import json
from datetime import date, datetime

from ihale import config
from ihale.export import TR_TZ, export_all
from ihale.flags import compute_flags_full
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
   "sozlesme_bedeli": {"amount": 2825000.00, "currency": "TRY"},
   "toplam_teklif": 2, "gecerli_teklif": 2,
   "kisim": {"records_in_ikn": 1},
   "source": {"date": "2026-11-18", "type": "mal", "file": "BULTEN_18112026_MAL_SONUC.pdf", "page": 18},
   "unreadable": [],
   "flags": [{"code": "bedel_orani", "value": 0.976, "text": "Sözleşme bedeli yaklaşık maliyetin %97'si"}],
   "score": 2.5, "score_parts": [{"code": "bedel_orani", "points": 2.5, "p": 0.08, "p_group": "mal/acik", "k": 8, "n": 100, "p_source": "group"}],
   "indicators": {"elenen_orani": 0.0, "elenen_orani_peer": 0.18, "karar_suresi_gun": 26, "usul_turu": "acik", "acik_olmayan": false,
                  "yuklenici_payi": 0.12, "yuklenici_payi_n": 12},
   "idare_stats": {"records": 12, "tek_gecerli_teklif": 0.80, "window_days": 30, "idare_turu": "sağlık", "il": "Antalya",
                   "peer": {"label": "Antalya'daki sağlık idareleri (mal)", "records": 140, "tek_gecerli_teklif": 0.43}}}
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
    res, rates = compute_flags_full(stored)
    store.set_meta("part_rates", rates)
    store.set_flags({i: {"flags": r.flags, "unreadable": r.unreadable, "kisim_n": r.kisim_n, "score": r.score,
                         "score_parts": r.score_parts, "idare_stats": r.idare_stats,
                         "indicators": r.indicators, "structural": r.structural,
                         "score_raw": r.score_raw, "value_weight": r.value_weight} for i, r in res.items()})
    return store


def exported(out):
    return (json.loads((out / "meta.json").read_text(encoding="utf-8")),
            lambda d: json.loads((out / "days" / f"{d}.json").read_text(encoding="utf-8")))


def test_export_matches_contract_shape():
    r = rec(3, ikn="2026/1766844", idare="ANTALYA İL SAĞLIK", yuklenici="Emir Limited Şirketi",
            bedel=2825000.0, maliyet=2894258.5, toplam=2, gecerli=2)
    r.title, r.konu = "17 KALEM TEMİZLİK MALZEMESİ ALIMI", "17 Kalem Temizlik Malzemesi Alımı"
    Store().replace_day(date(2026, 11, 18), "mal", [r])
    store = load_all()
    out = export_all(store, now=datetime(2026, 11, 18, 21, 30, tzinfo=TR_TZ))
    meta, day = exported(out)
    assert out == config.data_dir() / "export"
    d = day("2026-11-18")
    # shape: every key of the contract example, nothing else (flags/unreadable lists compared by element shape)
    # idare_stats: a lone record has no peer group, so compare that block's keys separately
    stats, c_stats = d["tenders"][0].pop("idare_stats"), CONTRACT_DAY["tenders"][0].pop("idare_stats")
    assert d["tenders"][0].pop("structural") is None            # §4.1.1: null unless a rule matches
    assert {"score_raw", "value_weight"} <= set(d["tenders"][0])        # §4.1 materiality weight: score = raw x w
    d["tenders"][0].pop("score_raw"), d["tenders"][0].pop("value_weight")
    assert d["tenders"][0]["idare"].pop("parent") is None            # no alias matches this idare
    sc, sp = d["tenders"][0].pop("score"), d["tenders"][0].pop("score_parts")
    c_sc, c_sp = CONTRACT_DAY["tenders"][0].pop("score"), CONTRACT_DAY["tenders"][0].pop("score_parts")
    assert isinstance(sc, float) and set(sp[0]) == set(c_sp[0]) == {"code", "points", "p", "p_group", "k", "n", "p_source"}
    assert [x["code"] for x in sp] == ["bedel_orani"]
    indic, c_indic = d["tenders"][0].pop("indicators"), CONTRACT_DAY["tenders"][0].pop("indicators")
    assert shape(d) == shape(CONTRACT_DAY)
    assert set(indic) == set(c_indic) | {"elenen_orani_peer_n", "bedel_orani", "bedel_orani_peer_median", "source_check", "pazarlik_21b", "downloader_bid_ratio",
                                         "bedel_orani_peer_n"}     # added for display of n and of the real value
    assert indic.pop("bedel_orani") == 282_500_000 / 289_425_850       # the same number the flag uses
    assert indic.pop("bedel_orani_peer_median") is None and indic.pop("bedel_orani_peer_n") is None
    assert indic.pop("source_check") is None
    assert indic.pop("pazarlik_21b") is False and indic.pop("downloader_bid_ratio") is None
    assert indic == {"elenen_orani": 0.0, "elenen_orani_peer": None, "elenen_orani_peer_n": 0,
                     "karar_suresi_gun": 26, "usul_turu": "acik", "acik_olmayan": False,
                     "yuklenici_payi": None, "yuklenici_payi_n": 1}
    assert set(stats) == set(c_stats) | {"usul_turu", "usul_label", "usul_signal"} and stats["peer"] is None and stats["records"] == 1
    assert set(c_stats["peer"]) == {"label", "records", "tek_gecerli_teklif"}
    got, want = set(meta["counts"]["2026-11-18"]), set(CONTRACT_META["counts"]["2026-11-18"])
    assert got == want | {"tek_teklif", "diger_teklifler_elendi"}   # the split flags add two counters
    assert set(meta) == set(CONTRACT_META) | {"structural_rules", "bugun_cutoff", "part_rates",
                                                        "idare_index", "yuklenici_index", "parent_aliases"}
    assert meta["bugun_cutoff"] == 3.0
    assert set(meta["part_rates"]["mal/hepsi"]) == {"tek_teklif", "diger_teklifler_elendi", "bedel_orani",
                                                "tekrarlayan_eslesik", "idare_orani", "n", "n_computable", "bedel_median_try"}
    t = d["tenders"][0]
    expected = CONTRACT_DAY["tenders"][0]
    expected["flags"][0]["value"] = t["flags"][0]["value"]
    assert t == expected
    assert meta["generated_at"] == "2026-11-18T21:30:00+03:00"
    assert meta["latest_date"] == "2026-11-18" and meta["dates"] == ["2026-11-18"]
    assert meta["counts"]["2026-11-18"] == {"records": 1, "flagged": 1, "tek_gecerli_teklif": 0, "tek_teklif": 0,
                                            "diger_teklifler_elendi": 0, "bedel_orani": 1,
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
