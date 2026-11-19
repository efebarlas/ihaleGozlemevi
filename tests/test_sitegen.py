"""Offline tests for the static site generator. Built from the fictional sample export."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from ihale import sitegen

SAMPLE = Path(__file__).parent / "fixtures" / "export_sample"
FORBIDDEN = ["şüphe", "yolsuz", "usulsüz", "rüşvet", "hile", "sahte", "kayırma"]


def _lower_tr(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


@pytest.fixture(scope="module")
def dist(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("site") / "dist"
    sitegen.build(SAMPLE, out)
    return out


def _tenders():
    out = []
    for p in sorted((SAMPLE / "days").glob("*.json")):
        out += json.loads(p.read_text(encoding="utf-8"))["tenders"]
    return out


def _html(dist: Path):
    return sorted(dist.rglob("*.html"))


def _read(dist: Path, rel: str) -> str:
    return (dist / rel).read_text(encoding="utf-8")


def test_expected_pages(dist):
    for rel in ["index.html", "404.html", "yontem/index.html", "arsiv/index.html",
                "gun/2026-11-18/index.html", "gun/2026-11-17/index.html", "style.css"]:
        assert (dist / rel).is_file(), rel


def test_detail_page_for_every_record(dist):
    tenders = _tenders()
    assert len(tenders) >= 8
    for t in tenders:
        assert (dist / "ihale" / t["id"] / "index.html").is_file()


def test_robots_meta_on_every_page(dist):
    pages = _html(dist)
    assert len(pages) >= 14
    for p in pages:
        assert '<meta name="robots" content="noindex, nofollow">' in p.read_text(encoding="utf-8"), p


def test_robots_txt_and_headers(dist):
    assert _read(dist, "robots.txt") == "User-agent: *\nDisallow: /\n"
    h = _read(dist, "_headers")
    assert h.splitlines()[0] == "/*"
    assert "X-Robots-Tag: noindex, nofollow" in h


def test_no_third_party_or_tracking(dist):
    assert not (dist / "sitemap.xml").exists()
    for p in _html(dist):
        t = p.read_text(encoding="utf-8")
        assert "og:" not in t and "<script" not in t
        for url in re.findall(r'(?:href|src)="(https?://[^"]+)"', t):
            assert url.startswith(("https://ekap.kik.gov.tr/", "https://github.com/")), (p, url)


def test_no_forbidden_words(dist):
    for p in dist.rglob("*"):
        if p.is_file() and p.suffix in {".html", ".css", ".txt"}:
            low = _lower_tr(p.read_text(encoding="utf-8"))
            for w in FORBIDDEN:
                assert w not in low, (p, w)


def test_bugun_heading_summary_and_order(dist):
    h = _read(dist, "index.html")
    assert "<h1>18 Kasım 2026</h1>" in h
    assert "6 sonuç ilanı · 5 tanesinde en az bir işaret" in h
    # 3 flags first; then one-flag cards by raw bedel amount (A-2 is 104.000 EUR, ranked below the TRY ones)
    pos = [h.index(f"/ihale/2026-11-18-mal-{x}/") for x in ("A-1", "A-3", "A-4", "B-1", "A-2")]
    assert pos == sorted(pos)
    assert "/gun/2026-11-18/" in h
    # no-JS filter chips
    assert 'type="radio"' in h and "Tek geçerli teklif (2)" in h
    # unflagged record is not a card on Bugün
    assert "2026-11-18-mal-B-2" not in h


def test_money_and_date_formatting(dist):
    assert sitegen.tr_money({"amount": 2767200.0, "currency": "TRY"}) == "2.767.200,00 TRY"
    assert sitegen.tr_money({"amount": 0.5, "currency": "EUR"}) == "0,50 EUR"
    assert sitegen.tr_money({"amount": 1234567.891, "currency": "TRY"}) == "1.234.567,89 TRY"
    assert sitegen.tr_date_long("2026-11-18") == "18 Kasım 2026"
    assert sitegen.tr_date_short("2026-03-05") == "05.03.2026"
    d = _read(dist, "ihale/2026-11-18-mal-A-1/index.html")
    assert "2.767.200,00 TRY" in d and "2.894.258,50 TRY" in d
    assert "21.10.2026" in d
    eur = _read(dist, "ihale/2026-11-18-mal-A-2/index.html")
    assert "104.000,00 EUR" in eur


def test_detail_flags_source_and_labels(dist):
    d = _read(dist, "ihale/2026-11-18-mal-A-1/index.html")
    assert "Tek geçerli teklif" in d
    assert "Sözleşme bedeli yaklaşık maliyetin %95&#39;i" in d
    assert "Kaynak: Kamu İhale Bülteni, 18.11.2026, Mal – Sonuç İlanları, s. 18" in d
    assert 'href="https://ekap.kik.gov.tr/EKAP/Ilan/BultenIndirme.aspx"' in d
    assert "Geçerli teklif sayısı" in d and "Sözleşme bedeli" in d


def test_unreadable_renders(dist):
    d = _read(dist, "ihale/2026-11-18-mal-B-2/index.html")
    assert d.count("okunamadı") >= 2  # yaklaşık maliyet + ihale tarihi
    assert "para birimi farklı" in d


def test_kismi_note(dist):
    d = _read(dist, "ihale/2026-11-18-mal-A-3/index.html")
    assert "2 kayıt var" in d and "/ihale/2026-11-18-mal-A-4/" in d
    assert "2 kayıt var" not in _read(dist, "ihale/2026-11-18-mal-A-1/index.html")


def test_person_name_as_printed_and_escaped(dist):
    assert "Ayşe ÖRNEK" in _read(dist, "ihale/2026-11-18-mal-B-1/index.html")
    assert "3 teklif, 1 geçerli" in _read(dist, "ihale/2026-11-18-mal-B-1/index.html")


def test_yontem_content(dist):
    y = _read(dist, "yontem/index.html")
    for needle in ["0,95", "365 gün", "en az 3 farklı", "tam olarak 1", "Kısmi", "okunamadı", "3-g",
                   "ihalent", "mal alımı", "17 Kasım 2026", "yargı bildirmez"]:
        assert needle in y, needle


def test_footer_line(dist):
    assert ("Bu site, resmî Kamu İhale Bülteni'nde yayımlanan bilgileri düzenler; "
            "herhangi bir değerlendirme veya suçlama içermez.") in _read(dist, "index.html")


def test_escaping(tmp_path):
    exp = tmp_path / "exp"
    (exp / "days").mkdir(parents=True)
    t = json.loads((SAMPLE / "days" / "2026-11-17.json").read_text(encoding="utf-8"))
    t["tenders"][0]["konu"] = "<script>alert(1)</script>"
    (exp / "days" / "2026-11-17.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    (exp / "meta.json").write_text(json.dumps({"schema": 1, "latest_date": "2026-11-17", "dates": ["2026-11-17"],
                                               "counts": {}}), encoding="utf-8")
    sitegen.build(exp, tmp_path / "o")
    for p in (tmp_path / "o").rglob("*.html"):
        assert "<script>alert" not in p.read_text(encoding="utf-8")


def test_unsafe_id_rejected(tmp_path):
    exp = tmp_path / "exp"
    (exp / "days").mkdir(parents=True)
    t = json.loads((SAMPLE / "days" / "2026-11-17.json").read_text(encoding="utf-8"))
    t["tenders"][0]["id"] = "../../evil"
    (exp / "days" / "2026-11-17.json").write_text(json.dumps(t), encoding="utf-8")
    (exp / "meta.json").write_text(json.dumps({"schema": 1, "latest_date": "2026-11-17", "dates": [], "counts": {}}),
                                   encoding="utf-8")
    with pytest.raises(ValueError):
        sitegen.build(exp, tmp_path / "o")


def _digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_deterministic_and_wipes(tmp_path):
    out = tmp_path / "dist"
    sitegen.build(SAMPLE, out)
    first = _digest(out)
    (out / "stale.txt").write_text("x")
    sitegen.build(SAMPLE, out)
    assert not (out / "stale.txt").exists()
    assert _digest(out) == first


def test_deploy_refuses_sample_and_missing(tmp_path, dist):
    with pytest.raises(RuntimeError):
        sitegen.deploy(tmp_path / "nope")
    with pytest.raises(RuntimeError, match="sample"):
        sitegen.deploy(dist)


def test_wrangler_config():
    cfg = (Path(sitegen.SITE_DIR) / "wrangler.jsonc").read_text(encoding="utf-8")
    cfg = re.sub(r"^\s*//.*$", "", cfg, flags=re.M)
    c = json.loads(cfg)
    assert c["name"] == "ihale-gozlemevi" and c["workers_dev"] is True
    assert c["assets"] == {"directory": "./dist", "not_found_handling": "404-page"}
    assert "routes" not in c and "route" not in c
