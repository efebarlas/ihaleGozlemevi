"""Rarity-weighted score (§4.1): points = ln(1/p), p = part rate within the record's usul_turu."""
import math
from datetime import date, timedelta

import pytest

from ihale import structural
from ihale.flags import BUGUN_CUTOFF, MIN_GROUP_N, P_FLOOR, compute_flags, compute_flags_full
from ihale.store import StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)


def run(*recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    return compute_flags(stored), stored


def mk(i, *, usul="Açık", tek=False, bedel=None, idare=None, day=D):
    r = rec(i, day=day, ikn=f"2026/{i}", idare=idare or f"IDARE {i}", yuklenici=f"Firma {i}",
            toplam=1 if tek else 3, gecerli=1 if tek else 3,
            bedel=bedel if bedel is not None else 50.0, maliyet=100.0)
    r.ihale_usulu = usul
    return r


def population(n, tek_n, usul="Açık", start=0, bedel_n=0):
    return [mk(start + i, usul=usul, tek=i < tek_n, bedel=99.0 if tek_n <= i < tek_n + bedel_n else None)
            for i in range(n)]


def test_points_are_ln_of_inverse_rate_within_the_usul_group():
    recs = population(200, 10)                               # p(tek_teklif) = 10/200 = 0.05 in acik (n >= 100)
    res, stored = run(*recs)
    a = res[1]
    (part,) = a.score_parts
    assert part == {"code": "tek_teklif", "points": round(math.log(20), 2), "p": 0.05, "p_group": "acik"}
    assert a.score == 3.0 and a.score >= BUGUN_CUTOFF            # ln 20 ≈ 3.00 is exactly the cut-off
    assert res[200].score == 0.0 and res[200].score_parts == []


def test_small_group_falls_back_to_all_records_rate():
    big = population(300, 3, usul="Açık")                    # tek rate 1% in acik
    small = [mk(1000 + i, usul="Pazarlık (MD 21 B)", tek=i < 5) for i in range(10)]   # n=10 < 100, 50% locally
    res, stored = run(*big, *small)
    sid = next(s.id for s in stored if s.record.ikn == "2026/1000")
    part = res[sid].score_parts[0]
    assert part["p_group"] == "hepsi" and part["p"] == round(8 / 310, 4)
    assert part["points"] == round(math.log(310 / 8), 2)
    big_id = next(s.id for s in stored if s.record.ikn == "2026/0")
    assert res[big_id].score_parts[0]["p_group"] == "acik" and res[big_id].score_parts[0]["p"] == 0.01


def test_group_threshold_is_100_records():
    assert MIN_GROUP_N == 100
    for n, expected in ((99, "hepsi"), (100, "acik")):
        recs = population(n, 5)
        recs += [mk(5000 + i, usul="Pazarlık (MD 21 B)") for i in range(150 - n)] if n < 100 else []
        res, _ = run(*recs)
        assert res[1].score_parts[0]["p_group"] == expected


def test_p_is_floored_at_one_in_a_thousand():
    recs = population(3000, 1)                               # raw p = 1/3000
    res, _ = run(*recs)
    part = res[1].score_parts[0]
    assert P_FLOOR == 0.001 and part["p"] == 0.001 and part["points"] == round(math.log(1000), 2) == 6.91


def test_score_is_the_sum_of_part_points():
    recs = [mk(i, tek=i < 20, bedel=99.0 if i < 10 else None) for i in range(200)]
    res, _ = run(*recs)
    a = res[1]                                               # tek_teklif and bedel_orani
    assert [p["code"] for p in a.score_parts] == ["tek_teklif", "bedel_orani"]
    assert a.score == round(sum(p["points"] for p in a.score_parts), 2)


def test_bare_repeat_earns_nothing_but_paired_repeat_is_a_part():
    dates = [D - timedelta(days=2), D - timedelta(days=1), D]
    bare = [rec(1, day=d, ikn=f"2026/{i}") for i, d in enumerate(dates)] + population(150, 0, start=100)
    res, stored = run(*bare)
    assert "tekrarlayan_yuklenici" in [f["code"] for f in res[3].flags] and res[3].score_parts == []
    paired = [rec(1, day=d, ikn=f"2026/{i}", toplam=1, gecerli=1) for i, d in enumerate(dates)] \
        + population(150, 0, start=100)
    res, _ = run(*paired)
    assert [p["code"] for p in res[3].score_parts] == ["tek_teklif", "tekrarlayan_eslesik"]


def test_part_rates_table():
    recs = population(150, 15) + [mk(900 + i, usul="Pazarlık (MD 21 F)", tek=True) for i in range(5)]
    _, rates = compute_flags_full([StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)])
    assert set(rates) == {"hepsi", "acik", "pazarlik_21f"}
    assert rates["acik"]["n"] == 150 and rates["acik"]["tek_teklif"] == 0.1
    assert rates["hepsi"]["n"] == 155 and rates["hepsi"]["tek_teklif"] == round(20 / 155, 4)
    assert set(rates["hepsi"]) == {"tek_teklif", "diger_teklifler_elendi", "bedel_orani", "tekrarlayan_eslesik",
                                   "idare_orani", "n"}


def test_rates_are_recomputed_from_the_whole_history():
    one, _ = run(*population(200, 10))
    more, _ = run(*population(200, 10), *population(200, 50, start=1000))     # a heavier tek share arrives
    assert more[1].score_parts[0]["p"] > one[1].score_parts[0]["p"]
    assert more[1].score < one[1].score


# ---------------------------------------------------------------- istisna-3e
def test_3e_single_bid_gets_no_points_for_any_idare_but_flags_stay():
    recs = [mk(1, usul="4734 / 3-e", tek=True, idare="ADALET BAKANLIĞI CEZA İNFAZ KURUMU İŞYURTLARI")]
    recs += population(150, 15, start=100)
    res, _ = run(*recs)
    a = res[1]
    assert [f["code"] for f in a.flags] == ["tek_teklif"] and a.score_parts == [] and a.score == 0.0
    assert a.structural["id"] == "istisna-3e" and a.structural["text"].startswith("4734 sayılı Kanun md. 3/e")
    assert a.idare_stats is None or a.idare_stats.get("peer_note") is None      # own_peer_group does not apply


def test_3e_other_parts_still_count():
    recs = [mk(i, usul="4734 / 3-e", tek=True, bedel=99.0, idare=f"KURUM {i}") for i in range(1, 4)]
    recs += population(150, 15, start=100)
    res, _ = run(*recs)
    assert [p["code"] for p in res[1].score_parts] == ["bedel_orani"]


def test_3e_rule_in_table_and_matches_any_idare():
    assert structural.match("HERHANGİ BİR İDARE", "istisna_3e").id == "istisna-3e"
    assert structural.match("HERHANGİ BİR İDARE", "istisna_3g") is None
    ids = [r["id"] for r in structural.rules_meta()]
    assert ids == ["istisna-3e"]
    rule = structural.rules_meta()[0]
    assert rule["effects"] == ["no_single_bid_points"] and rule["added"] == "2026-11-19"
