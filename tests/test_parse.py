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
    # truncated record (fixture cut): ihalent rejects it -> Record with confidence < 0.9 and warnings
    a7 = by_key["A", 7]
    assert a7.yuklenici is None and a7.confidence["yuklenici"] == 0.0
    assert not a7.confident("yuklenici") and not a7.confident("sozlesme_bedeli")
    assert any("kesik" in w for w in a7.warnings)
    assert not any(a7.confident(f) for f in CORE_FIELDS)   # ihalent rejected it: nothing is confident


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


def test_never_raises_and_rejected_notice_becomes_record():
    from ihalent.bulletin import Word
    from ihale.parse import parse_words

    def w(top, x0, text):
        return Word(1, float(x0), float(top), float(top) + 8, text)

    words = [
        w(100, 295, "3"), w(110, 265, "SONUÇ"), w(110, 302, "İLANI"),
        w(120, 145, "3."), w(120, 216, "2026/1234567"), w(120, 291, "BAŞLIK"),
        w(130, 75, "İhale"), w(130, 100, "kayıt"), w(130, 124, "numarası"), w(130, 242, ":"), w(130, 248, "xx"),
        w(145, 75, "1-"), w(145, 86, "İhalenin"),
        w(160, 75, "c)"), w(160, 86, "Yaklaşık"), w(160, 124, "Maliyeti"), w(160, 242, ":"), w(160, 248, "abc"),
    ]
    recs, read = parse_words(words, {1: 1}, date(2026, 11, 18), "mal", "x.pdf")
    assert len(recs) == 1 and len(read.rejected) == 1
    r = recs[0]
    assert (r.section, r.seq) == ("A", 3)
    assert r.ikn == "2026/1234567" and not r.confident("ikn")   # recovered from the header only
    assert not any(r.confident(f) for f in CORE_FIELDS)
    assert any("reddetti" in x for x in r.warnings)


LABELS = Path(__file__).parent / "labels" / "mal_2026-11-18.json"


@pytest.mark.skipif(not LABELS.exists(), reason="hand labels not present")
def test_fixture_accuracy_against_labels(by_key):
    """>=95% correct-and-confident per core field on the labeled records present in the fixture."""
    import json
    from decimal import Decimal

    def money(v):
        if v is None:
            return None
        alt = money(v["alt"]) if v.get("alt") else None
        return Money(int((Decimal(v["amount"]) * 100).to_integral_exact()), v["currency"], alt)

    labels = [x for x in json.loads(LABELS.read_text(encoding="utf-8")) if x["in_fixture"]]
    assert len(labels) >= 10
    good = {f: 0 for f in CORE_FIELDS}
    for lab in labels:
        r = by_key[lab["section"], lab["seq"]]
        for f in CORE_FIELDS:
            exp = lab[f]
            if f in ("sozlesme_bedeli", "yaklasik_maliyet"):
                exp = money(exp)
            got = getattr(r, f)
            if isinstance(got, str):
                got = " ".join(got.split())
            if got == exp and (r.confidence.get(f, 0) >= CONFIDENT):
                good[f] += 1
            else:
                # a miss must never be confident AND wrong
                assert not (got != exp and r.confidence.get(f, 0) >= CONFIDENT), (lab["section"], lab["seq"], f)
    for f in CORE_FIELDS:
        assert good[f] / len(labels) >= 0.95, (f, good[f], len(labels))
