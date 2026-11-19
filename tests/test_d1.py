"""Offline tests for the D1 split: classifier, staging, SQL chunking/escaping, manifest diffing, deploy order."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from ihale import sitegen
from ihale.sitegen import d1

SAMPLE = Path(__file__).parent / "fixtures" / "export_sample"
WORKER = Path(sitegen.SITE_DIR) / "worker" / "index.js"


# ------------------------------------------------------------------ classifier
CASES = {
    "/ihale/2026-11-18-mal-A-1/": True,
    "/idare/ornek-il-mudurlugu/": True,
    "/idare/ornek-il-mudurlugu/2/": True,
    "/yuklenici/ornek-yapi-ltd/": True,
    "/yuklenici/ornek-yapi-ltd/3/": True,
    "/gun/2026-11-18/1/": True,
    "/gun/2026-11-18/": False,
    "/": False, "/arsiv/": False, "/yontem/": False, "/404.html": False, "/style.css": False,
    "/idare/": False, "/yuklenici/": False,
    "/idare/liste/2/": False, "/yuklenici/liste/3/": False, "/idare/liste/": False,
    "/ihale/": False, "/ihale/a/b/": False, "/idare/x/y/": False, "/gun/": False,
}


@pytest.mark.parametrize("path,expected", CASES.items())
def test_is_bulk(path, expected):
    assert d1.is_bulk(path) is expected


def test_url_path():
    assert d1.url_path("index.html") == "/"
    assert d1.url_path("ihale/x/index.html") == "/ihale/x/"
    assert d1.url_path("gun\\2026-11-18\\2\\index.html") == "/gun/2026-11-18/2/"
    assert d1.url_path("style.css") is None and d1.url_path("404.html") is None


def test_worker_regexes_match_python_classifier():
    src = WORKER.read_text(encoding="utf-8")
    block = src[src.index("const BULK = ["):src.index("];", src.index("const BULK = ["))]
    pats = [re.compile(m.group(1)) for m in re.finditer(r"^\s*/(\^.*\$)/,$", block, flags=re.M)]
    assert len(pats) == 4
    for path in CASES:
        assert any(p.match(path) for p in pats) is d1.is_bulk(path), path


# ------------------------------------------------------------------ split build == full build
@pytest.fixture(scope="module")
def builds(tmp_path_factory):
    root = tmp_path_factory.mktemp("d1")
    sitegen.build(SAMPLE, root / "full", split_bulk=False)
    sitegen.build(SAMPLE, root / "split")
    return root / "full", root / "split"


def test_split_build_is_the_full_build_cut_in_two(builds):
    full, split = builds
    stage = d1.staging_path(split)
    assert stage.is_file() and not (full.parent / "full-pages.sqlite").exists()
    staged = dict(d1.staged_paths(stage))
    bulk_expected = set()
    for f in full.rglob("*.html"):
        url = d1.url_path(f.relative_to(full).as_posix()) or "/" + f.relative_to(full).as_posix()
        if d1.is_bulk(url):
            bulk_expected.add(url)
            assert not (split / f.relative_to(full)).exists(), url                 # bulk pages are not assets
            assert d1.staged_html(stage, url) == f.read_text(encoding="utf-8"), url   # identical bytes
            assert staged[url] == d1.sha_of(f.read_text(encoding="utf-8"))
        else:
            assert (split / f.relative_to(full)).read_bytes() == f.read_bytes(), url   # static pages identical
    assert set(staged) == bulk_expected
    assert any(u.startswith("/ihale/") for u in staged) and any(u.startswith("/gun/") for u in staged)
    assert any(u.startswith("/idare/") for u in staged) and any(u.startswith("/yuklenici/") for u in staged)
    for rel in ("index.html", "404.html", "robots.txt", "_headers", "style.css", "arsiv/index.html", "yontem/index.html",
                "gun/2026-11-18/index.html", "idare/index.html", "yuklenici/index.html"):
        assert (split / rel).is_file(), rel


def test_static_count_small_and_every_page_under_150kb(builds):
    full, split = builds
    n_static = sum(1 for p in split.rglob("*") if p.is_file())
    n_full = sum(1 for p in full.rglob("*") if p.is_file())
    print(f"static files: {n_static} of {n_full} total")
    assert n_static < n_full
    for p in split.rglob("*.html"):
        assert p.stat().st_size <= 150_000, p
    db = sqlite3.connect(d1.staging_path(split))
    try:
        assert db.execute("SELECT max(length(CAST(html AS BLOB))) FROM staged").fetchone()[0] <= 150_000
    finally:
        db.close()


def test_preview_build_stays_fully_static(tmp_path):
    sitegen.build(SAMPLE, tmp_path / "p", preview_design=True)
    assert (tmp_path / "p" / "ihale" / "2026-11-18-mal-A-1" / "index.html").is_file()
    assert not d1.staging_path(tmp_path / "p").exists()


# ------------------------------------------------------------------ SQL: chunking and escaping
NASTY = "it's 100% a;b -- c /* d */ \n\r\n İİıışşğğüüööçç ''quoted'' \"dq\" \\ <b>x</b> é \U0001F600 NULL"


def _apply(db: sqlite3.Connection, stmts: list[str]):
    db.executescript(d1.SCHEMA + "\n".join(stmts))


def _read_back(db, path):
    rows = db.execute("SELECT html FROM pages WHERE path=? ORDER BY part", (path,)).fetchall()
    return "".join(r[0] for r in rows)


def test_sql_quote_roundtrip_through_sqlite():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE t(x TEXT)")
    db.executescript(f"INSERT INTO t VALUES({d1.sql_quote(NASTY)});")
    assert db.execute("SELECT x FROM t").fetchone()[0] == NASTY


@pytest.mark.parametrize("html", ["", "x", NASTY, NASTY * 3000, "'" * 40_000, "ş" * 50_000, "\U0001F600" * 20_000])
def test_page_statements_chunk_and_roundtrip(html):
    stmts = d1.page_statements("/ihale/x'y;z/", html, d1.sha_of(html), "2026-11-19T00:00:00Z")
    assert all(len(s.encode("utf-8")) <= d1.MAX_STATEMENT_BYTES for s in stmts)
    db = sqlite3.connect(":memory:")
    _apply(db, stmts)
    assert _read_back(db, "/ihale/x'y;z/") == html
    parts, sha = db.execute("SELECT parts, sha FROM page_meta").fetchone()
    assert parts == len(d1.chunks(html)) and sha == d1.sha_of(html)


def test_statement_over_limit_is_rejected(monkeypatch):
    monkeypatch.setattr(d1, "CHUNK_CHARS", 100_000)
    with pytest.raises(ValueError, match="over"):
        d1.page_statements("/p/", "ş" * 100_000, "s", "u")


def test_batches_keep_pages_together_and_respect_limit():
    groups = [[f"INSERT {i} " + "x" * 1000 + ";" for _ in range(3)] for i in range(50)]
    batches = d1.batch_files(groups, limit=20_000)
    assert sum(len(b) for b in batches) == 50 and len(batches) > 1
    for b in batches:
        assert sum(len(s) + 1 for g in b for s in g) <= 20_000 + 3100
    assert [g for b in batches for g in b] == groups


# ------------------------------------------------------------------ manifest diff, deletion, row guard
def _mk_stage(path: Path, pages: dict[str, str]) -> Path:
    st = d1.Stage(path)
    for k, v in pages.items():
        st.add(k, v)
    st.close()
    return path


class FakeD1:
    """Applies batch files to an in-memory SQLite, like `wrangler d1 execute` would."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.files: list[Path] = []

    def __call__(self, f: Path):
        self.files.append(f)
        self.db.executescript(f.read_bytes().decode("utf-8"))

    def pages(self) -> dict[str, str]:
        paths = [r[0] for r in self.db.execute("SELECT path FROM page_meta")]
        return {p: _read_back(self.db, p) for p in paths}


