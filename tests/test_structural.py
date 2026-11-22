"""Structural single-bid table (§4.1.1): only `istisna-3e` is in it; DMO is scored like any other idare."""
import json
from datetime import date

from ihale import structural
from ihale.export import export_all
from ihale.flags import compute_flags_full
from ihale.store import Store, StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)
DMO = "DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ V NOLU SATIN ALMA ŞUBESİ"
G, E3 = "4734 / 3-g", "4734 / 3-e"
REASON_3E = ("4734 sayılı Kanun md. 3/e: alım, Kanunda adı sayılan kamu kuruluşundan (ör. ceza infaz kurumu "
             "işyurtları, DMO, TCDD, Et ve Balık Kurumu) yapılır; tek tedarikçi Kanun gereğidir.")


def run(*recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    out, _ = compute_flags_full(stored)
    return [out[s.id] for s in stored]


def mk(i, idare, usul, *, toplam=1, gecerli=1, bedel=50.0, maliyet=200.0, yuklenici="A", day=D):
    r = rec(i, day=day, ikn=f"2026/{i}", idare=idare, yuklenici=yuklenici, toplam=toplam, gecerli=gecerli,
            bedel=bedel, maliyet=maliyet)
    r.ihale_usulu = usul
    return r


def background(n=150, tek_n=15, start=1000):
    """Open-tender background so that part rates are small and points positive."""
    return [mk(start + i, f"ARKA PLAN KURUMU {i}", "Açık", toplam=1 if i < tek_n else 3,
               gecerli=1 if i < tek_n else 3, yuklenici=f"B{i}") for i in range(n)]


def codes(res):
    return [f["code"] for f in res.flags]


def test_table_has_only_istisna_3e():
    assert [r.id for r in structural.RULES] == ["istisna-3e"]
    assert structural.match(DMO, "istisna_3g") is None             # DMO is no longer special
    assert structural.match(DMO, "acik") is None


def test_match_3e_any_idare():
    assert structural.match("HERHANGİ BİR İDARE", "istisna_3e").id == "istisna-3e"
    assert structural.match("ADALET BAKANLIĞI CEZA İNFAZ KURUMU İŞYURTLARI", "istisna_3e").id == "istisna-3e"
    assert structural.match("HERHANGİ BİR İDARE", "istisna_3g") is None
    assert structural.match("X", "istisna_3a") is None
    assert structural.match(None, "istisna_3e") is None and structural.match("X", None) is None


def test_dmo_3g_is_scored_like_any_idare():
    recs = [mk(1, DMO, G, bedel=99.0, maliyet=100.0)] + [mk(100 + i, f"ÖBÜR KURUM {i}", G, toplam=3, gecerli=3,
                                                              yuklenici=f"P{i}") for i in range(150)]
    a = run(*recs)[0]
    assert codes(a) == ["tek_teklif", "bedel_orani"]
    assert [p["code"] for p in a.score_parts] == ["tek_teklif", "bedel_orani"] and a.score > 0
    assert a.structural is None


def test_dmo_gets_a_peer_group_and_can_fire_idare_orani():
    own = [mk(i, DMO, G) for i in range(6)]
    peers = [mk(100 + i, f"DEVLET MALZEME OFİSİ ŞUBE {i}", G, toplam=3, gecerli=3, yuklenici=f"P{i}") for i in range(30)]
    a = run(*own, *peers)[0]
    st = a.idare_stats
    assert st["usul_turu"] == "istisna_3g_dmo" and st["usul_label"] == "4734/3-g (DMO)"
    assert st["peer"] is not None and "peer_note" not in st and st["records"] == 6
    assert "idare_orani" in a.part_codes


def test_3e_single_bid_keeps_flags_but_no_points():
    recs = [mk(1, "ADALET BAKANLIĞI CEZA İNFAZ KURUMU İŞYURTLARI", E3)] + background()
    a = run(*recs)[0]
    assert codes(a) == ["tek_teklif"] and a.score_parts == [] and a.score == 0.0
    assert a.structural == {"id": "istisna-3e", "text": REASON_3E}


def test_3e_diger_teklifler_elendi_gets_no_points_and_other_parts_count():
    recs = [mk(1, "KURUM A", E3, toplam=4, gecerli=1, bedel=99.0, maliyet=100.0)] + background()
    a = run(*recs)[0]
    assert codes(a) == ["diger_teklifler_elendi", "bedel_orani"]
    assert [p["code"] for p in a.score_parts] == ["bedel_orani"]


def test_tekrarlayan_needs_a_non_excluded_partner_part_for_3e():
    recs = [mk(i, "KURUM A", E3) for i in range(3)] + background()          # same yüklenici, 3 ikns, single bids
    last = run(*recs)[2]
    assert "tekrarlayan_yuklenici" in codes(last) and last.score_parts == []
    paired = [mk(i, "KURUM A", E3, bedel=99.0, maliyet=100.0) for i in range(3)] + background()
    assert [p["code"] for p in run(*paired)[2].score_parts] == ["bedel_orani", "tekrarlayan_eslesik"]


def test_unconfident_idare_or_usul_never_matches():
    r = mk(1, "KURUM A", E3)
    r.confidence["ihale_usulu"] = 0.2
    assert run(r)[0].structural is None


def test_own_peer_group_mechanism_still_works_for_a_future_rule(monkeypatch):
    rule = structural.Rule(id="test", prefix="ÖZEL KURUM", usul_turu="acik",
                           effects=(structural.NO_SINGLE_BID_POINTS, structural.OWN_PEER_GROUP),
                           reason_tr="deneme", match_tr="deneme", added="2026-01-01")
    monkeypatch.setattr(structural, "RULES", (rule,))
    own = [mk(i, "ÖZEL KURUM GM", "Açık") for i in range(6)]
    peers = [mk(100 + i, f"KONYA BELEDİYESİ {i}", "Açık", toplam=3, gecerli=3, yuklenici=f"P{i}") for i in range(30)]
    a = run(*own, *peers)[0]
    assert a.idare_stats["peer"] is None and a.idare_stats["peer_note"] == "Kendi geçmişiyle karşılaştırılır"
    assert "idare_orani" not in a.part_codes and a.score_parts == []


def test_export_carries_structural_and_meta_rules():
    Store().replace_day(D, "mal", [mk(1, "KURUM A", E3), mk(2, DMO, G, yuklenici="B")])
    from ihale.pipeline import flag_all
    s = Store()
    flag_all(s)
    out = export_all(s)
    day = json.loads((out / "days" / "2026-11-18.json").read_text(encoding="utf-8"))
    assert day["tenders"][0]["structural"] == {"id": "istisna-3e", "text": REASON_3E}
    assert day["tenders"][1]["structural"] is None
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    rule = meta["structural_rules"][0]
    assert set(rule) == {"id", "match_tr", "effects", "reason_tr", "added"}
    assert rule["id"] == "istisna-3e" and rule["effects"] == ["no_single_bid_points"]
    assert rule["reason_tr"] == REASON_3E and rule["added"] == "2026-11-19"
