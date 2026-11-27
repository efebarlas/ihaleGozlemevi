"""M5h: structural categories get their own peer group (points are not zeroed)."""
from test_structural import DMO, G, background, mk, run

from ihale import indicators as ind
from ihale import structural

MEB = "ANKARA İL MİLLİ EĞİTİM MÜDÜRLÜĞÜ ETİMESGUT İLÇE MİLLİ EĞİTİM MÜDÜRLÜĞÜ"


def test_peer_category_matching_is_narrow():
    assert structural.peer_category(DMO, "KONYA İLİ SAĞLIK MARKET AĞUSTOS 2026 İLAÇ ALIMI") == "saglik_market"
    assert structural.peer_category(DMO, "ANKARA İLİ A GRUBU TIBBİ SARF MALZEME ALIMI") is None
    assert structural.peer_category(DMO, "VAN İLİ J0952 - DİNOPROSTON 10MG OVÜL TALEP TOPLAMA") == "saglik_market"
    assert structural.peer_category(DMO, "ANKARA İLİ 6 AYLIK AROMASIZ ENTERAL ÜRÜN İHALESİ") == "saglik_market"
    assert structural.peer_category(DMO, "GİRESUN İLİ 7 KALEM İLAÇ (J0269-J3807) TALEP TOPLAMA") == "saglik_market"
    assert structural.peer_category(DMO, "IĞDIR İLİ SMT4043-İLAÇ HAZNESİ, VİBRONİK ALIMI") is None
    assert structural.peer_category("KONYA ŞEHİR HASTANESİ", "SAĞLIK MARKET") is None             # needs DMO
    t = "ARAÇ KİRALAMA HİZMETİ ALINACAKTIR 2026-2027 Eğitim Öğretim Yılı Ortaöğretim Taşıma Hizmeti Alımı"
    assert structural.peer_category(MEB, t) == "meb_tasima"
    assert structural.peer_category(MEB, "2026-2027 Eğitim Öğretim Yılı Taşımalı Eğitim Kapsamındaki Öğrenciler") == "meb_tasima"
    assert structural.peer_category(MEB, "ARAÇ KİRALAMA HİZMETİ ALINACAKTIR Öğretmenevi şoförlü araç") is None
    assert structural.peer_category(MEB, "Taşımalı Eğitim Yemek Taşıma İşi") is None            # meals are not student transport
    assert structural.peer_category("KONYA BELEDİYESİ", t) is None                               # needs a MEB idare
    assert structural.peer_category(None, t) is None and structural.peer_category(MEB, None) is None


def test_usul_group_and_label_for_categories():
    assert ind.usul_group(DMO, "istisna_3g", "X SAĞLIK MARKET Y") == "saglik_market"
    assert ind.usul_group(DMO, "istisna_3g", "1 ADET JENERATÖR") == "istisna_3g_dmo"          # unchanged
    assert ind.usul_group(MEB, "acik", "Taşımalı Eğitim") == "meb_tasima"
    assert ind.usul_group(MEB, None, "Taşımalı Eğitim") is None                                # unknown usul stays unknown
    assert ind.usul_label("saglik_market") == "DMO sağlık ve ilaç"
    assert ind.usul_label("meb_tasima") == "MEB taşımalı eğitim / araç kiralama"


def test_category_has_its_own_rates_and_label_but_keeps_points():
    def market(i, tek):
        r = mk(i, DMO, G, toplam=1 if tek else 3, gecerli=1 if tek else 3, yuklenici=f"M{i}")
        r.title = "KONYA İLİ SAĞLIK MARKET AĞUSTOS 2026 İLAÇ ALIMI"
        return r
    recs = [market(i, tek=i < 60) for i in range(80)] + background()          # market: 75% single bid
    out = run(*recs)
    a = out[0]
    assert a.usul_group == "mal/saglik_market"
    assert a.idare_stats["usul_label"] == "DMO sağlık ve ilaç"
    other = out[100]                                                           # background open tender
    assert other.usul_group == "mal/acik"
    # single bids are the norm in the market group: far less surprising than in the open-tender background
    open_tek = next(r for r in out[80:] if "tek_teklif" in r.part_codes)
    pa = next(p for p in a.score_parts if p["code"] == "tek_teklif")
    pb = next(p for p in open_tek.score_parts if p["code"] == "tek_teklif")
    assert pa["p"] > pb["p"] and pa["p_group"] == "mal/saglik_market"


