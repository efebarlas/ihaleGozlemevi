from datetime import date

from ihale.flags import compute_flags
from ihale.model import Money
from ihale.store import StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)
SAGLIK = "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ"


def run(*recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    out = compute_flags(stored)
    return [out[s.id] for s in stored]


def mk(i, idare, ratio, usul="Açık", **kw):
    r = rec(1, ikn=f"2026/{i}", idare=idare, yuklenici=f"Firma {i}", bedel=ratio * 100.0, maliyet=100.0, **kw)
    r.ihale_usulu = usul
    return r


def peers_ratio(n, ratio_fn, fmt="MUĞLA İL SAĞLIK MÜDÜRLÜĞÜ {}", usul="Açık", start=1000):
    return [mk(start + i, fmt.format(i), ratio_fn(i), usul) for i in range(n)]


def test_ratio_present_for_every_record_not_only_flagged():
    a, b = run(mk(1, SAGLIK, 0.5), mk(2, "X KURUMU", 0.98))
    assert a.indicators["bedel_orani"] == 0.5 and "bedel_orani" not in [f["code"] for f in a.flags]
    assert b.indicators["bedel_orani"] == 0.98 and "bedel_orani" in [f["code"] for f in b.flags]


def test_ratio_is_the_same_number_the_flag_uses():
    (a,) = run(mk(1, SAGLIK, 0.9731))
    assert a.indicators["bedel_orani"] == a.flags[0]["value"]


def test_ratio_null_when_not_computable():
    r = mk(1, SAGLIK, 0.5)
    r.sozlesme_bedeli = Money(1000, "EUR")
    (a,) = run(r)
    assert a.indicators["bedel_orani"] is None and a.indicators["bedel_orani_peer_median"] is None
    (b,) = run(mk(1, SAGLIK, 0.5, conf={"sozlesme_bedeli": 0.1}))
    assert b.indicators["bedel_orani"] is None
    (c,) = run(mk(1, SAGLIK, 0.5, conf={"yaklasik_maliyet": 0.1}))
    assert c.indicators["bedel_orani"] is None


def test_kismi_ratio_is_the_sum_over_lots():
    lots = [rec(i, ikn="2026/9", yuklenici=f"F{i}", bedel=30.0, maliyet=100.0) for i in (1, 2, 3)]
    assert run(*lots)[0].indicators["bedel_orani"] == 0.9


def test_peer_median_needs_20_and_excludes_own_idare():
    own = mk(1, SAGLIK, 0.99)
    p19 = peers_ratio(19, lambda i: 0.5)
    ind19 = run(own, *p19)[0].indicators
    assert ind19["bedel_orani_peer_median"] is None and ind19["bedel_orani_peer_n"] is None
    p20 = peers_ratio(20, lambda i: 0.5 if i < 10 else 0.7)                       # median 0.6
    i20 = run(own, *p20)[0].indicators
    assert i20["bedel_orani_peer_median"] == 0.6 and i20["bedel_orani_peer_n"] == 20
    own2 = mk(2, SAGLIK, 0.1)                                                     # own idare's other award: excluded
    assert run(own, own2, *p20)[0].indicators["bedel_orani_peer_n"] == 20


def test_peer_median_uses_the_same_procedure_chain():
    own = mk(1, SAGLIK, 0.99, usul="4734 / 3-g")
    other_usul = peers_ratio(30, lambda i: 0.2, usul="Açık")
    assert run(own, *other_usul)[0].indicators["bedel_orani_peer_median"] is None
    same = peers_ratio(25, lambda i: 0.8, usul="4734 / 3-g", start=2000)
    i = run(own, *other_usul, *same)[0].indicators
    assert i["bedel_orani_peer_median"] == 0.8 and i["bedel_orani_peer_n"] == 25


def test_peer_chain_falls_back_from_il_to_turu():
    own = mk(1, SAGLIK, 0.99)
    local = peers_ratio(10, lambda i: 0.4, fmt="ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ ŞUBE {}", start=100)
    national = peers_ratio(12, lambda i: 0.6, start=300)
    i = run(own, *local, *national)[0].indicators
    assert i["bedel_orani_peer_n"] == 22 and i["bedel_orani_peer_median"] == 0.6   # 10x0.4 + 12x0.6 → median 0.6


def test_dmo_is_scored_like_any_idare_with_a_peer_median():
    dmo = mk(1, "DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ", 0.99, usul="4734 / 3-g")
    peers = peers_ratio(30, lambda i: 0.5, usul="4734 / 3-g", fmt="DEVLET MALZEME OFİSİ ŞUBE {}")   # DMO group peers
    i = run(dmo, *peers)[0].indicators
    assert i["bedel_orani"] == 0.99 and i["bedel_orani_peer_median"] == 0.5 and i["bedel_orani_peer_n"] == 30


def test_no_threshold_in_exported_texts():
    (a,) = run(mk(1, SAGLIK, 0.98))
    blob = repr([a.flags, a.indicators, a.idare_stats, a.structural])
    assert "0.97" not in blob and "0,97" not in blob and "eşik" not in blob.lower()
