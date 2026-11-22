"""M5g: brand-specified DMO orders and municipality-owned winners (record-level structural rules)."""
from test_structural import DMO, G, D, background, codes, mk, run

from ihale import structural
from ihale.keys import normalize_key

ERZ = "ERZURUM BÜYÜKŞEHİR BELEDİYE BAŞKANLIĞI MALİ HİZMETLER DAİRESİ BAŞKANLIĞI"
ER_KONUT = "Er Konut İnşaat Taahhüt İnşaat Malzemeleri Nakliye ve Madencilik Ticaret ve Sanayi Anonim Şirketi"


def test_marka_belirli_needs_dmo_and_a_brand_word():
    assert structural.marka_belirli(DMO, "3 ADET ISUZU NOVOCİTİ LİFE A/T MİDİBÜS") == "isuzu"   # capital I folds to ı
    assert structural.marka_belirli(DMO, "1 ADET FORD TRUCKS 3545 D 6X4") == "ford"
    assert structural.marka_belirli(DMO, "1 ADET CASE CX220D 22 TON PALETLİ EKSKAVATÖR")
    assert structural.marka_belirli(DMO, "2 ADET HİTACHİ MARKA ZX 48U-6 MİNİ EKSKAVATÖR")
    assert structural.marka_belirli("ANKARA BELEDİYESİ", "1 ADET ISUZU D-MAX") is None          # not DMO
    assert structural.marka_belirli(DMO, "ANKARA İLİ B GRUBU TIBBİ SARF MALZEME ALIMI") is None
    assert structural.marka_belirli(DMO, "İŞ AYAKKABISI ALIMI") is None
    assert structural.marka_belirli(DMO, "AFYON İLİ KAYSERİ MUAYENE ELDİVENİ") is None         # no substring hits
    assert structural.marka_belirli(DMO, None) is None and structural.marka_belirli(None, "ISUZU") is None


def test_brand_order_keeps_flags_but_no_points():
    r = mk(1, DMO, G, bedel=99.0, maliyet=100.0)
    r.title = "1 ADET MERCEDES-BENZ ACTROS 1835L ŞASİ"
    plain = mk(2, DMO, G, bedel=99.0, maliyet=100.0)
    plain.title = "1 ADET JENERATÖR"
    res = run(r, plain, *background())
    a, p = res[0], res[1]
    assert {"tek_teklif", "bedel_orani"} <= set(codes(a))          # facts stay visible
    assert a.score == 0 and a.score_parts == []
    assert a.structural["id"] == "marka-belirli" and a.structural["marka_belirli"] is True
    assert p.score > 0 and p.structural is None                    # same idare, no brand: scored as before


def test_in_house_needs_same_municipality_and_a_listed_company():
    key = normalize_key(ER_KONUT)
    assert structural.in_house(ERZ, key).source_url.startswith("https://")
    assert structural.in_house("KOCAELİ BÜYÜKŞEHİR BELEDİYE BAŞKANLIĞI", key) is None       # other municipality
    assert structural.in_house(ERZ, normalize_key("Başka Konut Anonim Şirketi")) is None
    assert structural.in_house(None, key) is None and structural.in_house(ERZ, None) is None


def test_in_house_award_gets_no_single_or_repeat_points():
    recs = [mk(i, ERZ, "Açık", yuklenici=ER_KONUT) for i in range(1, 5)]      # 4 single-bid awards, same winner
    other = [mk(10 + i, "BAŞKA BELEDİYE BAŞKANLIĞI", "Açık", yuklenici="Özel A.Ş.") for i in range(4)]
    res = run(*recs, *other, *background())
    for a in res[:4]:
        assert a.structural["id"] == "belediye-sirketi" and a.structural["kaynak_url"]
        assert "tek_teklif" in codes(a)                                       # still shown
        assert not ({"tek_teklif", "tekrarlayan_eslesik"} & set(a.part_codes))
    assert any("tek_teklif" in b.part_codes for b in res[4:8])               # private winners still score


def test_rules_meta_lists_the_new_rules_with_sources():
    meta = {m["id"]: m for m in structural.rules_meta()}
    assert {"istisna-3e", "marka-belirli", "belediye-sirketi"} <= set(meta)
    assert "sayistay.gov.tr" in meta["belediye-sirketi"]["match_tr"]
