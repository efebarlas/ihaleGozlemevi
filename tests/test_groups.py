"""p checked against a direct count, the 3-g DMO split, and the materiality weight (§4.1)."""
import json
import math
from datetime import date

import pytest

from ihale.export import export_all
from ihale.flags import compute_flags_full
from ihale.indicators import usul_group, usul_label
from ihale.model import Money
from ihale.pipeline import flag_all
from ihale.store import Store, StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)
DMO = "DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ {}"


def full(recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    res, rates = compute_flags_full(stored)
    return [res[s.id] for s in stored], rates


def mk(i, usul="Açık", *, idare=None, toplam=3, gecerli=3, bedel=50.0, maliyet=None, conf=None):
    r = rec(i, ikn=f"2026/{i}", idare=idare or f"KURUM {i}", yuklenici=f"Firma {i}", toplam=toplam, gecerli=gecerli,
            bedel=bedel, maliyet=maliyet if maliyet is not None else bedel * 2, conf=conf)
    r.ihale_usulu = usul
    return r


# ---------------------------------------------------------------- p equals a direct count
def test_p_matches_a_direct_count_including_structurally_excluded_records():
    recs = []
    for i in range(300):                                   # acik: 60 single-bid, 25 unreadable counts
        recs.append(mk(i, toplam=1 if i < 60 else 3, gecerli=1 if i < 60 else 3,
                       conf={"toplam_teklif": 0.1} if 60 <= i < 85 else None))
    for i in range(300, 500):                              # 3-e: 80 single-bid (no points, but real facts)
        recs.append(mk(i, "4734 / 3-e", toplam=1 if i < 380 else 3, gecerli=1 if i < 380 else 3))
    results, rates = full(recs)

    def direct(pred_group, code_cond, computable):
        grp = [r for r in recs if pred_group(r)]
        den = [r for r in grp if computable(r)]
        return sum(1 for r in den if code_cond(r)) / len(den)

    ok = lambda r: r.confident("toplam_teklif") and r.confident("gecerli_teklif")  # noqa: E731
    assert rates["mal/acik"]["tek_teklif"] == round(direct(lambda r: r.ihale_usulu == "Açık",
                                                       lambda r: r.toplam_teklif == 1, ok), 4)
    assert rates["mal/acik"]["tek_teklif"] == round(60 / 275, 4)                        # 25 unreadable are not in the base
    # 3-e single bids earn no points, but they still count in the rate: p must not collapse to 0
    assert rates["mal/istisna_3e"]["tek_teklif"] == round(80 / 200, 4) == 0.4
    assert rates["mal/istisna_3e"]["n"] == 200 and rates["mal/istisna_3e"]["n_computable"]["tek_teklif"] == 200
    assert rates["mal/hepsi"]["tek_teklif"] == round(direct(lambda r: True, lambda r: r.toplam_teklif == 1, ok), 4)
    # the 3-e records have no tek_teklif part in their score, whatever the rates
    assert results[400].score_parts == [] and results[400].flags == []


def test_p_denominator_counts_only_computable_records():
    recs = [mk(i, bedel=99.0, maliyet=100.0) if i < 20 else mk(i) for i in range(200)]       # 20 near-estimate
    recs += [mk(1000 + i, conf={"yaklasik_maliyet": 0.1}) for i in range(100)]               # ratio not computable
    _, rates = full(recs)
    assert rates["mal/acik"]["n"] == 300 and rates["mal/acik"]["n_computable"]["bedel_orani"] == 200
    assert rates["mal/acik"]["bedel_orani"] == 0.1                                               # 20 / 200, not 20 / 300


def test_part_with_a_small_computable_base_is_pulled_toward_the_type_rate():
    recs = [mk(i, toplam=1, gecerli=1) if i < 10 else mk(i) for i in range(150)]             # acik: 10/150 tek
    recs += [mk(1000 + i, "Pazarlık (MD 21 B)", toplam=1 if i < 5 else 3, gecerli=1 if i < 5 else 3)
             for i in range(60)]                                                             # < 100 in its group
    results, rates = full(recs)
    part = results[0].score_parts[0]
    parent = 15 / 210
    assert part["code"] == "tek_teklif" and part["p_group"] == "mal/acik" and (part["k"], part["n"]) == (10, 150)
    assert part["p"] == pytest.approx((10 + 50 * parent) / 200, rel=1e-3)
    small = results[150]
    assert (small.score_parts[0]["k"], small.score_parts[0]["n"]) == (5, 60)


# ---------------------------------------------------------------- 3-g split
def test_usul_group_and_labels():
    assert usul_group("DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ", "istisna_3g") == "istisna_3g_dmo"
    assert usul_group("devlet malzeme ofisi x", "istisna_3g") == "istisna_3g_dmo"
    assert usul_group("ANKARA BELEDİYESİ", "istisna_3g") == "istisna_3g"
    assert usul_group("DEVLET MALZEME OFİSİ", "acik") == "acik"
    assert usul_group(None, "istisna_3g") == "istisna_3g" and usul_group("X", None) is None
    assert usul_label("istisna_3g_dmo") == "4734/3-g (DMO)"
    assert usul_label("istisna_3g") == "4734/3-g (diğer idareler)"
    assert usul_label("istisna_3a") == "4734/3-a"


def test_dmo_and_other_3g_have_separate_rates_and_peer_chains():
    dmo = [mk(i, "4734 / 3-g", idare=DMO.format(i % 40), toplam=1, gecerli=1) for i in range(300)]      # all single
    other = [mk(1000 + i, "4734 / 3-g", idare=f"BELEDİYE {i}", toplam=1 if i < 20 else 3,
                gecerli=1 if i < 20 else 3) for i in range(200)]                                       # 10% single
    results, rates = full(dmo + other)
    assert rates["mal/istisna_3g_dmo"]["n"] == 300 and rates["mal/istisna_3g_dmo"]["tek_teklif"] == 1.0
    assert rates["mal/istisna_3g"]["n"] == 200 and rates["mal/istisna_3g"]["tek_teklif"] == 0.1
    assert results[0].usul_group == "mal/istisna_3g_dmo" and results[300].usul_group == "mal/istisna_3g"
    # DMO single bids are ordinary within DMO (p = 1 → 0 points); other buyers are rare against their own norm
    assert results[0].score_parts[0]["p"] == pytest.approx((300 + 50 * 0.64) / 350, rel=1e-3)   # parent: 320 / 500
    assert results[0].score_parts[0]["points"] < 0.1
    assert results[300].score_parts[0]["p"] == pytest.approx((20 + 50 * 0.64) / 250, rel=1e-3)
    assert results[300].score_parts[0]["p_group"] == "mal/istisna_3g"
    # idare_stats of another idare: peers exclude DMO
    st = results[300].idare_stats
    assert st["usul_turu"] == "istisna_3g" and st["usul_label"] == "4734/3-g (diğer idareler)"
    assert st["peer"]["records"] <= 199
    st_dmo = results[0].idare_stats
    assert st_dmo["usul_turu"] == "istisna_3g_dmo" and st_dmo["usul_label"] == "4734/3-g (DMO)"
    assert "(DMO)" in st_dmo["peer"]["label"]


# ---------------------------------------------------------------- materiality
def weighted_population():
    recs = [mk(i, bedel=100.0) for i in range(200)]               # TRY 100 each: group median 100
    recs[0] = mk(0, bedel=100.0, toplam=1, gecerli=1)             # at the median
    recs[1] = mk(1, bedel=1000.0, toplam=1, gecerli=1)            # 10x the median
    recs[2] = mk(2, bedel=10.0, toplam=1, gecerli=1)              # 1/10
    recs[3] = mk(3, bedel=1e7, toplam=1, gecerli=1)               # far above: clamped
    recs[4] = mk(4, bedel=0.01, toplam=1, gecerli=1)              # far below: clamped
    recs[5] = mk(5, bedel=100.0, toplam=1, gecerli=1)
    recs[5].sozlesme_bedeli = Money(10_000, "EUR")                # not TRY → w = 1
    recs[6] = mk(6, bedel=100.0, toplam=1, gecerli=1, conf={"sozlesme_bedeli": 0.1})   # unreadable → w = 1
    return recs


def test_value_weight_formula_clamp_and_fallbacks():
    results, rates = full(weighted_population())
    w = [r.value_weight for r in results[:7]]
    assert w[0] == 1.0 and w[1] == 1.5 and w[2] == 0.5 and w[3] == 1.5 and w[4] == 0.5 and w[5] == 1.0 and w[6] == 1.0
    mid = mk(0, bedel=316.2278, toplam=1, gecerli=1)              # sqrt(10) x median → 1 + 0.5 * 0.5 = 1.25
    results2, _ = full([mid] + weighted_population()[1:])
    assert results2[0].value_weight == pytest.approx(1.25, abs=0.005)
    assert rates["mal/acik"]["bedel_median_try"] == 100.0 and rates["mal/hepsi"]["bedel_median_try"] == 100.0


def test_score_is_raw_times_weight():
    results, _ = full(weighted_population())
    for r in results[:7]:
        assert r.score_raw == round(sum(p["points"] for p in r.score_parts), 2)
        assert r.score == pytest.approx(r.score_raw * r.value_weight, abs=0.01)
    assert results[1].score > results[0].score > results[2].score         # same parts, different value


def test_group_median_is_used_when_the_group_is_big_enough_else_all_records():
    cheap = [mk(i, bedel=100.0) for i in range(200)]
    dear = [mk(1000 + i, "Pazarlık (MD 21 B)", bedel=10_000.0, toplam=1, gecerli=1) for i in range(30)]   # n < 100
    results, rates = full(cheap + dear)
    assert rates["mal/pazarlik_21b"]["bedel_median_try"] == 10_000.0
    expected = min(1.5, 1 + 0.5 * math.log10(10_000.0 / rates["mal/hepsi"]["bedel_median_try"]))
    assert results[200].value_weight == pytest.approx(expected, abs=0.001)          # all-records median is used


def test_export_has_score_raw_value_weight_and_medians():
    Store().replace_day(D, "mal", weighted_population()[:20])
    s = Store()
    flag_all(s)
    out = export_all(s)
    day = json.loads((out / "days" / "2026-11-18.json").read_text(encoding="utf-8"))
    t = day["tenders"][1]
    assert {"score", "score_raw", "value_weight"} <= set(t)
    assert t["score"] == pytest.approx(t["score_raw"] * t["value_weight"], abs=0.01)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert "bedel_median_try" in meta["part_rates"]["mal/hepsi"] and meta["bugun_cutoff"] == 3.0