def _sync(tmp_path, stage, fake, **kw):
    return d1.sync_pages(stage_db=stage, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b",
                         execute=fake, updated="t", log=lambda m: None, **kw)


def test_first_sync_uploads_everything_then_second_is_a_noop(tmp_path):
    pages = {"/ihale/a/": "A" * 40_000, "/ihale/b/": NASTY, "/gun/2026-11-18/1/": "<p>x</p>"}
    stage = _mk_stage(tmp_path / "s.sqlite", pages)
    fake = FakeD1()
    plan = _sync(tmp_path, stage, fake)
    assert len(plan.upserts) == 3 and plan.deletes == [] and fake.pages() == pages
    assert plan.rows == (3 + 1) + (1 + 1) + (1 + 1)                      # 3 parts + meta, 1 part + meta, 1 part + meta
    fake2 = FakeD1()
    fake2.db = fake.db
    plan2 = _sync(tmp_path, stage, fake2)
    assert plan2.upserts == [] and plan2.deletes == [] and plan2.unchanged == 3 and plan2.rows == 0
    assert "INSERT INTO pages" not in fake2.files[-1].read_text(encoding="utf-8")


def test_changed_page_shrinks_and_deleted_page_is_removed(tmp_path):
    big = "B" * (d1.CHUNK_CHARS * 2 + 10)                                    # 3 parts
    stage = _mk_stage(tmp_path / "s.sqlite", {"/ihale/a/": big, "/ihale/b/": "keep", "/ihale/c/": "gone"})
    fake = FakeD1()
    _sync(tmp_path, stage, fake)
    assert fake.db.execute("SELECT count(*) FROM pages WHERE path='/ihale/a/'").fetchone()[0] == 3
    stage2 = _mk_stage(tmp_path / "s2.sqlite", {"/ihale/a/": "B" * (d1.CHUNK_CHARS + 5), "/ihale/b/": "keep", "/ihale/new/": "n"})
    plan = _sync(tmp_path, stage2, fake)
    assert [u[0] for u in plan.upserts] == ["/ihale/a/", "/ihale/new/"] and plan.deletes == ["/ihale/c/"]
    assert plan.rows == (3 + 2 + 1) + (0 + 1 + 1) + (1 + 1)                 # a: old 3 + new 2 + meta; new; delete c
    assert fake.db.execute("SELECT count(*) FROM pages WHERE path='/ihale/a/'").fetchone()[0] == 2   # no stale part
    assert fake.pages() == {"/ihale/a/": "B" * (d1.CHUNK_CHARS + 5), "/ihale/b/": "keep", "/ihale/new/": "n"}
    assert d1.load_manifest(tmp_path / "m.json").keys() == {"/ihale/a/", "/ihale/b/", "/ihale/new/"}


