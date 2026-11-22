"""Score (§4.1) and idare_stats."""
from datetime import date, timedelta

from ihale.flags import compute_flags
from ihale.store import StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)
SAGLIK = "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ"
SUBE = "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ ŞUBE {}"


def run(*recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    out = compute_flags(stored)
    return [out[s.id] for s in stored]


def codes(res):
    return [f["code"] for f in res.flags]


def mk(i, idare, tek, day=D, type_="mal"):
    return rec(1, day=day, type_=type_, ikn=f"2026/{i}", idare=idare, yuklenici=f"Firma {i}",
               toplam=1 if tek else 3, gecerli=1 if tek else 3)


def peers_of(n, tek_n, fmt="MUĞLA İL SAĞLIK MÜDÜRLÜĞÜ {}", start=1000, **kw):
    return [mk(start + i, fmt.format(i), i < tek_n, **kw) for i in range(n)]


def first(recs):
    return run(*recs)[0]


def test_score_parts_weights():
    a, b = run(rec(1, ikn="2026/1", gecerli=1, toplam=1, bedel=99.0, maliyet=100.0, yuklenici="X"),
               rec(1, ikn="2026/2", gecerli=3, yuklenici="Y"))
    assert a.part_codes == ["tek_teklif", "bedel_orani"]
    assert b.score == 0 and b.part_codes == []


def test_repeat_adds_two_only_with_another_flag():
    dates = [D - timedelta(days=2), D - timedelta(days=1), D]
    bare = run(*[rec(1, day=d, ikn=f"2026/{i}") for i, d in enumerate(dates)])[2]
    assert "tekrarlayan_yuklenici" in codes(bare) and bare.score == 0 and bare.part_codes == []
    comp = run(*[rec(1, day=d, ikn=f"2026/{i}", gecerli=1, toplam=1) for i, d in enumerate(dates)])[2]
    assert comp.part_codes == ["tek_teklif", "tekrarlayan_eslesik"]


def test_idare_orani_fires_with_local_peers():
    own = [mk(i, SAGLIK, True) for i in range(5)]
    a = first(own + peers_of(35, 7, fmt=SUBE))          # 20% tek among peers
    st = a.idare_stats
    assert st["records"] == 5 and st["tek_gecerli_teklif"] == 1.0
    assert st["idare_turu"] == "sağlık" and st["il"] == "Antalya" and st["window_days"] == 30
    assert st["peer"] == {"label": "Antalya'daki sağlık idareleri (mal, açık)", "records": 35, "tek_gecerli_teklif": 0.2}
    assert "idare_orani" in a.part_codes


def test_idare_below_minimum_sample_has_no_rate_and_no_part():
    a = first([mk(i, SAGLIK, True) for i in range(4)] + peers_of(30, 3, fmt=SUBE))
    assert a.idare_stats["records"] == 4 and a.idare_stats["tek_gecerli_teklif"] is None
    assert a.idare_stats["peer"]["records"] == 30
    assert "idare_orani" not in a.part_codes


def test_idare_share_must_be_double_peer_share():
    own = [mk(i, SAGLIK, i < 3) for i in range(5)]                 # 60%
    assert "idare_orani" not in first(own + peers_of(40, 14, fmt=SUBE)).part_codes    # peers 35%: 60 < 70
    assert "idare_orani" in first(own + peers_of(40, 12, fmt=SUBE)).part_codes        # peers 30%: 60 >= 60


def test_zero_rates_do_not_fire():
    a = first([mk(i, SAGLIK, False) for i in range(5)] + peers_of(35, 0, fmt=SUBE))
    assert a.idare_stats["tek_gecerli_teklif"] == 0.0 and "idare_orani" not in a.part_codes


def test_peer_fallback_chain_and_labels():
    own = [mk(i, SAGLIK, True) for i in range(5)]
    # 10 same turu+il (<30), 25 other-il sağlık → turu nationwide has 35
    group = peers_of(10, 1, fmt=SUBE) + peers_of(25, 3, start=2000)
    st = first(own + group).idare_stats
    assert st["peer"]["label"] == "Türkiye'deki sağlık idareleri (mal, açık)" and st["peer"]["records"] == 35
    # only non-sağlık peers → whole sector
    st = first(own + peers_of(32, 2, fmt="KONYA BELEDİYESİ {}", start=3000)).idare_stats
    assert st["peer"]["label"] == "Tüm idareler (mal, açık)" and st["peer"]["records"] == 32
    # nothing big enough → no peer, no idare_orani
    a = first(own + peers_of(5, 0, fmt="KONYA BELEDİYESİ {}", start=3000))
    assert a.idare_stats["peer"] is None and "idare_orani" not in a.part_codes


def test_unknown_il_skips_the_il_group():
    own = [mk(i, "SAĞLIK BAKANLIĞI", True) for i in range(5)]
    st = first(own + peers_of(35, 7)).idare_stats
    assert st["il"] is None and st["peer"]["label"] == "Türkiye'deki sağlık idareleri (mal, açık)"


def test_peers_exclude_the_idare_itself_and_other_sectors():
    own = [mk(i, SAGLIK, True) for i in range(6)]
    assert first(own + peers_of(30, 0, fmt=SUBE, type_="hizmet")).idare_stats["peer"] is None
    assert first(own + peers_of(30, 0, fmt=SUBE)).idare_stats["peer"]["records"] == 30


def test_window_is_30_days():
    old = [mk(i, SAGLIK, True, day=D - timedelta(days=30)) for i in range(5)]       # outside (d-30, d]
    new = [mk(100 + i, SAGLIK, True, day=D - timedelta(days=29)) for i in range(5)]
    res = run(*(old + new + [mk(900, SAGLIK, False)]))
    assert res[-1].idare_stats["records"] == 6        # 5 from day -29 plus itself
    assert res[0].idare_stats["records"] == 5         # the old ones see only their own window then


def test_kismi_lots_are_one_award():
    lots = [rec(i, ikn="2026/7", idare=SAGLIK, yuklenici=f"F{i}", bedel=1.0, maliyet=100.0, gecerli=1, toplam=1)
            for i in range(1, 30)]
    assert first(lots).idare_stats["records"] == 1


def test_idare_stats_none_without_confident_idare():
    (a,) = run(rec(1, conf={"idare": 0.2}))
    (b,) = run(rec(1, idare=None))
    assert a.idare_stats is None and b.idare_stats is None


def test_peer_group_minimum_is_30_and_falls_back_to_the_wider_group():
    from ihale.flags import PEER_MIN_N
    assert PEER_MIN_N == 30
    own = [mk(i, SAGLIK, True) for i in range(5)]
    wider = peers_of(10, 1, start=2000)                                   # other provinces, same turu: 10 more
    local29 = peers_of(29, 6, fmt=SUBE)
    st = first(own + local29 + wider).idare_stats                         # il group has 29 (< 30) → turu nationwide (39)
    assert st["peer"]["records"] == 39 and st["peer"]["label"].startswith("Türkiye'deki")
    st = first(own + local29[:-1] + peers_of(1, 0, fmt=SUBE, start=900) + peers_of(1, 0, fmt=SUBE, start=901)).idare_stats
    assert st["peer"]["records"] == 30 and st["peer"]["label"].startswith("Antalya'daki")   # exactly 30: local group


def test_bedel_peer_and_usul_pay_use_the_same_minimum():
    from ihale.flags import BEDEL_PEER_MIN_N
    from ihale.dosyalar import PEER_MIN_AWARDS
    assert BEDEL_PEER_MIN_N == PEER_MIN_AWARDS == 30
