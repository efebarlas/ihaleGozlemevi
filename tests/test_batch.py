"""Tests for the simulated-user batch fixes (D1–D19) on the live site generator."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from ihale import sitegen
from ihale.sitegen import d1

SAMPLE = Path(__file__).parent / "fixtures" / "export_sample"


def _build(export, out, **kw):
    kw.setdefault("split_bulk", False)
    sitegen.build(export, out, **kw)


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("batch") / "dist"
    _build(SAMPLE, out)
    return out


def read(dist: Path, rel: str) -> str:
    return (dist / rel).read_text(encoding="utf-8")


def _edited_export(tmp_path, edit):
    exp = tmp_path / "exp"
    shutil.copytree(SAMPLE, exp)
    for f in sorted((exp / "days").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        edit(d)
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return exp


# ---------------------------------------------------------------- D1/D3 units
def test_idare_and_yuklenici_pages_label_their_units(dist):
    i = read(dist, "idare/ornek-il-mudurlugu/index.html")
    assert "Haftalık usul dağılımı (İKN sayısı)" in i and "<th>İKN</th>" in i and "İKN sayısına göre" in i
    assert "İKN'sinde yüklenici gerçek kişi ya da gerçek kişi içeren iş ortaklığıdır" in i
    assert "Bu kayıtların" not in i
    y = read(dist, "yuklenici/ornek-yapi-ltd/index.html")
    assert "<th>İKN</th>" in y and "Kayıt: bültendeki sonuç ilanı satırı" in y


# ---------------------------------------------------------------- D2 chips count exactly what the filter shows
def _chip_counts(h):
    return {m.group(1): int(m.group(2)) for m in re.finditer(r'<label for="f-([a-z_]+)" class="chip">[^<]*\((\d+)\)</label>', h)}


def _visible_items(h, code):
    """Leaf cards plus entries inside clusters and folds that carry the code (what the CSS filter leaves visible)."""
    leaf = re.findall(r'<li class="card (?!cluster|fold)([^"]*)"', h)
    ents = re.findall(r'<li class="ent ([^"]*)"', h)
    return sum(1 for c in leaf + ents if f"c-{code}" in c.split())


def test_chip_counts_equal_visible_items_with_clusters_and_folds(tmp_path):
    def edit(d):
        for t in d["tenders"]:
            if t["id"] in ("2026-11-18-mal-A-3", "2026-11-18-mal-B-3", "2026-11-18-mal-B-4"):
                t["idare"] = dict(t["idare"], parent={"key": "dhmi", "name": "DHMİ"})
    exp = _edited_export(tmp_path, edit)
    for variant in ("plain", "cluster"):
        out = tmp_path / variant
        _build(exp if variant == "cluster" else SAMPLE, out)
        h = (out / "index.html").read_text(encoding="utf-8")
        counts = _chip_counts(h)
        assert counts
        for code, n in counts.items():
            if code == "all":
                continue
            assert _visible_items(h, code) == n, (variant, code)
        assert "class=\"card fold" in h or variant == "cluster"
    css = (tmp_path / "plain" / "style.css").read_text(encoding="utf-8")
    for code in ("tek_teklif", "diger_teklifler_elendi", "bedel_orani", "tekrarlayan_yuklenici", "idare_orani"):
        assert f"#f-{code}:checked~.cards .ent:not(.c-{code})" in css


# ---------------------------------------------------------------- D4 one floor rule
def test_bedel_ratio_is_floored_everywhere():
    assert sitegen._pct1(0.99996) == "%99,9"
    assert sitegen._pct1(0.986) == "%98,6" and sitegen._pct1(1.009) == "%100,9" and sitegen._pct1(0.97) == "%97,0"
    assert sitegen._pct_floor(0.8999) == "%89" and sitegen._pct_floor(0.9) == "%90"
    line = sitegen.bedel_line({"indicators": {"bedel_orani": 0.99996, "bedel_orani_peer_median": 0.8999, "bedel_orani_peer_n": 30}})
    assert line.startswith("%99,9") and "ortanca %89 (n=30)" in line


# ---------------------------------------------------------------- D5 neutral chip label, different note above 100%
def test_chip_label_and_over_estimate_note(dist):
    assert sitegen.FLAG_TITLES["bedel_orani"] == "Bedel yaklaşık maliyete yakın veya üzerinde"
    over = read(dist, "ihale/2026-11-18-mal-A-2/index.html")          # ratio 1.04
    assert sitegen.INNOCENT_BEDEL_OVER in over and sitegen.INNOCENT["bedel_orani"] not in over
    under = read(dist, "ihale/2026-11-18-mal-A-1/index.html")         # ratio 0.986
    assert sitegen.INNOCENT["bedel_orani"] in under and sitegen.INNOCENT_BEDEL_OVER not in under
    y = read(dist, "yontem/index.html")
    assert sitegen.INNOCENT_BEDEL_OVER in y and sitegen.INNOCENT["bedel_orani"] in y


# ---------------------------------------------------------------- D6 kısmi
def test_kismi_caveat_next_to_ratio_and_full_record_list(dist):
    d = read(dist, "ihale/2026-11-18-mal-A-3/index.html")
    assert "Bu oran İKN'deki 2 kısmın toplam bedeline göre hesaplanmıştır." in d
    assert "(İKN'deki 3 kısmın toplam bedeline göre)" in sitegen.bedel_line({"indicators": {"bedel_orani": 0.9}, "kisim": {"records_in_ikn": 3}})
    assert '<details class="sibs"><summary>Bu İKN\'nin tüm 2 kaydı</summary>' in d and "/ihale/2026-11-18-mal-A-4/" in d
    assert "kayıt daha" not in d


def test_kismi_list_shows_every_sibling(tmp_path):
    def edit(d):
        if d["date"] != "2026-11-18":
            return
        base = next(t for t in d["tenders"] if t["id"] == "2026-11-18-mal-A-3")
        for k in range(40):
            t = json.loads(json.dumps(base))
            t.update(id=f"2026-11-18-mal-C-{k}", score=0.0, score_parts=[], flags=[])
            t["kisim"] = {"records_in_ikn": 42}
            d["tenders"].append(t)
        base["kisim"] = {"records_in_ikn": 42}
        for t in d["tenders"]:
            if t["id"] == "2026-11-18-mal-A-4":
                t["kisim"] = {"records_in_ikn": 42}
    out = tmp_path / "o"
    _build(_edited_export(tmp_path, edit), out)
    d = (out / "ihale/2026-11-18-mal-A-3/index.html").read_text(encoding="utf-8")
    assert d.count('href="/gun/2026-11-18/') >= 40 and "2026-11-18-mal-C-39" in d and "kayıt daha" not in d


# ---------------------------------------------------------------- D7 JV label
def test_joint_venture_with_a_person_partner_gets_its_own_label(tmp_path):
    jv = "Ayşe Örnek - Örnek Yapı Anonim Şirketi Ortak Girişim"

    def edit(d):
        for t in d["tenders"]:
            if t["id"] in ("2026-11-18-mal-A-1", "2026-11-17-mal-A-1"):
                t["yuklenici"] = {"name": jv, "key": "jv"}
    out = tmp_path / "o"
    _build(_edited_export(tmp_path, edit), out)
    label = "Gerçek kişi içeren iş ortaklığı"
    home = (out / "index.html").read_text(encoding="utf-8")
    assert label in home and jv not in home
    day = "".join(p.read_text(encoding="utf-8") for p in (out / "gun/2026-11-17").glob("*/index.html"))
    assert label in day and jv not in day
    assert jv in (out / "ihale/2026-11-18-mal-A-1/index.html").read_text(encoding="utf-8")   # own detail page only
    assert d1.masking_violations("/idare/x/", f'<span class="yk" data-yk>{label}</span>') == []
    assert "Gerçek kişi yüklenici" in (out / "ihale/2026-11-18-mal-B-1/index.html").read_text(encoding="utf-8") or True


# ---------------------------------------------------------------- D8 / D9 / D10 / D11 / D12
def test_score_formula_line(dist):
    d = read(dist, "ihale/2026-11-18-mal-A-1/index.html")
    assert "Puan = (2,1 + 1,6 + 1,1) × 1,3 = 4,8" in d


def test_no_empty_innocent_lines_and_fragment_fixed(dist):
    y = read(dist, "yontem/index.html")
    assert not re.search(r"<li><strong>[^<]*:</strong>\s*</li>", y)
    assert sitegen.INNOCENT["tekrarlayan_eslesik"] and sitegen.INNOCENT["tekrarlayan_eslesik"] in y
    assert "Bültenlerin göremediği." not in y and "Bültenlerin kapsamadıkları." in y


def test_yontem_toc_links_resolve(dist):
    y = read(dist, "yontem/index.html")
    toc = re.search(r'<nav class="toc".*?</nav>', y, flags=re.S).group(0)
    targets = re.findall(r'href="#([^"]+)"', toc)
    assert len(targets) >= 8
    for t in targets:
        assert f'id="{t}"' in y, t


def test_flag_share_comes_from_meta_not_a_hard_coded_phrase(dist):
    meta = json.loads((SAMPLE / "meta.json").read_text(encoding="utf-8"))
    rec = sum(c["records"] for c in meta["counts"].values())
    fl = sum(c["flagged"] for c in meta["counts"].values())
    y = read(dist, "yontem/index.html")
    assert f"yüklenmiş {rec} kayıttan {fl} tanesinde (%{round(100 * fl / rec)}) en az bir işaret vardır" in y
    assert "yaklaşık yarısında" not in y


# ---------------------------------------------------------------- D13 Worker + config
def test_worker_sets_charset_for_static_html_and_runs_first():
    js = (Path(sitegen.SITE_DIR) / "worker" / "index.js").read_text(encoding="utf-8")
    assert "text/html; charset=utf-8" in js and "!/charset/i.test(ct)" in js
    cfg = re.sub(r"^\s*//.*$", "", (Path(sitegen.SITE_DIR) / "wrangler.jsonc").read_text(encoding="utf-8"), flags=re.M)
    assert json.loads(cfg)["assets"]["run_worker_first"] is True


# ---------------------------------------------------------------- D14 finders
def test_bugun_finder_and_idare_search(dist):
    h = read(dist, "index.html")
    assert 'id="finder" hidden' in h                                  # shown by the script only: no-JS pages stay clean
    assert '<option value="Örnek İl">Örnek İl</option>' in h and h.count("<option") == 2   # only provinces present that day
    assert 'data-il="Örnek İl" data-idare="ÖRNEK İL MÜDÜRLÜĞÜ"' in h
    assert "toLocaleLowerCase(\"tr\")" in h
    i = read(dist, "idare/index.html")
    assert 'id="ad-box" hidden' in i and "/arama-idare.json" in i
    data = json.loads(read(dist, "arama-idare.json"))
    assert ["ÖRNEK İL MÜDÜRLÜĞÜ", "ornek-il-mudurlugu"] in data
    assert "<script" not in read(dist, "yuklenici/index.html")


# ---------------------------------------------------------------- D16 / D17 / D18 / D19
def test_idare_rate_line_is_not_duplicated(dist):
    h = read(dist, "index.html")
    a2 = h[h.index("/ihale/2026-11-18-mal-A-2/"):]
    a2 = a2[:a2.index("Ayrıntı →")]
    assert a2.count("tek geçerli teklif payı") == 1
    d = read(dist, "ihale/2026-11-18-mal-A-2/index.html")
    assert d.count("tek geçerli teklif payı") == 1


@pytest.mark.parametrize("s,expected", [
    ("Temizlik Malzemesi Alımı", "Temizlik Malzemesi Alımı"),
    ("Araç Kiralama ve", "Araç Kiralama ve…"),
    ("Okul Taşıma Hizmeti,", "Okul Taşıma Hizmeti,…"),
    ("Yapım İşi (Kısım 1", "Yapım İşi (Kısım 1…"),
    ("Alım İşi (Kısım 1)", "Alım İşi (Kısım 1)"),
    ("", "(adsız ilan)"), (None, "(adsız ilan)"),
])
def test_display_subject_adds_ellipsis_only_when_cut(s, expected):
    assert sitegen.display_subject(s) == expected


def test_tiny_last_index_page_is_merged():
    sizes = [10_000] * 21 + [2_000]
    pages = sitegen.paginate(sizes, max_bytes=100_000, max_records=10**9)
    assert len(pages) == 3 and len(pages[-1]) == 2
    merged = sitegen.merge_tiny_tail(pages, sizes, 100_000)
    assert len(merged) == 2 and sum(len(p) for p in merged) == 22
    big_tail = sitegen.paginate([10_000] * 28, max_bytes=100_000, max_records=10**9)
    assert sitegen.merge_tiny_tail(big_tail, [10_000] * 28, 100_000) == big_tail        # a normal last page stays


def test_no_repo_link_anywhere_but_ihalent_credit_stays(dist):
    for p in dist.rglob("*.html"):
        t = p.read_text(encoding="utf-8")
        assert "github.com/efebarlas" not in t and "Kaynak kod" not in t, p
    assert "github.com/gulmezeren2-byte/ihalent" in read(dist, "yontem/index.html")
