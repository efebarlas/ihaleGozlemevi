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
