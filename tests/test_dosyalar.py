"""İdare and Yüklenici dossier files (M4)."""
import json
from datetime import date, timedelta

import pytest

from ihale import config
from ihale.dosyalar import procedure_category
from ihale.export import export_all
from ihale.pipeline import flag_all
from ihale.slugs import SlugMap, slugify, tr_sort_key
from ihale.store import Store

from rec_helpers import rec

D = date(2026, 11, 18)
IDARE = "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ"


def mk(i, *, day=D, idare=IDARE, yuklenici="Emir Sosyal Hizmetler Limited Şirketi", usul="Açık", type_="mal",
       toplam=3, gecerli=3, bedel=100.0, section="A"):
    r = rec(i, day=day, type_=type_, section=section, ikn=f"2026/{i}", idare=idare, yuklenici=yuklenici,
            toplam=toplam, gecerli=gecerli, bedel=bedel, maliyet=bedel * 2)
    r.ihale_usulu = usul
    return r


def export(*days):
    """days: (date, type, [records]) tuples; returns the export dir."""
    s = Store()
    for day, type_, recs in days:
        s.replace_day(day, type_, recs)
    flag_all(s)
    return export_all(s)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def idare_files(out):
    return sorted((out / "idare").glob("*.json"))


# ---------------------------------------------------------------- slugs
@pytest.mark.parametrize("text,slug", [
    ("ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ", "antalya-il-saglik-mudurlugu"),
    ("Şanlıurfa Büyükşehir Belediyesi", "sanliurfa-buyuksehir-belediyesi"),
    ("IŞIK Ltd. Şti.", "isik-ltd-sti"),
    ("İZMİR", "izmir"), ("  ", "x"), ("!!!", "x"), ("a&b c", "a-b-c")])
def test_slugify(text, slug):
    assert slugify(text) == slug


def test_slugify_truncates_at_word_boundary():
    s = slugify("kelime " * 40)
    assert len(s) <= 80 and not s.endswith("-")


def test_slug_map_unique_and_stable(data_dir):
    m = SlugMap()
    a, b = m.slug("idare", "ankara belediyesi"), m.slug("idare", "ankara belediyesi!")      # same base, different keys
    assert a == "ankara-belediyesi" and b == "ankara-belediyesi-2"
    m.save()
    m2 = SlugMap()
    assert m2.slug("idare", "ankara belediyesi") == a and m2.slug("idare", "ankara belediyesi!") == b
    assert m2.slug("yuklenici", "ankara belediyesi") == "ankara-belediyesi"                 # kinds are independent
    assert (config.data_dir() / "slugs.json").exists()


def test_slug_never_changes_once_issued():
    out = export((D, "mal", [mk(1)]))
    (first,) = [p.stem for p in idare_files(out)]
    earlier = mk(2, day=D - timedelta(days=1), idare="ANTALYA IL SAGLIK MUDURLUGU", yuklenici="Z Ltd. Şti.")
    out = export((D, "mal", [mk(1)]), (D - timedelta(days=1), "mal", [earlier]))
    assert load(out / "idare" / f"{first}.json")["name"] == IDARE
    assert len(idare_files(out)) == 2
    assert sorted(p.stem for p in idare_files(out)) == ["antalya-il-saglik-mudurlugu", "antalya-il-saglik-mudurlugu-2"]


def test_tr_sort_key_collation():
    names = ["Zeytin", "Çorum", "Ceyhan", "Ağrı", "Işık", "İzmir", "Ordu", "Şişli", "Sivas", "Ünye", "Ulus", "Öz", "Oba"]
    assert sorted(names, key=tr_sort_key) == ["Ağrı", "Ceyhan", "Çorum", "Işık", "İzmir", "Oba", "Ordu", "Öz",
                                              "Sivas", "Şişli", "Ulus", "Ünye", "Zeytin"]


# ---------------------------------------------------------------- idare files
def test_idare_file_contents_and_totals():
    mal = [mk(1, bedel=100.0), mk(2, bedel=300.0, yuklenici="Başka Ltd. Şti.")]
    hizmet = [mk(3, type_="hizmet", bedel=50.0)]
    out = export((D, "mal", mal), (D, "hizmet", hizmet))
    (f,) = idare_files(out)
    d = load(f)
    assert d["slug"] == f.stem == "antalya-il-saglik-mudurlugu" and d["name"] == IDARE
    assert d["key"] == "antalya il sağlık müdürlüğü" and d["idare_turu"] == "sağlık" and d["il"] == "Antalya"
    assert d["totals"]["mal"] == {"records": 2, "awards": 2, "try_total": 400.0, "median_bedel_try": 200.0}
    assert d["totals"]["hizmet"]["records"] == 1 and d["totals"]["hizmet"]["try_total"] == 50.0
    assert len(d["timeline"]) == 3


