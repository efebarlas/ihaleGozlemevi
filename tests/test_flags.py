from datetime import date, timedelta

import pytest

from ihale.flags import compute_flags, percent_possessive
from ihale.model import Money
from ihale.store import StoredRecord

from rec_helpers import money, rec

D = date(2026, 11, 18)


def run(*recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    out = compute_flags(stored)
    return [out[s.id] for s in stored]


def codes(res):
    return [f["code"] for f in res.flags]


# ---------------------------------------------------------------- suffix grammar
# Hand-written from the spoken numerals (the last word decides): suffix after "%N'" for N = 0..100.
# units: sıfır bir iki üç dört beş altı yedi sekiz dokuz
_UNITS = {0: "ı", 1: "i", 2: "si", 3: "ü", 4: "ü", 5: "i", 6: "sı", 7: "si", 8: "i", 9: "u"}
# tens: on yirmi otuz kırk elli altmış yetmiş seksen doksan yüz
_TENS = {10: "u", 20: "si", 30: "u", 40: "ı", 50: "si", 60: "ı", 70: "i", 80: "i", 90: "ı", 100: "ü"}
EXPECTED = {}
for _n in range(0, 101):
    if _n in _TENS:
        EXPECTED[_n] = _TENS[_n]
    else:
        EXPECTED[_n] = _UNITS[_n % 10]


@pytest.mark.parametrize("n", range(0, 101))
def test_percent_suffix_0_to_100(n):
    assert percent_possessive(n) == f"%{n}'{EXPECTED[n]}"


@pytest.mark.parametrize("n,s", [(95, "%95'i"), (97, "%97'si"), (90, "%90'ı"), (100, "%100'ü"),
                                 (99, "%99'u"), (60, "%60'ı"), (40, "%40'ı"), (104, "%104'ü"),
                                 (1000, "%1000'i"), (110, "%110'u")])
def test_percent_suffix_examples(n, s):
    assert percent_possessive(n) == s


# ---------------------------------------------------------------- tek_teklif / diger_teklifler_elendi
def tek(toplam, gecerli, **kw):
    (a,) = run(rec(1, toplam=toplam, gecerli=gecerli, **kw))
    return a


@pytest.mark.parametrize("toplam,gecerli,expected", [
    (1, 1, ["tek_teklif"]),
    (1, 0, ["tek_teklif"]),              # a single bid, but not valid: still a single bid
    (2, 1, ["diger_teklifler_elendi"]),
    (2, 2, []),
    (2, 0, []),
    (4, 1, ["diger_teklifler_elendi"]),
    (4, 3, []),
])
def test_offer_flag_boundaries(toplam, gecerli, expected):
    a = tek(toplam, gecerli)
    assert [c for c in codes(a) if c in ("tek_teklif", "diger_teklifler_elendi")] == expected


def test_offer_flag_texts_and_values():
    assert tek(1, 1).flags[0] == {"code": "tek_teklif", "value": 1, "text": "Tek teklif verildi"}
    f = tek(4, 1).flags[0]
    assert f == {"code": "diger_teklifler_elendi", "value": 4,
                 "text": "4 teklif verildi, yalnızca kazananınki geçerli sayıldı"}


@pytest.mark.parametrize("bad", ["gecerli_teklif", "toplam_teklif"])
def test_offer_flags_need_both_counts_confident(bad):
    a = tek(1, 1, conf={bad: 0.5})
    assert codes(a) == [] and bad in a.unreadable


def test_offer_flags_missing_values():
    a = tek(None, 1)
    assert codes(a) == [] and "toplam_teklif" in a.unreadable
    b = tek(2, None)
    assert codes(b) == [] and "gecerli_teklif" in b.unreadable


# ---------------------------------------------------------------- bedel_orani
def bedel(**kw):
    (a,) = run(rec(1, **kw))
    return a


def test_ratio_below_threshold_no_flag():
    assert "bedel_orani" not in codes(bedel(bedel=94.99, maliyet=100.0, gecerli=2))


def test_ratio_exactly_097_flags_and_096_does_not():
    assert "bedel_orani" not in codes(bedel(bedel=96.99, maliyet=100.0))
    f = bedel(bedel=97.0, maliyet=100.0).flags[0]
    assert f["code"] == "bedel_orani" and f["value"] == pytest.approx(0.97)
    assert f["text"] == "Sözleşme bedeli yaklaşık maliyetin %97'si"


def test_ratio_exactly_one():
    f = bedel(bedel=100.0, maliyet=100.0).flags[0]
    assert f["text"] == "Sözleşme bedeli yaklaşık maliyetin %100'ü" and f["value"] == 1.0


def test_ratio_above_one():
    f = bedel(bedel=104.9, maliyet=100.0).flags[0]
    assert f["text"] == "Sözleşme bedeli yaklaşık maliyetin üzerinde (%104)"


def test_display_floors_not_rounds():
    f = bedel(bedel=99.9, maliyet=100.0).flags[0]
    assert f["text"].endswith("%99'u") and f["value"] == pytest.approx(0.999)
    assert bedel(bedel=97.99, maliyet=100.0).flags[0]["text"].endswith("%97'si")


def test_threshold_is_exact_in_kurus():
    # 95 / 100 style ratios with awkward magnitudes must not be lost to float error
    r = rec(1)
    r.sozlesme_bedeli = Money(97_000_000, "TRY")
    r.yaklasik_maliyet = Money(100_000_001, "TRY")   # 0.94999999…: below the threshold
    (a,) = run(r)
    assert "bedel_orani" not in codes(a)
    r.sozlesme_bedeli = Money(9_700_000_097, "TRY")
    r.yaklasik_maliyet = Money(10_000_000_100, "TRY")  # exactly 0.97
    (a,) = run(r)
    assert "bedel_orani" in codes(a)


def test_esas_kisim_estimate_preferred_when_confident():
    a = bedel(bedel=97.0, maliyet=1000.0, esas=100.0)
    assert a.flags[0]["text"].endswith("%97'si")


def test_esas_kisim_unconfident_falls_back():
    a = bedel(bedel=97.0, maliyet=100.0, esas=10.0, conf={"esas_kisim_yaklasik_maliyet": 0.4})
    assert a.flags[0]["text"].endswith("%97'si")


def test_missing_estimate_is_unreadable():
    a = bedel(maliyet=None, bedel=100.0)
    assert "bedel_orani" not in codes(a) and "yaklasik_maliyet" in a.unreadable


def test_unconfident_bedel_is_unreadable():
    a = bedel(bedel=99.0, maliyet=100.0, conf={"sozlesme_bedeli": 0.6})
    assert "bedel_orani" not in codes(a) and "sozlesme_bedeli" in a.unreadable


def test_zero_estimate_is_not_divided():
    a = bedel(maliyet=0.0, bedel=1.0)
    assert "bedel_orani" not in codes(a) and "yaklasik_maliyet" in a.unreadable


def test_currency_mismatch_no_ratio_with_reason():
    r = rec(1, maliyet=100.0)
    r.sozlesme_bedeli = Money(15405000, "EUR")
    (a,) = run(r)
    assert "bedel_orani" not in codes(a)
    assert {"field": "sozlesme_bedeli", "reason": "para birimi farklı"} in a.unreadable


def test_dual_estimate_uses_primary_currency_only():
    r = rec(1, bedel=47407500.0, maliyet=47407500.0)
    r.yaklasik_maliyet = Money(4740750000, "TRY", Money(107247500, "EUR"))
    (a,) = run(r)
    assert a.flags[0]["value"] == 1.0


def test_kismi_sum_over_ikn_records():
    lots = [rec(i, ikn="2026/9", bedel=33.0, maliyet=100.0, yuklenici=f"Firma {i}") for i in (1, 2, 3)]
    for a in run(*lots):
        assert a.flags[0]["code"] == "bedel_orani"
        assert a.flags[0]["text"] == "Bu ihalenin 3 kısmının toplam bedeli yaklaşık maliyetin %99'u"
        assert a.kisim_n == 3


def test_kismi_below_threshold_no_flag():
    res = run(*[rec(i, ikn="2026/9", bedel=10.0, maliyet=100.0, yuklenici=f"F{i}") for i in (1, 2)])
    assert all("bedel_orani" not in codes(a) for a in res)


def test_kismi_dedupe_same_ikn_yuklenici_bedel():
    lots = [rec(1, ikn="2026/9", bedel=50.0, maliyet=100.0, yuklenici="A Ltd. Şti."),
            rec(2, ikn="2026/9", bedel=50.0, maliyet=100.0, yuklenici="A Limited Şirketi"),  # same award twice
            rec(3, ikn="2026/9", bedel=47.0, maliyet=100.0, yuklenici="B Ltd. Şti.")]
    res = run(*lots)
    assert res[0].kisim_n == 2
    assert res[0].flags[0]["text"] == "Bu ihalenin 2 kısmının toplam bedeli yaklaşık maliyetin %97'si"


def test_kismi_over_estimate_text():
    res = run(rec(1, ikn="2026/9", bedel=60.0, maliyet=100.0, yuklenici="A"),
              rec(2, ikn="2026/9", bedel=50.0, maliyet=100.0, yuklenici="B"))
    assert res[0].flags[0]["text"] == "Bu ihalenin 2 kısmının toplam bedeli yaklaşık maliyetin üzerinde (%110)"


def test_kismi_with_unconfident_sibling_is_unreadable():
    res = run(rec(1, ikn="2026/9", bedel=50.0, maliyet=100.0, yuklenici="A"),
              rec(2, ikn="2026/9", bedel=50.0, maliyet=100.0, yuklenici="B", conf={"sozlesme_bedeli": 0.2}))
    assert "bedel_orani" not in codes(res[0]) and "sozlesme_bedeli" in res[0].unreadable


def test_kismi_with_sibling_in_other_currency():
    sib = rec(2, ikn="2026/9", yuklenici="B", maliyet=100.0)
    sib.sozlesme_bedeli = Money(1000, "EUR")
    res = run(rec(1, ikn="2026/9", bedel=99.0, maliyet=100.0, yuklenici="A"), sib)
    assert {"field": "sozlesme_bedeli", "reason": "para birimi farklı"} in res[0].unreadable


def test_same_ikn_on_other_day_counts_as_same_tender():
    res = run(rec(1, ikn="2026/9", bedel=50.0, maliyet=100.0, yuklenici="A", day=D - timedelta(days=1)),
              rec(1, ikn="2026/9", bedel=45.0, maliyet=100.0, yuklenici="B"))
    assert res[1].kisim_n == 2


# ---------------------------------------------------------------- tekrarlayan_yuklenici
def repeats(dates):
    """One contractor/idare, one record per date with distinct ikns. Returns results in input order."""
    return run(*[rec(1, day=d, ikn=f"2026/{i}") for i, d in enumerate(dates)])


def test_three_distinct_ikns_flag_with_text():
    res = repeats([D - timedelta(days=10), D - timedelta(days=5), D])
    assert "tekrarlayan_yuklenici" not in codes(res[0]) and "tekrarlayan_yuklenici" not in codes(res[1])
    f = [x for x in res[2].flags if x["code"] == "tekrarlayan_yuklenici"][0]
    assert f["value"] == 3 and f["text"] == "Bu yüklenici son 12 ayda bu idareden 3 sözleşme aldı (bu dahil)"


def test_two_ikns_not_enough():
    assert all("tekrarlayan_yuklenici" not in codes(a) for a in repeats([D - timedelta(days=3), D]))


def test_same_ikn_many_lots_is_one():
    lots = [rec(i, ikn="2026/5", bedel=1.0, maliyet=100.0) for i in range(1, 6)]
    assert all("tekrarlayan_yuklenici" not in codes(a) for a in run(*lots))


def test_window_edge_365_included_366_excluded():
    inside = repeats([D - timedelta(days=365), D - timedelta(days=100), D])
    assert "tekrarlayan_yuklenici" in codes(inside[2])
    outside = repeats([D - timedelta(days=366), D - timedelta(days=100), D])
    assert "tekrarlayan_yuklenici" not in codes(outside[2])


def test_later_records_do_not_count_for_earlier_ones():
    res = repeats([D - timedelta(days=2), D - timedelta(days=1), D])
    assert "tekrarlayan_yuklenici" not in codes(res[0]) and "tekrarlayan_yuklenici" not in codes(res[1])


def test_same_day_other_ikns_count():
    assert all("tekrarlayan_yuklenici" in codes(a) for a in repeats([D, D, D]))


def test_different_idare_does_not_count():
    res = run(rec(1, ikn="2026/1", idare="A İDARESİ"), rec(1, ikn="2026/2", idare="B İDARESİ"),
              rec(1, ikn="2026/3", idare="A İDARESİ"))
    assert all("tekrarlayan_yuklenici" not in codes(a) for a in res)


def test_different_yuklenici_does_not_count():
    res = run(rec(1, ikn="2026/1", yuklenici="A"), rec(1, ikn="2026/2", yuklenici="B"),
              rec(1, ikn="2026/3", yuklenici="A"))
    assert all("tekrarlayan_yuklenici" not in codes(a) for a in res)


def test_key_normalization_joins_spellings():
    res = run(rec(1, ikn="2026/1", yuklenici="Acme San. ve Tic. Ltd. Şti."),
              rec(1, ikn="2026/2", yuklenici="ACME SANAYİ VE TİCARET LİMİTED ŞİRKETİ"),
              rec(1, ikn="2026/3", yuklenici="Acme  San. ve Tic. Ltd. Şti"))
    assert "tekrarlayan_yuklenici" in codes(res[2])


def test_unconfident_member_not_counted_and_unconfident_self_unreadable():
    res = run(rec(1, ikn="2026/1"), rec(1, ikn="2026/2", conf={"yuklenici": 0.4}), rec(1, ikn="2026/3"))
    assert "tekrarlayan_yuklenici" not in codes(res[2])
    assert "yuklenici" in res[1].unreadable and "tekrarlayan_yuklenici" not in codes(res[1])


def test_missing_idare_unreadable():
    (a,) = run(rec(1, idare=None))
    assert "idare" in a.unreadable


def test_unreadable_lists_low_confidence_but_not_known_empty():
    (a,) = run(rec(1, conf={"konu": 0.5, "esas_kisim_yaklasik_maliyet": 1.0}))
    assert a.unreadable == ["konu"]
