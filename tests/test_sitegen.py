"""Offline tests for the static site generator. Built from the fictional sample export."""
from __future__ import annotations

import hashlib
import shutil
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


def _day_block(dist: Path, date: str, rid: str) -> str:
    """The expandable <details> block of a record on its day page."""
    h = _read(dist, f"gun/{date}/index.html")
    i = h.index(f'id="{rid}"')
    return h[i:h.index("</li>", i)]


def test_detail_pages_only_for_score_ge_1_and_every_record_on_day_page(dist):
    tenders = _tenders()
    assert len(tenders) >= 8
    for t in tenders:
        page = dist / "ihale" / t["id"] / "index.html"
        assert page.is_file() == (t["score"] >= 1), t["id"]
        day = _read(dist, f"gun/{t['source']['date']}/index.html")
        assert f'id="{t["id"]}"' in day
        assert ("<details>" in _day_block(dist, t["source"]["date"], t["id"])) == (t["score"] < 1)


def test_robots_meta_on_every_page(dist):
    pages = _html(dist)
    assert len(pages) >= 10
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
    assert "8 sonuç ilanı okundu · 6 tanesi gösteriliyor" in h
    # 3 flags first; then one-flag cards by raw bedel amount (A-2 is 104.000 EUR, ranked below the TRY ones)
    pos = [h.index(f"/ihale/2026-11-18-mal-{x}/") for x in ("A-1", "A-3", "B-1", "A-2")]
    assert pos == sorted(pos)
    assert "/gun/2026-11-18/" in h
    # no-JS filter chips
    assert 'type="radio"' in h and "Tek teklif (4)" in h
    # unflagged record is not a card on Bugün
    for hidden in ("A-4", "B-2"):  # score 1 / 0
        assert f"/ihale/2026-11-18-mal-{hidden}/" not in h


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
    assert "Tek teklif verildi" in d
    assert "Sözleşme bedeli yaklaşık maliyetin %98,6&#39;sı" in d
    assert "Kaynak: Kamu İhale Bülteni, 18.11.2026, Mal – Sonuç İlanları, s. 18" in d
    assert 'href="https://ekap.kik.gov.tr/EKAP/Ilan/BultenIndirme.aspx"' in d
    assert "Geçerli teklif sayısı" in d and "Sözleşme bedeli" in d


def test_unreadable_renders(dist):
    d = _day_block(dist, "2026-11-18", "2026-11-18-mal-B-2")   # score 0: expandable block, no page
    assert d.count("okunamadı") >= 2  # yaklaşık maliyet + ihale tarihi
    assert "para birimi farklı" in d


def test_kismi_note(dist):
    d = _read(dist, "ihale/2026-11-18-mal-A-3/index.html")
    assert "2 kayıt var" in d and "/ihale/2026-11-18-mal-A-4/" in d
    assert "2 kayıt var" not in _read(dist, "ihale/2026-11-18-mal-A-1/index.html")


def test_person_name_as_printed_and_escaped(dist):
    assert "Ayşe ÖRNEK" in _read(dist, "ihale/2026-11-18-mal-B-1/index.html")
    assert "3 teklif verildi, yalnızca kazananınki geçerli sayıldı" in _read(dist, "ihale/2026-11-18-mal-B-1/index.html")


