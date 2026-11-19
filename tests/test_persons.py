"""Natural-person masking rule (SPEC §6.1): biased towards masking."""
import pytest

from ihale.sitegen.persons import is_joint_venture, is_natural_person

PERSONS = [
    "Mustafa Öz",
    "Yurdakul Bostancı",
    "Selim Karataş İnşaat Mühendislik",                    # sole-proprietor trade name
    "Kurtuluş Kocaman Kurtuluş Medikal",
    "Volkan Gönültaş 4D Elektronik Medikal Sistemler",
    "Ahmet Yılmaz İnşaat Taahhüt Sanayi Ticaret",         # business words are not legal forms
    "Fatih Orman, Bünyamin Sertkaya İş Ortaklığı",          # JV of persons
    "Sinan Sayında - Harun Yıldırım İş Ortaklığı",
    "Sercan Kurumsal Yapı İnşaat Taahhüt San. Tic. A.Ş., Abdullah Üçeş İş Ortaklığı",  # JV with a person
    "Karataş",                                              # one word, no legal form: masked
]
COMPANIES = [
    "Emir Sosyal Hizmetler Limited Şirketi",
    "Kale Makina Pazarlama Anonim Şirketi",
    "Fresenıus Medikal Hizmetler Anonim Şirketi",
    "Ahmet Demirel Orman Ürünleri Emprenye İnşaat Nakliye ve Otomotiv San. Tic. Ltd. Şti.",
    "Integral Mühendislik İnşaat San. Tic. A.Ş.",
    "ABC Yapı Ltd.Şti.",
    "Örnek Tarım Kalkınma Kooperatifi",
    "Siemens Healthcare GmbH",
    "Ankara Büyükşehir Belediyesi",
    "X İnşaat A.Ş., Y Yapı Ltd. Şti. İş Ortaklığı",           # JV of companies only
]


@pytest.mark.parametrize("name", PERSONS)
def test_persons_are_masked(name):
    assert is_natural_person(name), name


@pytest.mark.parametrize("name", COMPANIES)
def test_companies_are_not_masked(name):
    assert not is_natural_person(name), name


def test_empty_and_jv_detection():
    assert not is_natural_person(None) and not is_natural_person("  ")
    assert is_joint_venture("A Ltd. Şti., B A.Ş. İş Ortaklığı")
    assert not is_joint_venture("Kale Makina Pazarlama Anonim Şirketi")
