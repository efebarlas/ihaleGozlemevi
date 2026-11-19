"""Offline tests for the mal sonuç ilanları parser, run on the 12-page fixture excerpt."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ihale.model import CONFIDENT, CORE_FIELDS, Money, Record
from ihale.parse import parse_bulletin

FIXTURE = Path(__file__).parent / "fixtures" / "mal_sonuc_excerpt.pdf"


@pytest.fixture(scope="module")
def records() -> list[Record]:
    return parse_bulletin(FIXTURE, date(2026, 11, 18), "mal")


@pytest.fixture(scope="module")
def by_key(records):
    return {(r.section, r.seq): r for r in records}


def test_count_and_sections(records):
    assert len(records) == 17
    assert [(r.section, r.seq) for r in records] == [
        ("A", 1), ("A", 2), ("A", 3), ("A", 4), ("A", 5), ("A", 6), ("A", 7),
        ("A", 75), ("A", 76), ("A", 77),
        ("B", 1), ("B", 2), ("B", 3), ("B", 4), ("B", 5), ("B", 90), ("B", 91),
    ]
    assert all(r.source_file == "mal_sonuc_excerpt.pdf" for r in records)
    assert all(r.bulletin_type == "mal" and r.bulletin_date == date(2026, 11, 18) for r in records)


def test_a1_pazarlik_with_gerekce(by_key):
    r = by_key["A", 1]
    assert r.ikn == "2026/1880594"
    assert r.title == "14 KALEM MUHTELİF ÜRÜNLER"
    assert r.idare == "CEZA VE TEVKİFEVLERİ GENEL MÜDÜRLÜĞÜ SİVEREK AÇIK CEZA İNFAZ KURUMU MÜDÜRLÜĞÜ"
    assert r.ihale_tarihi == date(2026, 10, 21)
    assert r.ihale_usulu == "Pazarlık (MD 21 F)"
    # the wrapped Gerekçe row sits between Usulü and Yaklaşık Maliyeti; it must not leak
    assert r.yaklasik_maliyet == Money(289425850, "TRY")
    assert r.esas_kisim_yaklasik_maliyet is None
    assert r.konu == "14 Kalem Muhtelif Ürünler"
    assert (r.toplam_teklif, r.gecerli_teklif) == (2, 2)
    assert r.sozlesme_tarihi == date(2026, 11, 16)   # not the ihale tarihi
    assert r.sozlesme_bedeli == Money(276720000, "TRY")
    assert r.sozlesme_suresi == "16.11.2026 - 31.12.2026"
    assert r.yuklenici == "Emir Sosyal Hizmetler İş Sağlığı ve Güvenliği Gıda İnşaat Turizm Sanayi Ticaret Limited Şirketi"
    assert r.yuklenici_uyrugu == "Türkiye"
    assert (r.page_start, r.page_end) == (17, 17)
    assert all(r.confident(f) for f in CORE_FIELDS)


def test_a3_split_across_pages(by_key):
    r = by_key["A", 3]
    assert (r.page_start, r.page_end) == (18, 19)   # source page numbers from the footer
    assert r.ikn == "2026/1766844"
    assert r.idare == "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ ANTALYA MANAVGAT DEVLET HASTANESİ BAŞHEKİMLİĞİ"
    assert r.ihale_usulu == "Pazarlık (MD 21 B)"
    assert r.esas_kisim_yaklasik_maliyet == Money(101541940, "TRY")  # wrapped label
    assert r.sozlesme_bedeli == Money(15528000, "TRY")
    assert r.yuklenici == "Mustafa Öz"
    assert all(r.confident(f) for f in CORE_FIELDS)


def test_a5_a6_kismi_lots(by_key):
    a5, a6 = by_key["A", 5], by_key["A", 6]
    assert a5.ikn == a6.ikn == "2026/1833735"
    assert a5.yaklasik_maliyet == a6.yaklasik_maliyet == Money(1094622750, "TRY")
    assert a5.esas_kisim_yaklasik_maliyet == a6.esas_kisim_yaklasik_maliyet == Money(1094622750, "TRY")
    assert a5.sozlesme_bedeli == Money(8300000, "TRY")
    assert a6.sozlesme_bedeli == Money(25000000, "TRY")
    assert a5.yuklenici == "Yurdakul Bostancı"
    assert a6.yuklenici.startswith("Bioart Medikal")
    assert (a5.toplam_teklif, a5.gecerli_teklif) == (12, 11)
    assert (a5.page_start, a5.page_end) == (20, 21)
    assert (a6.page_start, a6.page_end) == (21, 22)
    for r in (a5, a6):
        assert all(r.confident(f) for f in CORE_FIELDS)


def test_a76_suffix_and_empty_estimate(by_key):
    r = by_key["A", 76]
    assert r.ikn == "2026/1772339-1"
    assert r.ihale_usulu == "Açık"
    assert r.yaklasik_maliyet is None
    assert r.confidence["yaklasik_maliyet"] == 1.0  # known empty, not unreadable
    assert not r.confident("yaklasik_maliyet")      # but unusable downstream
    assert r.sozlesme_bedeli == Money(19481245000, "TRY")
    assert r.konu.startswith("Üniversitemiz Sağlık Uygulama Araştırma Merkezi (Hastane)")
    assert r.konu.endswith("Serbest Piyasadan Elektrik Enerjisi Alımı")  # label between value lines
    assert "yuklenici_uyrugu" not in r.confidence                     # absent in the short layout


def test_b2_label_between_value_lines(by_key):
    r = by_key["B", 2]
    assert r.yuklenici == "Hidromek-Hidrolik ve Mekanik Makina İmalat Sanayi ve Ticaret Anonim Şirketi"
    assert r.confident("yuklenici")
    assert r.sozlesme_suresi == "26.10.2026 - 12.04.2027"
    assert r.ihale_usulu == "4734 / 3-g"
    assert r.section == "B"


def test_b4_dual_currency(by_key):
    r = by_key["B", 4]
    assert r.ikn == "2025/1643181"
    assert r.yaklasik_maliyet == Money(4740750000, "TRY", Money(107247500, "EUR"))
    assert r.sozlesme_bedeli == Money(3300000000, "TRY")
    assert r.confident("yaklasik_maliyet")


def test_b90_eur_bedel(by_key):
    r = by_key["B", 90]
    assert r.sozlesme_bedeli == Money(15405000, "EUR")
    assert r.yaklasik_maliyet == Money(1037799157, "TRY")
    assert r.confident("sozlesme_bedeli")
    assert (r.page_start, r.page_end) == (257, 257)


def test_confidence_on_empty_and_missing_fields(by_key):
    # empty value after the colon: None with confidence 1.0
    a3 = by_key["A", 3]
    assert a3.sozlesme_suresi is None and a3.confidence["sozlesme_suresi"] == 1.0
    # truncated record (fixture cut): labels never seen -> None with confidence 0 and warnings
    a7 = by_key["A", 7]
    assert a7.yuklenici is None and a7.confidence["yuklenici"] == 0.0
    assert not a7.confident("yuklenici") and not a7.confident("sozlesme_bedeli")
    assert any("kesik" in w for w in a7.warnings)
    assert a7.confident("ikn") and a7.confident("idare") and a7.confident("yaklasik_maliyet")


def test_confident_values_have_expected_shape(records):
    for r in records:
        for name, c in r.confidence.items():
            assert 0.0 <= c <= 1.0
            if c >= CONFIDENT:
                v = getattr(r, name)
                if v is None:
                    assert c == 1.0  # only "known empty" may be a confident None
    for r in records:
        if r.confident("ikn"):
            import re
            assert re.fullmatch(r"\d{4}/\d+(-\d+)?", r.ikn)


def test_never_raises_on_garbage_rows():
    from ihale.parse import _Row, parse_rows

    rows = [
        _Row(1, 100.0, "3", False, ""),
        _Row(1, 110.0, "SONUÇ İLANI", False, ""),
        _Row(1, 120.0, "garbage", True, "???"),
        _Row(1, 130.0, "İhale kayıt numarası", True, "xx"),
        _Row(1, 140.0, "1- İhalenin", False, ""),
        _Row(1, 150.0, "c) Yaklaşık Maliyeti", True, "abc TRY"),
    ]
    recs = parse_rows(rows, date(2026, 11, 18), "mal", "x.pdf")
    assert len(recs) == 1
    assert recs[0].yaklasik_maliyet is None
    assert not recs[0].confident("yaklasik_maliyet")
    assert not recs[0].confident("ikn")
    assert recs[0].warnings