def test_every_idare_key_with_a_record_gets_a_file_and_index_entry():
    out = export((D, "mal", [mk(1, idare="ÇORUM BELEDİYESİ"), mk(2, idare="Adana Belediyesi"),
                             mk(3, idare="IĞDIR ÜNİVERSİTESİ"), mk(4, idare="İZMİR BELEDİYESİ")]))
    assert len(idare_files(out)) == 4
    meta = load(out / "meta.json")
    assert [x["name"] for x in meta["idare_index"]] == ["Adana Belediyesi", "ÇORUM BELEDİYESİ", "IĞDIR ÜNİVERSİTESİ",
                                                        "İZMİR BELEDİYESİ"]
    assert all(set(x) == {"slug", "name", "records"} and x["records"] == 1 for x in meta["idare_index"])


def test_unconfident_idare_gets_no_file():
    r = mk(1)
    r.confidence["idare"] = 0.2
    out = export((D, "mal", [r, mk(2, idare="KONYA BELEDİYESİ")]))
    assert [load(p)["name"] for p in idare_files(out)] == ["KONYA BELEDİYESİ"]


def test_procedure_mix_per_iso_week_with_21b_separate():
    d1, d2 = date(2026, 11, 16), date(2026, 11, 23)        # Mondays of W47 and W48
    recs1 = [mk(1, day=d1, usul="Açık"), mk(2, day=d1, usul="Pazarlık (MD 21 B)"),
             mk(3, day=d1, usul="Pazarlık (MD 21 F)"), mk(4, day=d1, usul="4734 / 3-g"),
             mk(5, day=d1, usul="4734 / 3-e"), mk(6, day=d1, usul="4734 / 3-b"),
             mk(7, day=d1, usul="Açık", bedel=900.0)]
    out = export((d1, "mal", recs1), (d2, "mal", [mk(10, day=d2, usul="Açık")]))
    d = load(idare_files(out)[0])
    w47, w48 = d["procedure_mix"]
    assert w47["week"] == "2026-W47" and w47["start"] == "2026-11-16" and w48["week"] == "2026-W48"
    assert w47["counts"] == {"acik": 2, "pazarlik_21b": 1, "pazarlik_diger": 1, "istisna_3g": 1, "istisna_3e": 1,
                             "istisna_diger": 1}
    assert w47["try"]["acik"] == 1000.0 and w47["try"]["pazarlik_21b"] == 100.0
    assert w48["counts"] == {"acik": 1}
    assert [c["code"] for c in d["procedure_categories"]][:2] == ["acik", "pazarlik_21b"]


def test_procedure_category_mapping():
    got = [procedure_category(c) for c in ("acik", "pazarlik_21b", "pazarlik_21f", "istisna_3g", "istisna_3e",
                                           "istisna_3b", "belli_istekliler", None)]
    assert got == ["acik", "pazarlik_21b", "pazarlik_diger", "istisna_3g", "istisna_3e", "istisna_diger",
                   "diger", "diger"]


def test_tek_share_by_group_beside_peers():
    own = [mk(i, toplam=1, gecerli=1, yuklenici=f"F{i}") for i in range(6)]
    peers = [mk(100 + i, idare=f"MUĞLA İL SAĞLIK MÜDÜRLÜĞÜ {i}", toplam=1 if i < 5 else 3,
                gecerli=1 if i < 5 else 3, yuklenici=f"P{i}") for i in range(25)]
    out = export((D, "mal", own + peers))
    d = next(load(p) for p in idare_files(out) if load(p)["name"] == IDARE)
    (g,) = d["tek_gecerli_by_group"]
    assert g["group"] == "mal/acik" and g["records"] == 6 and g["tek_gecerli_teklif"] == 1.0
    assert g["peer"]["records"] == 25 and g["peer"]["tek_gecerli_teklif"] == 0.2