def test_delete_override_is_per_run_and_default_off(monkeypatch):
    import pytest
    from ihale.sitegen import _delete_override
    monkeypatch.delenv("IHALE_MAX_DELETE_FRACTION", raising=False)
    assert _delete_override(lambda m: None) == {}                       # normal 5% guard
    monkeypatch.setenv("IHALE_MAX_DELETE_FRACTION", "0.08")
    logs = []
    assert _delete_override(logs.append) == {"max_delete_fraction": 0.08} and "override" in logs[0]
    monkeypatch.setenv("IHALE_MAX_DELETE_FRACTION", "0.9")
    with pytest.raises(ValueError):
        _delete_override(lambda m: None)


def test_dmo_arac_group_is_the_i_nolu_unit():
    i_nolu = "DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ I NOLU SATIN ALMA DAİRE BAŞKANLIĞI"
    v_nolu = "DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ V NOLU SATIN ALMA DAİRE BAŞKANLIĞI"
    assert structural.peer_category(i_nolu, "SATIH KAPLAMA ARACI") == "dmo_arac"
    assert structural.peer_category(v_nolu, "SATIH KAPLAMA ARACI") is None
    assert structural.peer_category("DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ III NOLU SATIN ALMA", "X") is None
    assert structural.peer_category(i_nolu, "VAN İLİ J0952 DİNOPROSTON") == "saglik_market"        # health wins
    assert ind.usul_label("dmo_arac") == "DMO araç ve iş makinesi siparişleri"


# ---------------------------------------------------------------- kalem bazlı (item-based per-supplier notices)

def test_kalem_bazli_ratio_not_computable_like_currency_mismatch():
    from datetime import date
    from ihale import flags as F
    from ihale.store import StoredRecord
    from rec_helpers import rec, money
    d = date(2026, 11, 18)
    split = rec(1, day=d, ikn="2026/900", bedel=20_000.0, maliyet=9_000_000.0, toplam=30, gecerli=29)
    split.esas_kisim_yaklasik_maliyet = money(9_000_000.0)
    split.confidence["esas_kisim_yaklasik_maliyet"] = 1.0
    real_low = rec(1, day=d, ikn="2026/901", bedel=20_000.0, maliyet=9_000_000.0, toplam=30, gecerli=29)
    real_low.esas_kisim_yaklasik_maliyet = money(50_000.0)            # own share printed: measurable
    real_low.confidence["esas_kisim_yaklasik_maliyet"] = 1.0
    few_bids = rec(1, day=d, ikn="2026/902", bedel=20_000.0, maliyet=9_000_000.0, toplam=3, gecerli=3)
    near = rec(1, day=d, ikn="2026/903", bedel=99.0, maliyet=100.0, toplam=6, gecerli=6)    # fires bedel_orani
    stored = [StoredRecord(id=i, record=r) for i, r in enumerate([split, real_low, few_bids, near], 1)]
    res, rates = F.compute_flags_full(stored)
    s = res[1]
    assert s.indicators["bedel_orani"] is None and s.indicators["bedel_orani_not_comparable"] is True
    assert "bedel_orani" not in s.computable and s.indicators["bedel_orani_peer_median"] is None
    assert {"field": "sozlesme_bedeli", "reason": F.KALEM_BAZLI} in s.unreadable
    assert res[2].indicators["bedel_orani_not_comparable"] is False and res[2].indicators["bedel_orani"] == 0.4
    assert res[3].indicators["bedel_orani_not_comparable"] is False and "bedel_orani" in res[3].computable
    assert "bedel_orani" in res[4].score_parts or any(f["code"] == "bedel_orani" for f in res[4].flags)
    assert rates["mal/hepsi"]["n_computable"]["bedel_orani"] == 3           # the split record left the denominator
    assert F.kalem_bazli(split, 0.29) and not F.kalem_bazli(split, 0.30)


def test_bedel_line_says_not_comparable():
    from ihale import sitegen
    t = {"indicators": {"bedel_orani": None, "bedel_orani_not_comparable": True}}
    assert sitegen.bedel_line(t).startswith("karşılaştırılamaz (kalem bazlı ilan")
    assert sitegen.bedel_peer_line(t) is None