def test_deletions_run_after_the_between_step(tmp_path):
    stage = _mk_stage(tmp_path / "s.sqlite", {"/ihale/a/": "a", "/ihale/c/": "c"})
    fake = FakeD1()
    _sync(tmp_path, stage, fake)
    stage2 = _mk_stage(tmp_path / "s2.sqlite", {"/ihale/a/": "a2"})
    events = []
    d1.sync_pages(stage_db=stage2, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b",
                  execute=lambda f: (events.append("exec"), fake(f)), between=lambda: events.append("deploy"),
                  updated="t", log=lambda m: None)
    assert events == ["exec", "deploy", "exec"]                             # upserts, Worker deploy, deletions
    assert "/ihale/c/" not in fake.pages()


def test_row_guard_refuses_before_any_write(tmp_path):
    stage = _mk_stage(tmp_path / "s.sqlite", {f"/ihale/{i}/": "x" for i in range(30)})
    fake = FakeD1()
    with pytest.raises(RuntimeError, match="exceeds the limit"):
        _sync(tmp_path, stage, fake, max_rows=50)
    assert fake.files == [] and not (tmp_path / "m.json").exists()
    assert d1.D1_MAX_ROWS_PER_RUN == 90_000


def test_failed_batch_keeps_manifest_for_the_uncommitted_pages_only(tmp_path, monkeypatch):
    pages = {f"/ihale/{i:03d}/": "p" * 6000 for i in range(40)}
    stage = _mk_stage(tmp_path / "s.sqlite", pages)
    fake = FakeD1()
    calls = []

    def flaky(f):
        calls.append(f)
        if len(calls) == 2:
            raise RuntimeError("boom")
        fake(f)
    monkeypatch.setattr(d1, "BATCH_BYTES", 100_000)
    with pytest.raises(RuntimeError, match="boom"):
        _sync(tmp_path, stage, flaky)
    done = d1.load_manifest(tmp_path / "m.json")
    assert 0 < len(done) < 40
    assert set(done) == set(fake.pages())                                   # manifest == what really reached D1
    plan = _sync(tmp_path, stage, fake)                                      # re-run finishes only the rest
    assert len(plan.upserts) == 40 - len(done) and fake.pages() == pages


