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
    kinds = [c[0] + (":" + ("remote" if "--remote" in c else "local") if c[0] == "d1" else "") for c in calls]
    assert kinds[0] == "d1:remote" and kinds[-1] == "deploy" or kinds == ["d1:remote", "deploy"]
    assert kinds.index("deploy") > max(i for i, k in enumerate(kinds) if k.startswith("d1"))   # no deletions to run here


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
