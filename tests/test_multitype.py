"""Scoring is per bulletin type: group key = <type>/<usul group>, each type has its own <type>/hepsi fallback."""
from datetime import date

import pytest

from ihale import cli
from ihale.flags import compute_flags_full
from ihale.store import StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)


def full(recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    res, rates = compute_flags_full(stored)
    return [res[s.id] for s in stored], rates


def mk(i, type_="mal", usul="Açık", tek=False, idare=None, bedel=50.0):
    r = rec(i, type_=type_, ikn=f"2026/{i}", idare=idare or f"KURUM {type_} {i}", yuklenici=f"F{type_}{i}",
            toplam=1 if tek else 3, gecerli=1 if tek else 3, bedel=bedel, maliyet=bedel * 2)
    r.ihale_usulu = usul
    return r


def pop(type_, n, tek_n, start, usul="Açık", bedel=50.0):
    return [mk(start + i, type_, usul, tek=i < tek_n, bedel=bedel) for i in range(n)]


def test_group_keys_include_the_bulletin_type():
    recs = pop("mal", 150, 15, 0) + pop("yapim", 150, 30, 1000)
    res, rates = full(recs)
    assert set(rates) == {"mal/hepsi", "mal/acik", "yapim/hepsi", "yapim/acik"}
    assert rates["mal/acik"]["tek_teklif"] == 0.1 and rates["yapim/acik"]["tek_teklif"] == 0.2
    assert res[0].usul_group == "mal/acik" and res[150].usul_group == "yapim/acik"
    assert res[0].score_parts[0]["p_group"] == "mal/acik" and res[0].score_parts[0]["p"] == 0.1
    assert res[150].score_parts[0]["p_group"] == "yapim/acik" and res[150].score_parts[0]["p"] == 0.2


def test_same_usul_in_two_types_does_not_mix():
    recs = pop("mal", 200, 2, 0) + pop("hizmet", 200, 100, 1000)         # 1% vs 50% single bids in open tenders
    res, rates = full(recs)
    assert rates["mal/acik"]["tek_teklif"] == 0.01 and rates["hizmet/acik"]["tek_teklif"] == 0.5
    assert res[0].score > res[200].score                                 # a mal single bid is far rarer than a hizmet one


def test_each_type_is_smoothed_toward_its_own_parent_rate():
    recs = (pop("mal", 150, 15, 0) + pop("mal", 40, 20, 500, usul="Pazarlık (MD 21 B)")
            + pop("yapim", 150, 75, 1000) + pop("yapim", 40, 4, 2000, usul="Pazarlık (MD 21 B)"))
    res, rates = full(recs)
    mal_b = next(r for r, s in zip(res, recs) if s.ikn == "2026/500")
    yap_b = next(r for r, s in zip(res, recs) if s.ikn == "2026/2000")
    assert mal_b.score_parts[0]["p_group"] == "mal/pazarlik_21b" and mal_b.score_parts[0]["p_source"] == "group"
    assert mal_b.score_parts[0]["p"] == pytest.approx((20 + 50 * 35 / 190) / 90, rel=1e-3)      # parent: all mal records
    # yapim 21/b has only 4 events (< 5): p is the yapim-wide rate, never the mal one
    assert yap_b.score_parts[0]["p_source"] == "type" and yap_b.score_parts[0]["p_group"] == "yapim/hepsi"
    assert yap_b.score_parts[0]["p"] == pytest.approx(79 / 190, rel=1e-3)


def test_bedel_median_fallback_is_per_type():
    recs = pop("mal", 200, 0, 0, bedel=100.0) + pop("yapim", 200, 0, 1000, bedel=100_000.0)
    recs += [mk(5000, "mal", "Pazarlık (MD 21 B)", tek=True, bedel=1000.0)]             # tiny group → mal median (100)
    res, rates = full(recs)
    assert rates["mal/hepsi"]["bedel_median_try"] == 100.0 and rates["yapim/hepsi"]["bedel_median_try"] == 100_000.0
    assert res[-1].value_weight == 1.5                                       # 10x the *mal* median, not the global one


def test_peer_chain_and_labels_stay_inside_the_type():
    own = [mk(i, "yapim", "Açık", tek=True, idare="ANTALYA BELEDİYESİ") for i in range(6)]
    mal_peers = pop("mal", 40, 0, 1000)                                      # other type: must not be peers
    yapim_peers = [mk(2000 + i, "yapim", "Açık", idare=f"KONYA BELEDİYESİ {i}") for i in range(35)]
    res, _ = full(own + mal_peers + yapim_peers)
    st = res[0].idare_stats
    assert st["peer"]["records"] == 35
    assert st["peer"]["label"] == "Türkiye'deki belediyeler (yapım, açık)"
    res2, _ = full(own + mal_peers)
    assert res2[0].idare_stats["peer"] is None


def test_default_types_are_all_three():
    assert cli.DEFAULT_TYPES == ["mal", "hizmet", "yapim"]
    assert cli.parse_types(cli.DEFAULT_TYPES) == ["mal", "hizmet", "yapim"]
