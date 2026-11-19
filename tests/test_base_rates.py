import importlib.util
from datetime import date
from pathlib import Path

from ihale.store import Store

from rec_helpers import rec

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "base_rates.py"


def load():
    spec = importlib.util.spec_from_file_location("base_rates", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_empty_db(capsys):
    assert load().main([]) == 0
    assert "no records stored" in capsys.readouterr().out


def test_report_contents(capsys):
    D = date(2026, 11, 18)
    third = rec(3, ikn="2026/3", yuklenici="C", gecerli=3, section="B")
    third.ihale_usulu = "4734 / 3-g"
    Store().replace_day(D, "mal", [
        rec(1, ikn="2026/1", yuklenici="A", gecerli=1, toplam=1, bedel=99.0, maliyet=100.0),
        rec(2, ikn="2026/2", yuklenici="B", gecerli=3), third])
    assert load().main(["--date", "2026-11-18"]) == 0
    out = capsys.readouterr().out
    assert "3 records, 1 bulletin day(s)" in out
    assert "By usul" in out and "By section" in out and "Score distribution" in out
    assert "tek geçerli teklif" in out and "bedel >= 0.97" in out
    assert "score 2:" in out
    assert "Indicators by usul_turu" in out and "Indicators by section" in out
    assert "[istisna_3g]" in out and "karar_suresi_gun" in out and "yuklenici_payi" in out
