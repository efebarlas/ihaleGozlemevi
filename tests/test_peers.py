import pytest

from ihale.peers import PROVINCES, idare_turu, il_of, locative_ki, peer_label


def test_81_provinces_unique():
    assert len(PROVINCES) == 81 == len(set(PROVINCES))


@pytest.mark.parametrize("name,turu", [
    ("ANTALYA BÜYÜKŞEHİR BELEDİYESİ", "belediye"),
    ("ANKARA ÜNİVERSİTESİ REKTÖRLÜĞÜ", "üniversite"),
    ("HACETTEPE ÜNİVERSİTESİ HASTANELERİ", "üniversite"),          # order: üniversite before hastane
    ("ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ MANAVGAT DEVLET HASTANESİ", "sağlık"),
    ("İZSU SU VE KANALİZASYON İDARESİ", "su-kanalizasyon"),
    ("JANDARMA GENEL KOMUTANLIĞI", "güvenlik"),
    ("İSTANBUL EMNİYET MÜDÜRLÜĞÜ", "güvenlik"),
    ("KONYA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜ", "eğitim"),
    ("KONYA İL MİLLİ EĞİTİM MÜDÜRLÜĞÜ", "eğitim"),
    ("ATATÜRK İLKOKULU MÜDÜRLÜĞÜ", "eğitim"),
    ("KARAYOLLARI 5. BÖLGE MÜDÜRLÜĞÜ", "karayolları"),
    ("DSİ 12. BÖLGE MÜDÜRLÜĞÜ", "dsi"),
    ("DEVLET SU İŞLERİ GENEL MÜDÜRLÜĞÜ", "dsi"),
    ("TÜRKİYE ELEKTRİK İLETİM A.Ş.", "diğer"),
    ("MODSİ HOLDING", "diğer"),                                       # 'dsi' only as a whole word
    ("belediye başkanlığı", "belediye"),
    ("", "diğer"), (None, "diğer"),
])
def test_idare_turu(name, turu):
    assert idare_turu(name) == turu


@pytest.mark.parametrize("name,il", [
    ("ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ", "Antalya"),
    ("İZMİR BÜYÜKŞEHİR BELEDİYESİ", "İzmir"),
    ("İzmir Büyükşehir Belediyesi", "İzmir"),
    ("izmir il özel idaresi", "İzmir"),
    ("ŞANLIURFA BÜYÜKŞEHİR BELEDİYESİ", "Şanlıurfa"),
    ("ISPARTA BELEDİYESİ", "Isparta"),
    ("IĞDIR ÜNİVERSİTESİ", "Iğdır"),
    ("AYDIN ADNAN MENDERES ÜNİVERSİTESİ", "Aydın"),
    ("ANTALYA'NIN İMAR VE ŞEHİRCİLİK", "Antalya"),
    ("KAHRAMANMARAŞ SÜTÇÜ İMAM ÜNİVERSİTESİ", "Kahramanmaraş"),
    ("MARAŞ BELEDİYESİ", "Kahramanmaraş"),
])
def test_il_of(name, il):
    assert il_of(name) == il


@pytest.mark.parametrize("name", [
    "ANKARA İZMİR ORTAK İDARESİ",            # two provinces → unknown
    "ANKARA VE ANKARA BELEDİYESİ" + " İZMİR",
    "AYDINLATMA GENEL MÜDÜRLÜĞÜ",              # 'aydın' inside a longer word is not Aydın
    "KOORDİNASYON KURULU",                     # 'ordu' fragment
    "SAĞLIK BAKANLIĞI", "", None,
])
def test_il_unknown(name):
    assert il_of(name) is None


def test_same_province_twice_is_still_one():
    assert il_of("GAZİANTEP GAZİANTEP BELEDİYESİ") == "Gaziantep"
    assert il_of("GAZİANTEP ANTEP ÜNİVERSİTESİ") == "Gaziantep"


@pytest.mark.parametrize("place,s", [
    ("Antalya", "Antalya'daki"), ("İzmir", "İzmir'deki"), ("Tokat", "Tokat'taki"), ("Muş", "Muş'taki"),
    ("Van", "Van'daki"), ("Rize", "Rize'deki"), ("Çorum", "Çorum'daki"), ("Kars", "Kars'taki"),
    ("Elazığ", "Elazığ'daki"), ("Kocaeli", "Kocaeli'deki"), ("Türkiye", "Türkiye'deki"),
    ("Eskişehir", "Eskişehir'deki"), ("Zonguldak", "Zonguldak'taki"), ("Hakkari", "Hakkari'deki")])
def test_locative(place, s):
    assert locative_ki(place) == s


def test_labels():
    assert peer_label("turu_il", "sağlık", "Antalya", "mal") == "Antalya'daki sağlık idareleri (mal)"
    assert peer_label("turu_il", "belediye", "İzmir", "yapim") == "İzmir'deki belediyeler (yapım)"
    assert peer_label("turu", "üniversite", None, "hizmet") == "Türkiye'deki üniversiteler (hizmet)"
    assert peer_label("sector", "diğer", None, "mal") == "Tüm idareler (mal)"
