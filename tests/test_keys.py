import unicodedata

import pytest

from ihale.keys import normalize_key, turkish_lower


def test_turkish_lower_dotted_dotless():
    assert turkish_lower("İSTANBUL") == "istanbul"
    assert turkish_lower("IŞIK") == "ışık"
    assert turkish_lower("İŞİK") == "işik"
    assert turkish_lower("Iı İi") == "ıı ii"
    assert "\u0307" not in turkish_lower("İ")


@pytest.mark.parametrize("a,b", [
    ("Emir Hizmetler Ltd. Şti.", "EMİR HİZMETLER LİMİTED ŞİRKETİ"),
    ("Emir Hizmetler LTD.ŞTİ.", "emir hizmetler limited şirketi"),
    ("Acme A.Ş.", "ACME ANONİM ŞİRKETİ"),
    ("Acme AŞ", "Acme A.Ş"),
    ("X San. ve Tic. Ltd. Şti.", "X Sanayi ve Ticaret Limited Şirketi"),
    ("X San. ve Tic. A.Ş.", "X SANAYİ VE TİCARET ANONİM ŞİRKETİ"),
    ("  Acme   \n Gıda  ", "ACME GIDA"),
    ("Acme-Gıda, (Ankara)", "acme gıda ankara"),
])
def test_equivalent_names_share_a_key(a, b):
    assert normalize_key(a) == normalize_key(b)


def test_expected_key_values():
    assert normalize_key("Emir Sosyal Hizmetler Limited Şirketi") == "emir sosyal hizmetler ltd"
    assert normalize_key("Acme Anonim Şirketi") == "acme as"
    assert normalize_key("Yılmaz San. ve Tic. A.Ş.") == "yılmaz san tic as"


def test_ampersand_kept():
    assert normalize_key("Arslan & Oğulları Ltd. Şti.") == "arslan & oğulları ltd"


@pytest.mark.parametrize("a,b", [
    ("Işık Ltd. Şti.", "İşik Ltd. Şti."),     # ı vs i are different letters
    ("Şahin Ltd. Şti.", "Sahin Ltd. Şti."),   # no ASCII folding
    ("Acme Ltd. Şti.", "Acme Anonim Şirketi"),
    ("Acme Gıda Ltd. Şti.", "Acme Ltd. Şti."),  # no fuzzy / partial matching
])
def test_no_false_merges(a, b):
    assert normalize_key(a) != normalize_key(b)


def test_person_names_intact_apart_from_case_and_whitespace():
    assert normalize_key("Mustafa ÖZ") == "mustafa öz"
    assert normalize_key("Yurdakul  Bostancı") == "yurdakul bostancı"
    assert normalize_key("İsmail IŞIK") == "ismail ışık"
    # a surname "Aş" must not be rewritten into a company suffix when it starts the name
    assert normalize_key("Aş Ahmet") == "aş ahmet"


def test_nfd_input_equals_nfc():
    s = "ŞİŞLİ Gıda Ltd. Şti. Çiğköfte"
    assert normalize_key(unicodedata.normalize("NFD", s)) == normalize_key(s)


def test_empty():
    assert normalize_key(None) is None
    assert normalize_key("") is None
    assert normalize_key(" . - ") is None
