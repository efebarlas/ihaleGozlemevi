from datetime import date

import pytest

from ihale import structural
from ihale.export import export_all
from ihale.flags import compute_flags
from ihale.store import Store, StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)
DMO = "DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ I NOLU SATIN ALMA ŞUBESİ"
G = "4734 / 3-g"
REASON = ("Devlet Malzeme Ofisi merkezî alım kurumudur; 4734/3-g kapsamındaki seri, markaya özgü alımlarında "
          "tek teklif yapısı gereğidir.")


def run(*recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    out = compute_flags(stored)
    return [out[s.id] for s in stored]


def mk(i, idare, usul, *, toplam=1, gecerli=1, bedel=50.0, maliyet=200.0, yuklenici="A", day=D):
    r = rec(i, day=day, ikn=f"2026/{i}", idare=idare, yuklenici=yuklenici, toplam=toplam, gecerli=gecerli,
            bedel=bedel, maliyet=maliyet)
    r.ihale_usulu = usul
    return r


def codes(res):
    return [f["code"] for f in res.flags]


def test_match_rules():
    assert structural.match(DMO, "istisna_3g").id == "dmo-3g"
    assert structural.match("devlet malzeme ofisi", "istisna_3g").id == "dmo-3g"       # Turkish casefold
    assert structural.match("  DEVLET   MALZEME  OFİSİ X", "istisna_3g").id == "dmo-3g"
    assert structural.match(DMO, "acik") is None
    assert structural.match(DMO, "istisna_3a") is None
    assert structural.match("ANKARA BELEDİYESİ", "istisna_3g") is None
    assert structural.match("T.C. DEVLET MALZEME OFİSİ", "istisna_3g") is None            # prefix, not substring
    assert structural.match(None, "istisna_3g") is None and structural.match(DMO, None) is None


def test_dmo_3g_keeps_flags_but_scores_only_from_bedel_orani():
    (a,) = run(mk(1, DMO, G, bedel=99.0, maliyet=100.0))
    assert codes(a) == ["tek_teklif", "bedel_orani"]            # both stay as shown facts
    assert a.part_codes == ["bedel_orani"]
    assert a.structural == {"id": "dmo-3g", "text": REASON}


def test_dmo_3g_diger_teklifler_elendi_adds_no_points():
    (a,) = run(mk(1, DMO, G, toplam=4, gecerli=1))
    assert codes(a) == ["diger_teklifler_elendi"] and a.score == 0 and a.part_codes == []


def test_tekrarlayan_needs_a_non_excluded_partner_flag():
    recs = [mk(i, DMO, G) for i in range(3)]                         # same yüklenici, 3 ikns, all tek teklif
    last = run(*recs)[2]
    assert "tekrarlayan_yuklenici" in codes(last) and last.score == 0 and last.part_codes == []
    bedel = [mk(i, DMO, G, bedel=99.0, maliyet=100.0) for i in range(3)]
    last = run(*bedel)[2]
    assert last.part_codes == ["bedel_orani", "tekrarlayan_eslesik"]


def test_own_peer_group_means_no_peer_and_no_idare_orani():
    own = [mk(i, DMO, G) for i in range(6)]
    peers = [mk(100 + i, f"KONYA BELEDİYESİ {i}", G, toplam=3, gecerli=3, yuklenici=f"P{i}") for i in range(30)]
    a = run(*own, *peers)[0]
    st = a.idare_stats
    assert st["peer"] is None and st["peer_note"] == "Kendi geçmişiyle karşılaştırılır"
    assert st["records"] == 6 and st["tek_gecerli_teklif"] == 1.0          # its own rate is still shown
    assert "idare_orani" not in a.part_codes


def test_dmo_with_other_usul_is_unaffected():
    (a,) = run(mk(1, DMO, "Açık"))
    assert a.structural is None and a.part_codes == ["tek_teklif"]
    own = [mk(i, DMO, "Açık") for i in range(6)]
    peers = [mk(100 + i, f"KONYA BELEDİYESİ {i}", "Açık", toplam=3, gecerli=3, yuklenici=f"P{i}") for i in range(30)]
    st = run(*own, *peers)[0]
    assert st.structural is None and "peer_note" not in st.idare_stats and "idare_orani" in st.part_codes


def test_non_dmo_idare_with_3g_is_unaffected():
    (a,) = run(mk(1, "ANKARA BELEDİYESİ", G))
    assert a.structural is None and a.part_codes == ["tek_teklif"]


def test_unconfident_idare_or_usul_never_matches():
    r = mk(1, DMO, G)
    r.confidence["idare"] = 0.2
    assert run(r)[0].structural is None
    r2 = mk(1, DMO, G)
    r2.confidence["ihale_usulu"] = 0.2
    assert run(r2)[0].structural is None


def test_export_carries_structural_and_meta_rules():
    import json
    from ihale import config
    Store().replace_day(D, "mal", [mk(1, DMO, G), mk(2, "ANKARA BELEDİYESİ", G, yuklenici="B")])
    from ihale.pipeline import flag_all
    s = Store()
    flag_all(s)
    out = export_all(s)
    day = json.loads((out / "days" / "2026-11-18.json").read_text(encoding="utf-8"))
    assert day["tenders"][0]["structural"] == {"id": "dmo-3g", "text": REASON}
    assert day["tenders"][1]["structural"] is None
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    rule = next(r for r in meta["structural_rules"] if r["id"] == "dmo-3g")
    assert [r["id"] for r in meta["structural_rules"]] == ["dmo-3g", "istisna-3e"]
    assert set(rule) == {"id", "match_tr", "effects", "reason_tr", "added"}
    assert rule["id"] == "dmo-3g" and rule["effects"] == ["no_single_bid_points", "own_peer_group"]
    assert rule["reason_tr"] == REASON and rule["added"] == "2026-11-19"