# ------------------------------------------------------------------ deploy() order and guards
def _fake_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "yontem").mkdir(parents=True)
    (dist / "index.html").write_text("<html>real site</html>", encoding="utf-8")
    (dist / "yontem" / "index.html").write_text("<html>y</html>", encoding="utf-8")
    _mk_stage(d1.staging_path(dist), {"/ihale/a/": "a", "/idare/x/": "x"})
    return dist


def test_deploy_local_runs_d1_only_with_local_flag(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path)
    calls = []
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda args: calls.append(args) or "")
    monkeypatch.setattr(sitegen, "log", lambda m: None)
    url = sitegen.deploy(dist, local=True, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b")
    assert url == "local" and calls
    assert all(c[:3] == ["d1", "execute", "ihale-pages"] and "--local" in c and "--remote" not in c for c in calls)
    assert not any(c[0] == "deploy" for c in calls)


def test_deploy_remote_order_and_placeholder_guard(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path)
    calls = []

    def fake(args):
        calls.append(args)
        return "Published ihale-gozlemevi\n  https://ihale-gozlemevi.example.workers.dev\n" if args[0] == "deploy" else ""
    monkeypatch.setattr(sitegen, "_run_wrangler", fake)
    monkeypatch.setattr(sitegen, "log", lambda m: None)
    with pytest.raises(RuntimeError, match="placeholder"):                     # the repo config still has the zero id
        sitegen.deploy(dist, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b")
    assert calls == []
    monkeypatch.setattr(sitegen, "_d1_id", lambda: "11111111-2222-3333-4444-555555555555")
    url = sitegen.deploy(dist, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b")
    assert url == "https://ihale-gozlemevi.example.workers.dev"
    kinds = [("d1:" + ("remote" if "--remote" in c else "local") if c[:2] == ["d1", "execute"] else c[0] + (":" + c[1] if c[0] == "d1" else ""))
             for c in calls]
    assert kinds[0] == "d1:remote" and kinds.index("deploy") > max(i for i, k in enumerate(kinds) if k == "d1:remote")
    assert "d1:local" not in kinds
    assert kinds[kinds.index("deploy") + 1:] == ["d1:info", "d1:insights"]       # usage check runs after the deploy


def test_deploy_refuses_without_staged_pages_and_keeps_old_guards(tmp_path, builds):
    full, split = builds
    d = tmp_path / "d"
    d.mkdir()
    (d / "index.html").write_text("<html>x</html>", encoding="utf-8")
    with pytest.raises(RuntimeError, match="staged bulk pages"):
        sitegen.deploy(d)
    with pytest.raises(RuntimeError, match="sample"):                          # test-sample builds never deploy
        sitegen.deploy(split)
    out = tmp_path / "pv"
    sitegen.build(SAMPLE, out, preview_design=True)
    with pytest.raises(RuntimeError, match="design preview"):
        sitegen.deploy(out)


# ------------------------------------------------------------------ masking guard
PERSON_PAGE = '<span class="yk" data-yk>Ayşe Örnekoğlu</span>'
COMPANY = '<span class="yk" data-yk>Örnek Yapı Limited Şirketi</span>'
LABEL = '<span class="yk" data-yk>Gerçek kişi yüklenici</span>'
LEAK_RE = r'(<span class="yk" data-yk>)[^<]*(</span>)'


def test_masking_guard_passes_clean_builds(builds):
    full, split = builds
    d1.check_masking(full, None)
    d1.check_masking(split, d1.staging_path(split))          # static pages and the staged bulk pages


def test_masking_guard_rules():
    v = d1.masking_violations
    assert v("/idare/x/", f"<td>{COMPANY}</td><td>{LABEL}</td>") == []
    assert v("/gun/2026-11-18/1/", '<span class="yk" data-yk>okunamadı</span>') == []               # unreadable placeholder
    assert len(v("/idare/x/", f"<td>{PERSON_PAGE}</td>")) == 1                      # planted leak
    assert len(v("/gun/2026-11-18/1/", f"<li>{PERSON_PAGE}</li>")) == 1
    assert v("/ihale/a/", '<dd><span class="yk" data-yk="own">Ayşe Örnekoğlu</span></dd>') == []   # own detail page
    assert len(v("/idare/x/", '<dd><span class="yk" data-yk="own">Ayşe Örnekoğlu</span></dd>')) == 1
    # raw text is not scanned: a founder's name inside a company name or an item text is fine
    assert v("/idare/x/", "<p>İsmail Özdemir Huzurevi alımı</p><p>Ayşe Örnekoğlu</p>") == []
    assert v("/ihale/a/", "<h1>Ayşe Örnekoğlu İnşaat Limited Şirketi</h1>") == []
    assert len(v("/yuklenici/ayse/", "<html><head><title>Ayşe Örnekoğlu · İhale Gözlemevi</title></head></html>")) == 1


def test_masking_guard_catches_planted_leak_on_idare_page_in_build_and_in_staged_pages(builds, tmp_path):
    import shutil as _sh
    full, split = builds
    copy = tmp_path / "full"                                                          # (a) static / full tree
    _sh.copytree(full, copy)
    page = copy / "idare" / "ornek-il-mudurlugu" / "index.html"
    html = page.read_text(encoding="utf-8")
    assert "data-yk>" in html
    page.write_text(re.sub(LEAK_RE, r"\1Ayşe Örnekoğlu\2", html, count=1), encoding="utf-8")
    with pytest.raises(RuntimeError, match="masking guard"):
        d1.check_masking(copy, None)
    stage = tmp_path / "stage.sqlite"                                                 # (b) staged bulk page
    _sh.copyfile(d1.staging_path(split), stage)
    db = sqlite3.connect(stage)
    url, h = db.execute("SELECT path, html FROM staged WHERE path='/idare/ornek-il-mudurlugu/'").fetchone()
    db.execute("UPDATE staged SET html=? WHERE path=?", (re.sub(LEAK_RE, r"\1Ayşe Örnekoğlu\2", h, count=1), url))
    db.commit()
    db.close()
    with pytest.raises(RuntimeError, match="/idare/ornek-il-mudurlugu/"):
        d1.check_masking(split, stage)


def test_deploy_runs_the_masking_guard_before_any_wrangler_call(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path)
    db = sqlite3.connect(d1.staging_path(dist))
    db.execute("UPDATE staged SET html=? WHERE path='/idare/x/'", (f"<ul><li>{PERSON_PAGE}</li></ul>",))
    db.commit()
    db.close()
    calls = []
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda args: calls.append(args) or "")
    with pytest.raises(RuntimeError, match="masking guard"):
        sitegen.deploy(dist, local=True, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b")
    assert calls == []


def test_real_templates_mark_the_names(builds):
    full, _ = builds
    t = (full / "ihale" / "2026-11-18-mal-B-1" / "index.html").read_text(encoding="utf-8")
    assert 'data-yk="own"' in t and "Ayşe ÖRNEK" in t                          # own page shows the name, marked as own
    day = "".join(p.read_text(encoding="utf-8") for p in (full / "gun" / "2026-11-18").glob("*/index.html"))
    assert "Ayşe ÖRNEK" not in day and "data-yk>Gerçek kişi yüklenici<" in day


# ------------------------------------------------------------------ usage warnings and the stop rule
def test_usage_warnings_at_80_percent():
    assert d1.usage_warnings(rows_written_today=79_999, rows_read_today=3_999_999, db_bytes=399_999_999) == []
    w = d1.usage_warnings(rows_written_today=80_000, rows_read_today=4_000_000, db_bytes=400_000_000)
    assert len(w) == 3 and any("rows written" in x for x in w) and any("rows read" in x for x in w) and any("database size" in x for x in w)
    assert any("total storage" in x for x in d1.usage_warnings(rows_written_today=0, rows_read_today=0, db_bytes=4_000_000_000))
    assert d1.usage_warnings(rows_written_today=None, rows_read_today=None, db_bytes=None) == []


def test_rows_written_tally_resets_each_day(tmp_path):
    f = tmp_path / "u.json"
    assert d1.add_rows_written(f, 30_000, "2026-11-19") == 30_000
    assert d1.add_rows_written(f, 55_000, "2026-11-19") == 85_000
    assert d1.add_rows_written(f, 1_000, "2026-11-20") == 1_000


def test_wrangler_output_parsing():
    assert d1.parse_info_size('{"name":"ihale-pages","file_size": 123456789, "num_tables": 2}') == 123456789
    assert d1.parse_info_size("no json") is None
    assert d1.parse_rows_read('[{"query":"x","rowsRead":10},{"query":"y","rowsRead":5}]') == 15
    assert d1.parse_rows_read("[]") is None


def test_report_d1_usage_writes_marker_and_clears_it(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(sitegen, "log", logs.append)
    outputs = {"info": '{"file_size": 420000000}', "insights": "[]"}
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda args: outputs[args[1]])
    w = sitegen.report_d1_usage(tmp_path, d1.Plan(rows=85_000, total_bytes=124_000_000), "2026-11-19")
    assert len(w) == 2 and (tmp_path / "logs" / "d1-usage-warning.txt").is_file()
    assert any(m.startswith("WARNING") for m in logs)
    outputs["info"] = '{"file_size": 1000}'
    assert sitegen.report_d1_usage(tmp_path, d1.Plan(rows=1, total_bytes=10), "2026-11-20") == []
    assert not (tmp_path / "logs" / "d1-usage-warning.txt").exists()


def test_usage_lookup_failures_do_not_break_the_report(tmp_path, monkeypatch):
    def boom(args):
        raise RuntimeError("no auth")
    monkeypatch.setattr(sitegen, "_run_wrangler", boom)
    monkeypatch.setattr(sitegen, "log", lambda m: None)
    assert sitegen.report_d1_usage(tmp_path, d1.Plan(rows=10, total_bytes=1), "2026-11-19") == []


@pytest.mark.parametrize("text", ["Please add a credit card to continue", "This requires a paid plan",
                                  "Upgrade to the Workers Paid plan", "To continue, create a new Cloudflare account"])
def test_payment_or_account_request_stops_the_run(monkeypatch, text):
    import subprocess as sp

    class P:
        returncode = 0
        stdout = text
        stderr = ""
    monkeypatch.setattr(sp, "run", lambda *a, **k: P())
    monkeypatch.setattr(sitegen, "_npx", lambda: "npx")
    with pytest.raises(sitegen.PaymentRequired, match="STOP"):
        sitegen._run_wrangler(["d1", "execute", "x"])
    P.stdout = "Published ihale-gozlemevi https://x.workers.dev"
    assert "Published" in sitegen._run_wrangler(["deploy"])


def test_worker_returns_503_not_a_crash_when_d1_throws():
    src = WORKER.read_text(encoding="utf-8")
    assert "catch (e)" in src and "status: 503" in src and "unavailable(request)" in src
