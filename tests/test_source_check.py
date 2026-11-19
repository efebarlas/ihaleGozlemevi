"""Source inconsistency (§4.1): probable typos (power of ten) vs large ratios."""
from datetime import date

import pytest

from ihale.flags import LARGE_NOTE, TYPO_NOTE, compute_flags_full, source_check
from ihale.store import StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)


def full(recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    res, rates = compute_flags_full(stored)
    return [res[s.id] for s in stored], rates


def background(n=300, bad=0):
    """Plain open-tender records, `bad` of them near-estimate (ratio 0.99), so bedel_orani has a base rate."""
    return [rec(1000 + i, ikn=f"2026/{1000 + i}", idare=f"ARKA {i}", yuklenici=f"B{i}",
                bedel=99.0 if i < bad else 50.0, maliyet=100.0) for i in range(n)]


def target(ratio, **kw):
    return rec(1, ikn="2026/1", idare="HEDEF KURUM", yuklenici="Hedef Firma", bedel=ratio * 100.0, maliyet=100.0, **kw)


def bedel_flag(res):
    return next((f for f in res.flags if f["code"] == "bedel_orani"), None)


@pytest.mark.parametrize("ratio,expected", [
    (1000.0, "typo"), (1010.0, "typo"), (990.0, "typo"), (1011.0, "large"), (10.0, "typo"), (100.0, "typo"),
    (0.1001, "typo"), (0.1, "typo"), (0.01, "typo"), (0.0101, "typo"), (0.0102, None),
    (4.83, "large"), (1.51, "large"), (1.5, None), (1.2, None), (1.0, None), (1.009, None), (0.97, None),
    (None, None), (0.0, None)])
def test_source_check_classifier(ratio, expected):
    assert source_check(ratio) == expected


def test_1000x_is_a_typo_shown_but_unscored_and_excluded_from_p():
    recs = [target(1000.0, toplam=1, gecerli=1)] + background(300, bad=30)
    res, rates = full(recs)
    a = res[0]
    f = bedel_flag(a)
    assert f["source_check"] == "typo" and f["text"].endswith(TYPO_NOTE) and "üzerinde" in f["text"]
    assert [p["code"] for p in a.score_parts] == ["tek_teklif"]               # no bedel_orani points
    assert a.indicators["source_check"] == "typo" and a.indicators["bedel_orani"] == 1000.0
    # excluded from p: 30 near-estimate among 300 computable (the typo record is neither numerator nor base)
    assert rates["acik"]["n_computable"]["bedel_orani"] == 300 and rates["acik"]["bedel_orani"] == 0.1


def test_typo_is_not_a_partner_for_the_repeat_pair():
    from datetime import timedelta
    recs = [rec(1, day=D - timedelta(days=i), ikn=f"2026/{i}", bedel=1000.0 * 100, maliyet=100.0)
            for i in range(3)] + background(200)
    res, _ = full(recs)
    last = res[0]
    assert "tekrarlayan_yuklenici" in [f["code"] for f in last.flags] and last.score_parts == []


def test_4_83x_is_large_scored_normally_and_counted_in_p():
    recs = [target(4.83, toplam=3, gecerli=3)] + background(300, bad=30)
    res, rates = full(recs)
    a = res[0]
    f = bedel_flag(a)
    assert f["source_check"] == "large" and f["text"].endswith(LARGE_NOTE)
    assert [p["code"] for p in a.score_parts] == ["bedel_orani"] and a.score_raw > 0
    assert a.indicators["source_check"] == "large"
    assert rates["acik"]["n_computable"]["bedel_orani"] == 301
    assert rates["acik"]["bedel_orani"] == round(31 / 301, 4)


def test_0_1001x_has_no_flag_but_a_typo_indicator():
    (a, *_), _ = full([target(0.1001)] + background(50))
    assert bedel_flag(a) is None and a.indicators["source_check"] == "typo" and a.score_parts == []


def test_1_2x_gets_neither():
    (a, *_), _ = full([target(1.2)] + background(50))
    f = bedel_flag(a)
    assert f is not None and "source_check" not in f and f["text"].endswith("(%120,0)")
    assert a.indicators["source_check"] is None


def test_kismi_sum_is_classified_on_the_total():
    lots = [rec(i, ikn="2026/9", yuklenici=f"F{i}", bedel=50_000.0, maliyet=100.0) for i in (1, 2)]
    (a, _), _ = full(lots)
    assert bedel_flag(a)["source_check"] == "typo" and a.indicators["bedel_orani"] == 1000.0