def test_yontem_content(dist):
    y = _read(dist, "yontem/index.html")
    for needle in ["0,97", "365 gün", "en az 3 farklı", "toplam teklif sayısı tam olarak 1", "Kısmi", "okunamadı", "3-g",
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


def test_peer_comparison_line(dist):
    h = _read(dist, "index.html")
    assert ("Bu idarenin açık ihale alımları (n=12): %80 tek geçerli teklif · "
            "Örnek ilindeki sağlık idareleri (mal, açık ihale, n=140): %43") in h
    assert "Bu idarenin pazarlık (md. 21/b) alımları (n=8): %75 tek geçerli teklif · Tüm üniversiteler (mal, n=60): %35" in h
    d = _read(dist, "ihale/2026-11-18-mal-A-1/index.html")
    assert "Bu idarenin açık ihale alımları (n=12): %80" in d and "Puan: 4" in d


def test_peer_line_hidden_when_sample_small(dist):
    assert "Bu idare" not in _read(dist, "ihale/2026-11-18-mal-B-1/index.html")  # n=3
    assert sitegen.peer_line({"idare_stats": {"records": 4, "tek_gecerli_teklif": 0.5}}) is None
    assert sitegen.peer_line({"idare_stats": {"records": 5, "tek_gecerli_teklif": 0.5}}) == \
        "Bu idare (n=5): %50 tek geçerli teklif"


def test_score_parts_and_idare_orani_shown(dist):
    h = _read(dist, "index.html")
    assert sitegen.IDARE_ORANI_TEXT in h
    assert "Puan: 4,8" in h and "Puan: 3,5" in h and "Puan: 1,2" not in h and "Puan: 0,0" not in h
    assert "Bu yüklenici son 12 ayda" in h


def test_yontem_score_and_peer(dist):
    y = _read(dist, "yontem/index.html")
    for needle in ['id="puan"', "R018", "R035", "R038", "GTI", "en az 20 kaydı", "Bültende sektör veya il alanı yoktur",
                   "github.com/gulmezeren2-byte/ihalent", "yarısında"]:
        assert needle in y, needle


def test_indicators_block(dist):
    d = _read(dist, "ihale/2026-11-18-mal-A-1/index.html")
    assert "Göstergeler" in d
    assert "Karar süresi" in d and "20 gün" in d
    assert "%42" in d and "n=12" in d       # yüklenici payı
    assert "Açık ihale usulü" in d and "açık olmayan" not in d
    assert "Elenen teklif oranı" not in d                        # null -> hidden
    e = _read(dist, "ihale/2026-11-18-mal-A-2/index.html")
    assert "%0 (teklif verenlerin elenen payı) · benzer idarelerin ortalaması: %18" in e
    assert "Pazarlık usulü (md. 21/b) · açık olmayan usul" in e and "Yüklenicinin payı" not in e
    g = _read(dist, "ihale/2026-11-18-mal-B-1/index.html")
    assert "İstisna (4734 / 3-g) · açık olmayan usul" in g and "Karar süresi" not in g
    # no indicators at all -> no block, and indicators are not styled as flags
    assert "Göstergeler" not in _day_block(dist, "2026-11-17", "2026-11-17-mal-A-1")
    assert 'class="flag' not in d.split("Göstergeler")[1].split("Kaynak")[0]


def test_expandable_block_has_all_fields_and_source(dist):
    b = _day_block(dist, "2026-11-17", "2026-11-17-mal-A-1")
    for needle in ["<details>", "İhale kayıt no", "42.000,00 TRY", "Kaynak: Kamu İhale Bülteni, 17.11.2026, Mal – Sonuç İlanları, s. 7",
                   "BultenIndirme.aspx"]:
        assert needle in b, needle


def test_sibling_link_points_to_anchor_when_no_page(dist):
    # A-4 (score 1) has a page; its sibling A-3 has one too. A score-0 sibling would link to the day anchor.
    assert "/ihale/2026-11-18-mal-A-4/" in _read(dist, "ihale/2026-11-18-mal-A-3/index.html")


def test_file_count_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(sitegen, "MAX_FILES", 10)
    out = tmp_path / "dist"
    with pytest.raises(sitegen.SiteTooLargeError, match="over the limit"):
        sitegen.build(SAMPLE, out)
    assert not (out / "index.html").exists()   # deploy can't pick up a half-valid dist
    monkeypatch.setattr(sitegen, "MAX_FILES", 10_000)
    sitegen.build(SAMPLE, out)
    assert (out / "index.html").is_file()


def test_no_raw_python_values_and_null_names(tmp_path):
    exp = tmp_path / "exp"
    shutil.copytree(SAMPLE, exp)
    f = exp / "days" / "2026-11-18.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["tenders"][0]["idare"] = {"name": None, "key": None}
    d["tenders"][0]["flags"][1]["value"] = 1.0093869731800766
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "o"
    sitegen.build(exp, out)
    for p in out.rglob("*.html"):
        h = p.read_text(encoding="utf-8")
        assert not re.search(r"\bNone\b|\bTrue\b|\bFalse\b|\d\.\d{5,}|değer:", h), p


def test_fold_at_most_two_cards_per_idare(dist):
    h = _read(dist, "index.html")
    # 3 records of ÖRNEK İL MÜDÜRLÜĞÜ at score >= 2 (A-1, A-3, B-3, B-4 -> two cards + 2 folded)
    cards = re.findall(r'<li class="card [^"]*">\s*<h2><a href="/ihale/([^/]+)/', h)
    assert cards == ["2026-11-18-mal-A-1", "2026-11-18-mal-A-3", "2026-11-18-mal-B-1", "2026-11-18-mal-A-2"]
    assert "Bu idareden bugün 2 kayıt daha" in h
    i = h.index("kayıt daha")
    for hidden in ("B-3", "B-4"):                       # folded, linked, never dropped
        assert f'href="/ihale/2026-11-18-mal-{hidden}/"' in h[i:]
    # fold sits right after the idare's second card
    assert h.index("/ihale/2026-11-18-mal-A-3/") < i < h.index("/ihale/2026-11-18-mal-B-1/")
    # chips still count every record: tek_teklif = A-1, A-3, B-3, B-4
    assert "Tek teklif (4)" in h
    # every record keeps its detail page
    assert (dist / "ihale/2026-11-18-mal-B-4/index.html").is_file()


def test_fold_cards_unit():
    mk = lambda i, k: {"id": i, "_idare": k, "idare": {"key": k}, "_codes": ["tek_teklif"]}
    items = sitegen.fold_cards([mk("a", "X"), mk("b", "X"), mk("c", "X"), mk("d", "Y"), mk("e", "X")])
    assert [("card", x["card"]["id"]) if "card" in x else ("fold", [h["id"] for h in x["fold"]]) for x in items] ==         [("card", "a"), ("card", "b"), ("fold", ["c", "e"]), ("card", "d")]


def test_yontem_new_rules(dist):
    y = _read(dist, "yontem/index.html")
    for needle in ["406.700,00 TRY üzerinde (%100,9)", "aynı usul içinde", "en fazla 2 kart"]:
        assert needle in y, needle


from ihale.sitegen.persons import PERSON_LABEL, is_natural_person  # noqa: E402


@pytest.mark.parametrize("name,expected", [
    ("Mustafa Öz", True), ("Yurdakul Bostancı", True), ("AYŞE ÖRNEK", True), ("Aşkın Demir", True),
    ("Emir Sosyal Hizmetler Limited Şirketi", False),
    ("Kale Makina Pazarlama Anonim Şirketi", False),
    ("Fresenıus Medikal Hizmetler Anonim Şirketi", False),
    ("Örnek Yapı Ltd.Şti.", False), ("Örnek Gıda A.Ş.", False), ("ÖRNEK İNŞAAT SAN. VE TİC. LTD. ŞTİ.", False),
    ("Örnek Kooperatifi", False), ("Örnek Belediyesi", False), ("X Ortak Girişim", False),
    ("Ahmet Yılmaz Gıda", False), ("Tek", False), ("", False), (None, False),
])
def test_is_natural_person(name, expected):
    assert is_natural_person(name) is expected


def test_person_names_only_on_own_detail_page(dist):
    names = {"Ayşe ÖRNEK": "ihale/2026-11-18-mal-B-1/index.html", "Mehmet Örnekoğlu": None}
    for p in dist.rglob("*"):
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        for n, only in names.items():
            if n in text:
                assert only and p == dist / only, (n, p)
    assert "Ayşe ÖRNEK" in _read(dist, "ihale/2026-11-18-mal-B-1/index.html")
    assert PERSON_LABEL in _read(dist, "index.html")                       # Bugün card
    assert PERSON_LABEL in _read(dist, "gun/2026-11-17/index.html")        # expandable block, no page
    assert PERSON_LABEL in _read(dist, "gun/2026-11-18/index.html")


def test_no_threshold_labels_outside_yontem(dist):
    for p in dist.rglob("*.html"):
        if p.parent.name == "yontem":
            continue
        t = p.read_text(encoding="utf-8")
        assert "≥ %" not in t and "%97" not in t, p
    assert "Yaklaşık maliyete yakın (" in _read(dist, "index.html")


def test_bedel_ratio_with_peer_context(dist):
    d = _read(dist, "ihale/2026-11-18-mal-A-1/index.html")
    assert "%98,6 · benzer idarelerde ortanca %87 (n=140)" in d
    assert "Bedel / yaklaşık maliyet: bu kayıtta %98,6 · benzer idarelerde ortanca %87 (n=140)" in _read(dist, "index.html")


def test_innocent_lines(dist):
    d = _read(dist, "ihale/2026-11-18-mal-A-1/index.html")
    assert sitegen.INNOCENT["tek_teklif"] in d and sitegen.INNOCENT["bedel_orani"] in d
    assert sitegen.INNOCENT["tekrarlayan_yuklenici"] in d
    y = _read(dist, "yontem/index.html")
    for v in sitegen.INNOCENT.values():
        assert v in y


def test_structural_note_peer_note_and_table(dist):
    d = _read(dist, "ihale/2026-11-18-mal-A-4/index.html")
    assert "seri alımlarında tek teklif yapısı gereğidir" in d and "puana puan eklemez" in d
    assert "Kendi geçmişiyle karşılaştırılır" in d
    y = _read(dist, "yontem/index.html")
    assert "Yapısal tek teklif durumları" in y and "Gerekçe" in y and "Eklenme tarihi" in y
    assert "19 Kasım 2026" in y and "yalnızca belirtilmiş bir gerekçeyle" in y


def test_yontem_general_limits_no_evasion_list(dist):
    y = _read(dist, "yontem/index.html")
    assert "teklif verenlerin birbirinden bağımsız olup olmadığını" in y
    for p in dist.rglob("*.html"):
        low = _lower_tr(p.read_text(encoding="utf-8"))
        for w in ("göstermelik", "ihaleyi bölme", "ihale bölme"):
            assert w not in low, (p, w)


def test_score_formatting_and_cutoff(dist, tmp_path):
    assert sitegen.tr_score(4.8) == "4,8" and sitegen.tr_score(3) == "3,0"
    assert sitegen.tr_pct(0.12) == "%12" and sitegen.tr_pct(0.045) == "%4,5"
    h = _read(dist, "index.html")
    assert "Puan: 4,8" in h and "B-4" in h   # B-4 sits exactly on the 3.0 cut-off (folded under its idare)
    assert "2026-11-18-mal-A-4" not in h                              # 1.2 < cut-off
    # raise the cut-off: fewer cards, same pages
    exp = tmp_path / "exp"
    shutil.copytree(SAMPLE, exp)
    m = json.loads((exp / "meta.json").read_text(encoding="utf-8"))
    m["bugun_cutoff"] = 4.0
    (exp / "meta.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    sitegen.build(exp, tmp_path / "o")
    h2 = (tmp_path / "o" / "index.html").read_text(encoding="utf-8")
    assert "1 tanesi gösteriliyor" in h2 and "2026-11-18-mal-A-3" not in h2
    assert (tmp_path / "o" / "ihale/2026-11-18-mal-A-3/index.html").is_file()   # page still exists (score > 0)
    assert "4,0 veya daha yüksek" in (tmp_path / "o" / "yontem/index.html").read_text(encoding="utf-8")


def test_part_breakdown_only_on_detail(dist):
    d = _read(dist, "ihale/2026-11-18-mal-A-1/index.html")
    assert "Tek teklif: 2,1 puan (bu usulde görülme oranı %12)" in d
    assert "Tekrarlayan yüklenici: 1,1 puan (bu usulde görülme oranı %33)" in d
    assert "görülme oranı" not in _read(dist, "index.html").split("</header>")[1].split("<h2")[0]
    assert "görülme oranı" not in _day_block(dist, "2026-11-18", "2026-11-18-mal-B-2")


def test_yontem_rarity_and_part_rates_table(dist):
    y = _read(dist, "yontem/index.html")
    for needle in ["ln(1 / p)", "Nadirlik ağırlığı", "3,0 veya daha yüksek", "İşaretlerin usule göre görülme oranları",
                   "Tüm usuller", "İstisna (4734 / 3-g)", "%61", "Açık ihale usulü"]:
        assert needle in y, needle


def test_old_integer_shape_still_builds(tmp_path):
    exp = tmp_path / "exp"
    shutil.copytree(SAMPLE, exp)
    for f in (exp / "days").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        for t in d["tenders"]:
            t["score_parts"] = [pt["code"] for pt in t["score_parts"]]
            t["score"] = int(t["score"])
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    sitegen.build(exp, tmp_path / "o")
    assert (tmp_path / "o" / "index.html").is_file()


def test_value_weight_line_and_group_labels(dist):
    d = _read(dist, "ihale/2026-11-18-mal-A-1/index.html")
    assert "Tutar katsayısı: 1,3 (sözleşme bedeli, bu usuldeki ortanca bedelin yaklaşık 4 katı)" in d
    assert "TRY dışındaki veya okunamayan bedellere katsayı uygulanmaz" in _read(dist, "ihale/2026-11-18-mal-A-2/index.html")
    assert "Tutar katsayısı" not in _read(dist, "ihale/2026-11-18-mal-A-3/index.html")   # no weight exported
    y = _read(dist, "yontem/index.html")
    assert "Tutar katsayısı." in y and "log10" in y
    assert "<td>4734/3-g (DMO)</td>" in y                    # label exactly as exported
    assert "bedel_median_try" not in y and "3000000" not in y   # median is not a rate column


def test_source_check_typo_note(tmp_path):
    exp = tmp_path / "exp"
    shutil.copytree(SAMPLE, exp)
    f = exp / "days" / "2026-11-18.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    by = {t["id"]: t for t in d["tenders"]}
    by["2026-11-18-mal-A-3"]["indicators"] = {"source_check": "typo"}                 # no flag carries it -> note
    by["2026-11-18-mal-A-1"]["indicators"]["source_check"] = "typo"
    by["2026-11-18-mal-A-1"]["flags"][1]["source_check"] = "typo"                     # flag text already says it
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    sitegen.build(exp, tmp_path / "o")
    note = "Bültendeki iki rakam arasındaki fark tam bir 10'un katı; kaynakta yazım hatası olabilir."
    assert note in (tmp_path / "o/ihale/2026-11-18-mal-A-3/index.html").read_text(encoding="utf-8")
    assert note not in (tmp_path / "o/ihale/2026-11-18-mal-A-1/index.html").read_text(encoding="utf-8")
    assert note not in (tmp_path / "o/ihale/2026-11-18-mal-A-4/index.html").read_text(encoding="utf-8")