def test_timeline_in_date_order_with_flags_score_and_masked_persons():
    older = mk(2, day=D - timedelta(days=3))
    newer = mk(1, yuklenici="Mustafa Öz", toplam=1, gecerli=1)
    out = export((D - timedelta(days=3), "mal", [older]), (D, "mal", [newer]))
    d = load(idare_files(out)[0])
    assert [t["date"] for t in d["timeline"]] == ["2026-11-15", "2026-11-18"]
    last = d["timeline"][1]
    assert last["yuklenici"] == "Gerçek kişi yüklenici" and last["yuklenici_slug"] is None
    assert last["flags"] == ["tek_teklif"] and isinstance(last["score"], float)
    assert set(last) == {"id", "date", "type", "konu", "yuklenici", "yuklenici_slug", "bedel", "flags", "score"}
    assert d["timeline"][0]["yuklenici_slug"] == "emir-sosyal-hizmetler-ltd"
    assert "Mustafa" not in json.dumps(d, ensure_ascii=False)


def test_top_yuklenici_lists_are_facts_only():
    recs = [mk(i, yuklenici="A Ltd. Şti.", bedel=10.0) for i in range(3)]
    recs += [mk(10, yuklenici="B Ltd. Şti.", bedel=5000.0), mk(20, yuklenici="Ali Veli")]      # firm B, a person
    out = export((D, "mal", recs))
    d = load(idare_files(out)[0])
    assert [x["name"] for x in d["top_yuklenici_by_count"]] == ["A Ltd. Şti.", "B Ltd. Şti."]
    assert [x["name"] for x in d["top_yuklenici_by_try"]] == ["B Ltd. Şti.", "A Ltd. Şti."]
    assert set(d["top_yuklenici_by_count"][0]) == {"name", "slug", "count", "try_total"}
    assert d["natural_person_awards"] == 1 and "Ali Veli" not in json.dumps(d, ensure_ascii=False)


# ---------------------------------------------------------------- yüklenici files
def test_yuklenici_file_contents_no_score():
    first = [mk(1, bedel=100.0, usul="Açık"), mk(2, idare="KONYA BELEDİYESİ", bedel=50.0, usul="4734 / 3-g")]
    older = mk(3, day=D - timedelta(days=2), bedel=25.0)
    out = export((D, "mal", first), (D - timedelta(days=2), "mal", [older]))
    d = load(out / "yuklenici" / "emir-sosyal-hizmetler-ltd.json")
    assert d["name"] == "Emir Sosyal Hizmetler Limited Şirketi" and d["key"] == "emir sosyal hizmetler ltd"
    assert [a["date"] for a in d["awards"]] == ["2026-11-16", "2026-11-18", "2026-11-18"]
    a = d["awards"][1]
    assert set(a) == {"id", "date", "type", "idare", "konu", "bedel", "usul"}
    assert a["idare"] == {"name": IDARE, "slug": "antalya-il-saglik-mudurlugu"}
    assert d["totals_per_idare"][0] == {"idare": IDARE, "slug": "antalya-il-saglik-mudurlugu", "count": 2,
                                        "try_total": 125.0}
    blob = json.dumps(d, ensure_ascii=False)
    assert "score" not in blob and "flags" not in blob and "rank" not in blob


def test_natural_persons_get_no_yuklenici_file_and_are_not_indexed():
    out = export((D, "mal", [mk(1, yuklenici="Mustafa Öz"), mk(2, yuklenici="Acme Ltd. Şti.")]))
    assert [p.stem for p in (out / "yuklenici").glob("*.json")] == ["acme-ltd"]
    meta = load(out / "meta.json")
    assert [x["name"] for x in meta["yuklenici_index"]] == ["Acme Ltd. Şti."]
    assert "mustafa" not in (config.data_dir() / "slugs.json").read_text(encoding="utf-8").lower()


def test_unconfident_yuklenici_gets_no_file():
    r = mk(1)
    r.confidence["yuklenici"] = 0.1
    out = export((D, "mal", [r]))
    assert not (out / "yuklenici").exists() or not list((out / "yuklenici").glob("*.json"))


def test_stale_files_removed_when_data_goes_away():
    out = export((D, "mal", [mk(1), mk(2, idare="KONYA BELEDİYESİ", yuklenici="Z Ltd. Şti.")]))
    assert len(idare_files(out)) == 2
    out = export((D, "mal", [mk(1)]))
    assert len(idare_files(out)) == 1 and len(list((out / "yuklenici").glob("*.json"))) == 1


def test_export_is_byte_stable_across_runs():
    recs = [mk(i, idare=f"KURUM {i % 3}", yuklenici=f"Firma {i % 4} Ltd. Şti.") for i in range(12)]

    def snapshot(out):
        return {p.name: p.read_bytes() for p in idare_files(out) + sorted((out / "yuklenici").glob("*.json"))}

    first = snapshot(export((D, "mal", recs)))
    second = snapshot(export((D, "mal", recs)))
    assert first == second and len(first) == 7
