import logging
from datetime import date, timedelta

import pytest

from ihale.flags import compute_flags
from ihale.indicators import acik_olmayan, elenen_orani, karar_suresi_gun, usul_turu
from ihale.store import StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)
IDARE = "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ"


def run(*recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    out = compute_flags(stored)
    return [out[s.id].indicators for s in stored]


# ---------------------------------------------------------------- usul_turu
@pytest.mark.parametrize("usul,code,non_open", [
    ("Açık", "acik", False),
    ("AÇIK", "acik", False),
    ("Belli İstekliler Arasında", "belli_istekliler", False),
    ("Pazarlık (MD 21 B)", "pazarlik_21b", True),
    ("Pazarlık (MD 21 F)", "pazarlik_21f", True),
    ("Pazarlık (MD 21 A)", "pazarlik_21a", True),
    ("4734 / 3-g", "istisna_3g", True),
    ("4734 / 3-a", "istisna_3a", True),
    ("Doğrudan Temin (MD 22 D)", "dogrudan_temin_22d", True),
    ("Doğrudan Temin", "dogrudan_temin", True),
    ("Pazarlık", "diger", True),
    ("Bir şey", "diger", True),
])
def test_usul_turu_mapping(usul, code, non_open):
    assert usul_turu(usul) == code
    assert acik_olmayan(code) is non_open


def test_usul_empty():
    assert usul_turu(None) is None and usul_turu("  ") is None and acik_olmayan(None) is None


def test_usul_unconfident_gives_null():
    (i,) = run(rec(1, conf={"ihale_usulu": 0.3}))
    assert i["usul_turu"] is None and i["acik_olmayan"] is None
    (j,) = run(rec(1))
    assert j["usul_turu"] == "acik" and j["acik_olmayan"] is False


# ---------------------------------------------------------------- elenen_orani
@pytest.mark.parametrize("toplam,gecerli,expected", [
    (1, 1, None), (1, 0, None), (2, 2, 0.0), (2, 1, 0.5), (4, 1, 0.75), (4, 0, 1.0),
    (None, 1, None), (2, None, None), (2, 3, None)])
def test_elenen_orani_boundaries(toplam, gecerli, expected):
    assert elenen_orani(toplam, gecerli) == expected


def test_elenen_orani_needs_confident_counts():
    (i,) = run(rec(1, toplam=4, gecerli=1, conf={"gecerli_teklif": 0.2}))
    assert i["elenen_orani"] is None
    (j,) = run(rec(1, toplam=4, gecerli=1))
    assert j["elenen_orani"] == 0.75


def test_elenen_peer_mean_needs_five_eligible_peers_and_excludes_own_idare():
    own = rec(1, ikn="2026/1", toplam=4, gecerli=3, idare=IDARE, yuklenici="A")        # 0.25
    peers4 = [rec(1, ikn=f"2026/{10 + i}", toplam=2, gecerli=1, idare=f"MUĞLA İL SAĞLIK {i}", yuklenici=f"P{i}")
              for i in range(4)]
    assert run(own, *peers4)[0]["elenen_orani_peer"] is None                  # 4 < 5
    peers5 = peers4 + [rec(1, ikn="2026/99", toplam=2, gecerli=2, idare="MUĞLA İL SAĞLIK 9", yuklenici="P9")]
    i = run(own, *peers5)[0]
    assert i["elenen_orani_peer"] == pytest.approx(0.4) and i["elenen_orani_peer_n"] == 5   # (4*.5 + 0)/5
    # awards with a single bid are not eligible
    singles = [rec(1, ikn=f"2026/{200 + k}", toplam=1, gecerli=1, idare=f"MUĞLA İL SAĞLIK S{k}", yuklenici=f"S{k}")
               for k in range(10)]
    assert run(own, *peers4, *singles)[0]["elenen_orani_peer"] is None


# ---------------------------------------------------------------- karar_suresi_gun
def test_karar_suresi_boundaries():
    assert karar_suresi_gun(date(2026, 10, 21), date(2026, 11, 16)) == 26
    assert karar_suresi_gun(date(2026, 10, 21), date(2026, 10, 21)) == 0
    assert karar_suresi_gun(date(2026, 10, 21), date(2026, 10, 20)) is None
    assert karar_suresi_gun(None, date(2026, 10, 20)) is None


def test_negative_decision_period_is_null_with_warning(caplog):
    r = rec(1)
    r.ihale_tarihi, r.sozlesme_tarihi = date(2026, 11, 10), date(2026, 11, 1)
    with caplog.at_level(logging.WARNING, logger="ihale"):
        (i,) = run(r)
    assert i["karar_suresi_gun"] is None and "before ihale_tarihi" in caplog.text


def test_karar_suresi_unconfident_dates():
    (i,) = run(rec(1, conf={"sozlesme_tarihi": 0.1}))
    assert i["karar_suresi_gun"] is None
    (j,) = run(rec(1))
    assert j["karar_suresi_gun"] == 26


# ---------------------------------------------------------------- yuklenici_payi
def awards(n, *, winner_every=2, bedel=100.0, start=0, day=D):
    """n awards of one idare; every `winner_every`-th goes to 'Baskın Ltd. Şti.', others to distinct firms."""
    return [rec(1, day=day, ikn=f"2026/{start + i}", idare=IDARE, bedel=bedel,
                yuklenici="Baskın Ltd. Şti." if i % winner_every == 0 else f"Firma {i}") for i in range(n)]


def test_payi_requires_five_awards():
    four = run(*awards(4))
    assert four[0]["yuklenici_payi"] is None and four[0]["yuklenici_payi_n"] == 4
    five = run(*awards(5))
    assert five[0]["yuklenici_payi_n"] == 5 and five[0]["yuklenici_payi"] == pytest.approx(0.6)   # 3 of 5 awards


def test_payi_is_share_of_try_value():
    recs = awards(5)
    recs[0].sozlesme_bedeli = recs[0].sozlesme_bedeli.__class__(100_000, "TRY")     # 1000.00 vs 4 x 100.00
    out = run(*recs)
    assert out[0]["yuklenici_payi"] == pytest.approx((1000 + 100 + 100) / (1000 + 400), abs=1e-3)   # winner owns i=0,2,4


def test_payi_ignores_non_try_and_unconfident_bedel_in_the_sums_but_counts_the_award():
    recs = awards(5)
    recs[1].sozlesme_bedeli = recs[1].sozlesme_bedeli.__class__(5_000_000, "EUR")
    recs[3].confidence["sozlesme_bedeli"] = 0.2
    out = run(*recs)
    assert out[0]["yuklenici_payi_n"] == 5
    assert out[0]["yuklenici_payi"] == pytest.approx(300 / 300)       # only awards 0, 2, 4 count, all the winner


def test_payi_window_365_days():
    old = awards(5, start=100, day=D - timedelta(days=366))
    new = awards(4, start=0)
    out = run(*(new + old))
    assert out[0]["yuklenici_payi_n"] == 4 and out[0]["yuklenici_payi"] is None     # old ones fall outside
    edge = awards(5, start=100, day=D - timedelta(days=365))
    assert run(*(new + edge))[0]["yuklenici_payi_n"] == 9


def test_payi_kismi_lots_are_one_award_but_values_sum():
    lots = [rec(i, ikn="2026/7", idare=IDARE, yuklenici="A", bedel=10.0) for i in range(1, 7)]
    out = run(*lots)
    assert out[0]["yuklenici_payi_n"] == 1 and out[0]["yuklenici_payi"] is None


def test_payi_null_without_confident_idare_or_yuklenici():
    (a,) = run(rec(1, conf={"idare": 0.1}))
    assert a["yuklenici_payi"] is None and a["yuklenici_payi_n"] is None
    recs = awards(5)
    recs[0].confidence["yuklenici"] = 0.1
    assert run(*recs)[0]["yuklenici_payi"] is None
