import pdfplumber

from conftest import FIXTURES


def test_fixture_pdf_has_extractable_text():
    with pdfplumber.open(FIXTURES / "mal_sonuc_excerpt.pdf") as pdf:
        assert len(pdf.pages) == 12
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    assert "SONUÇ İLANI" in text
    assert "İhale kayıt numarası : 2026/1880594" in text
    assert "Toplam Geçerli Teklif Sayısı" in text
    assert "Yaklaşık Maliyeti" in text and "Bedeli" in text
    assert text.count("Kamuoyuna saygıyla duyurulur") >= 8


def test_fixture_size_budget():
    assert (FIXTURES / "mal_sonuc_excerpt.pdf").stat().st_size < 450_000


def test_cli_parser_fetch_args():
    from ihale.cli import build_parser

    a = build_parser().parse_args(["fetch", "--date", "18.11.2026", "--type", "mal"])
    assert (a.date, a.type) == ("18.11.2026", "mal")
