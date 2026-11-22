"""Offline tests for the D1 split: classifier, staging, SQL chunking/escaping, manifest diffing, deploy order."""
from __future__ import annotations

import gzip
import json
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


def test_full_build_without_split_is_fully_static(tmp_path):
    sitegen.build(SAMPLE, tmp_path / "p", split_bulk=False)
    assert (tmp_path / "p" / "ihale" / "2026-11-18-mal-A-1" / "index.html").is_file()
    assert not d1.staging_path(tmp_path / "p").exists()


# ------------------------------------------------------------------ SQL: gzip BLOB rows, chunking and escaping
NASTY = "it's 100% a;b -- c /* d */ \n\r\n İİıışşğğüüööçç ''quoted'' \"dq\" \\ <b>x</b> é \U0001F600 NULL"


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """deploy() keeps its manifests and the daily usage tally in the data dir: never touch the real one in tests."""
    monkeypatch.setenv("IHALE_DATA_DIR", str(tmp_path / "datadir"))
    (tmp_path / "datadir" / "export").mkdir(parents=True)                   # a plausible export for the empty-site guard (a)
    (tmp_path / "datadir" / "export" / "meta.json").write_text(
        json.dumps({"counts": {"2026-11-18": {"records": 4000}, "2026-11-17": {"records": 1500}}}), encoding="utf-8")


def _apply(db: sqlite3.Connection, stmts: list[str]):
    db.executescript(d1.SCHEMA + "\n".join(stmts))


def _read_back(db, path):
    """Concatenate the gzip parts of a page, gunzip once, return the HTML (what the Worker does)."""
    rows = db.execute("SELECT gz FROM pg WHERE path=? ORDER BY part", (path,)).fetchall()
    return gzip.decompress(b"".join(r[0] for r in rows)).decode("utf-8") if rows else ""


def test_sql_quote_roundtrip_through_sqlite():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE t(x TEXT)")
    db.executescript(f"INSERT INTO t VALUES({d1.sql_quote(NASTY)});")
    assert db.execute("SELECT x FROM t").fetchone()[0] == NASTY


import random as _random
_rnd = _random.Random(7)
RANDOM = "".join(_rnd.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ğüşöçıİ<>/=") for _ in range(150_000))   # barely compressible


@pytest.mark.parametrize("html", ["", "x", NASTY, NASTY * 3000, "'" * 40_000, "ş" * 50_000, "\U0001F600" * 20_000, RANDOM])
def test_page_statements_gzip_roundtrip(html):
    gz = d1.gzip_page(html)
    stmts = d1.page_statements("/ihale/x'y;z/", gz, d1.sha_of(html))
    assert all(len(s.encode("utf-8")) <= d1.MAX_STATEMENT_BYTES for s in stmts)
    db = sqlite3.connect(":memory:")
    _apply(db, stmts)
    assert _read_back(db, "/ihale/x'y;z/") == html
    shas = db.execute("SELECT part, sha FROM pg ORDER BY part").fetchall()
    assert shas[0] == (0, d1.sha_of(html)) and all(s is None for _, s in shas[1:])        # sha lives on part 0 only
    assert len(shas) == len(d1.gz_parts(gz))
    _apply(db, stmts)                                                                    # replaying the group changes nothing
    assert db.execute("SELECT count(*) FROM pg").fetchone()[0] == len(shas)


def test_a_typical_large_page_is_one_row_and_gzip_is_deterministic():
    html = ("<li class=\"row\"><a href=\"/ihale/2026-11-18-mal-A-1/\">Örnek konu</a> <span>ÖRNEK İL MÜDÜRLÜĞÜ</span></li>\n" * 1200)
    assert len(html.encode()) > 100_000
    gz = d1.gzip_page(html)
    assert gz == d1.gzip_page(html) and len(gz) < 10_000 and len(d1.gz_parts(gz)) == 1
    big = d1.gzip_page(RANDOM)
    assert len(d1.gz_parts(big)) >= 2 and b"".join(d1.gz_parts(big)) == big             # split compressed bytes, never members


def test_statement_over_limit_is_rejected(monkeypatch):
    monkeypatch.setattr(d1, "PART_BYTES", 60_000)                                       # hex literal would be 120 KB
    with pytest.raises(ValueError, match="over"):
        d1.page_statements("/p/", d1.gzip_page(RANDOM), "s")


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
    """Applies batch files to an in-memory SQLite, like `wrangler d1 execute` would (the v1 tables exist to be dropped)."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("CREATE TABLE pages(path TEXT); CREATE TABLE page_meta(path TEXT);")
        self.files: list[Path] = []

    def __call__(self, f: Path):
        self.files.append(f)
        self.db.executescript(f.read_bytes().decode("utf-8"))

    def pages(self) -> dict[str, str]:
        try:
            paths = [r[0] for r in self.db.execute("SELECT path FROM pg WHERE part=0")]
        except sqlite3.OperationalError:
            return {}
        return {p: _read_back(self.db, p) for p in paths}


def _sync(tmp_path, stage, fake, **kw):
    return d1.sync_pages(stage_db=stage, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b",
                         execute=fake, log=lambda m: None, **kw)


def test_first_sync_uploads_everything_drops_v1_then_second_is_a_noop(tmp_path):
    pages = {"/ihale/a/": "A" * 40_000, "/ihale/b/": NASTY, "/gun/2026-11-18/1/": "<p>x</p>"}
    stage = _mk_stage(tmp_path / "s.sqlite", pages)
    fake = FakeD1()
    plan = _sync(tmp_path, stage, fake)
    assert len(plan.upserts) == 3 and plan.deletes == [] and fake.pages() == pages
    assert plan.rows == 3                                                  # one gzip row per page, no meta rows
    assert "DROP TABLE IF EXISTS pages" in fake.files[-1].read_text(encoding="utf-8")
    assert fake.db.execute("SELECT count(*) FROM sqlite_master WHERE name IN ('pages','page_meta')").fetchone()[0] == 0
    fake2 = FakeD1()
    fake2.db = fake.db
    plan2 = _sync(tmp_path, stage, fake2)
    assert plan2.upserts == [] and plan2.deletes == [] and plan2.unchanged == 3 and plan2.rows == 0
    assert fake2.files == []                                               # nothing to upload: no wrangler import at all


def test_changed_page_shrinks_and_deleted_page_is_removed(tmp_path):
    big = RANDOM * 2                                                       # several gzip parts
    stage = _mk_stage(tmp_path / "s.sqlite", {"/ihale/a/": big, "/ihale/b/": "keep", "/ihale/c/": "gone"})
    fake = FakeD1()
    _sync(tmp_path, stage, fake)
    old_parts = fake.db.execute("SELECT count(*) FROM pg WHERE path='/ihale/a/'").fetchone()[0]
    assert old_parts >= 3
    stage2 = _mk_stage(tmp_path / "s2.sqlite", {"/ihale/a/": "short", "/ihale/b/": "keep", "/ihale/new/": "n"})
    plan = _sync(tmp_path, stage2, fake, max_delete_fraction=1.0)
    assert [u[0] for u in plan.upserts] == ["/ihale/a/", "/ihale/new/"] and plan.deletes == ["/ihale/c/"]
    assert plan.rows == (old_parts + 1) + 1 + 1                            # a: old parts + 1 new part; new; delete c
    assert fake.db.execute("SELECT count(*) FROM pg WHERE path='/ihale/a/'").fetchone()[0] == 1       # no stale part
    assert fake.pages() == {"/ihale/a/": "short", "/ihale/b/": "keep", "/ihale/new/": "n"}
    assert {k for k in d1.load_manifest(tmp_path / "m.json") if not k.startswith("__")} == {"/ihale/a/", "/ihale/b/", "/ihale/new/"}


def test_deletions_run_after_the_between_step(tmp_path):
    stage = _mk_stage(tmp_path / "s.sqlite", {"/ihale/a/": "a", "/ihale/c/": "c"})
    fake = FakeD1()
    _sync(tmp_path, stage, fake)
    stage2 = _mk_stage(tmp_path / "s2.sqlite", {"/ihale/a/": "a2"})
    events = []
    d1.sync_pages(stage_db=stage2, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b",
                  execute=lambda f: (events.append("exec"), fake(f)), between=lambda: events.append("deploy"),
                  log=lambda m: None, max_delete_fraction=1.0)
    assert events == ["exec", "deploy", "exec"]                             # upserts, Worker deploy, deletions
    assert "/ihale/c/" not in fake.pages()


def test_row_guard_counts_todays_tally_and_refuses_before_any_write(tmp_path):
    stage = _mk_stage(tmp_path / "s.sqlite", {f"/ihale/{i}/": "x" for i in range(30)})
    fake = FakeD1()
    with pytest.raises(d1.BudgetExceeded, match="over the budget"):
        _sync(tmp_path, stage, fake, max_rows=50, rows_today=21)                    # 30 rows + 21 already today > 50
    assert fake.files == [] and not (tmp_path / "m.json").exists()
    assert d1.D1_MAX_ROWS_PER_RUN == 80_000 and d1.D1_DAILY_LIMIT == 100_000        # 80% of the free daily writes


def test_dry_run_reports_and_changes_nothing(tmp_path):
    stage = _mk_stage(tmp_path / "s.sqlite", {"/ihale/a/": "a" * 5000, "/ihale/b/": RANDOM})
    fake = FakeD1()
    logs = []
    plan = d1.sync_pages(stage_db=stage, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b", execute=fake,
                         dry_run=True, rows_today=1000, log=logs.append)
    assert fake.files == [] and not (tmp_path / "m.json").exists() and not (tmp_path / "b").exists()
    text = "\n".join(logs)
    assert "2 changed/new pages" in text and f"rows to write: {plan.rows}" in text and "gzip bytes stored" in text
    assert "rows written today (UTC): 1000" in text and f"with this run {1000 + plan.rows}" in text and "SQL batch files: 1" in text
    assert plan.rows >= 2 and plan.gz_bytes > 0 and plan.max_html_bytes >= 5000


def test_failed_batch_keeps_manifest_for_the_uncommitted_pages_only(tmp_path, monkeypatch):
    pages = {f"/ihale/{i:03d}/": "".join(_rnd.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(6000)) for i in range(40)}
    stage = _mk_stage(tmp_path / "s.sqlite", pages)
    fake = FakeD1()
    calls = []

    def flaky(f):
        calls.append(f)
        if len(calls) == 2:
            raise RuntimeError("boom")
        fake(f)
    monkeypatch.setattr(d1, "BATCH_BYTES", 60_000)
    with pytest.raises(RuntimeError, match="boom"):
        _sync(tmp_path, stage, flaky)
    done = {k for k in d1.load_manifest(tmp_path / "m.json") if not k.startswith("__")}
    assert 0 < len(done) < 40
    assert done == set(fake.pages())                                         # manifest == what really reached D1
    plan = _sync(tmp_path, stage, fake)                                      # re-run finishes only the rest
    assert len(plan.upserts) == 40 - len(done) and fake.pages() == pages


# ------------------------------------------------------------------ transient upload errors
def test_transient_upload_errors_are_retried_twice_with_pauses(monkeypatch):
    sleeps, calls = [], []

    def flaky(args):
        calls.append(args)
        if len(calls) <= 2:
            raise RuntimeError("wrangler d1 execute failed (1):\nFile could not be uploaded. Please retry.\nServiceUnavailable")
        return "ok"
    monkeypatch.setattr(sitegen, "_run_wrangler", flaky)
    monkeypatch.setattr(sitegen, "log", lambda m: None)
    assert sitegen.run_with_retries(["d1", "execute"], sleep=sleeps.append) == "ok"
    assert sleeps == [15, 45] and len(calls) == 3


def test_retries_give_up_after_two_and_skip_other_errors(monkeypatch):
    monkeypatch.setattr(sitegen, "log", lambda m: None)
    calls = []
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda a: calls.append(a) or (_ for _ in ()).throw(RuntimeError("ECONNRESET")))
    with pytest.raises(RuntimeError, match="ECONNRESET"):
        sitegen.run_with_retries(["x"], sleep=lambda s: None)
    assert len(calls) == 3                                                     # first try + 2 retries
    calls.clear()
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda a: calls.append(a) or (_ for _ in ()).throw(RuntimeError("SQLITE_ERROR: syntax")))
    with pytest.raises(RuntimeError, match="SQLITE_ERROR"):
        sitegen.run_with_retries(["x"], sleep=lambda s: None)
    assert len(calls) == 1                                                     # not transient: no retry
    calls.clear()
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda a: calls.append(a) or (_ for _ in ()).throw(sitegen.PaymentRequired("STOP: card")))
    with pytest.raises(sitegen.PaymentRequired):
        sitegen.run_with_retries(["x"], sleep=lambda s: None)
    assert len(calls) == 1                                                     # never retry a payment prompt


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


def test_deploy_remote_order_timing_log_and_placeholder_guard(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path)
    calls, logs = [], []

    def fake(args):
        calls.append(args)
        return "Published ihale-gozlemevi\n  https://ihale-gozlemevi.example.workers.dev\n" if args[0] == "deploy" else ""
    monkeypatch.setattr(sitegen, "_run_wrangler", fake)
    monkeypatch.setattr(sitegen, "log", logs.append)
    monkeypatch.setattr(sitegen, "_d1_id", lambda: sitegen.PLACEHOLDER_D1_ID)
    with pytest.raises(RuntimeError, match="placeholder"):
        sitegen.deploy(dist, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b")
    assert calls == []
    monkeypatch.setattr(sitegen, "_d1_id", lambda: "11111111-2222-3333-4444-555555555555")
    url = sitegen.deploy(dist, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b")
    assert url == "https://ihale-gozlemevi.example.workers.dev"
    kinds = [("d1:" + ("remote" if "--remote" in c else "local") if c[:2] == ["d1", "execute"] else c[0] + (":" + c[1] if c[0] == "d1" else ""))
             for c in calls]
    # upserts (one batch), Worker deploy, then the one-time drop of the v1 tables, then the usage lookups
    assert kinds == ["d1:remote", "deploy", "d1:remote", "d1:info", "d1:insights"]
    assert sum(1 for m in logs if m.startswith("D1 execute batch-")) == 2 and any("start" in m and " s " in m for m in logs)
    usage = json.loads((tmp_path / "datadir" / "d1-usage.json").read_text(encoding="utf-8"))
    assert usage["rows_written"] == 2                                          # per executed batch, not at the end


def test_deploy_dry_run_makes_no_wrangler_call_and_no_state_change(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path)
    logs = []
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda args: pytest.fail("wrangler must not be called in a dry run"))
    monkeypatch.setattr(sitegen, "log", logs.append)
    monkeypatch.setattr(sitegen, "_d1_id", lambda: "11111111-2222-3333-4444-555555555555")
    assert sitegen.deploy(dist, dry_run=True, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b") == "dry-run"
    assert not (tmp_path / "m.json").exists() and not (tmp_path / "b").exists()
    assert not (tmp_path / "datadir" / "d1-usage.json").exists()
    assert any("rows to write: 2" in m for m in logs)
    sitegen_dist = tmp_path / "dist"
    (sitegen_dist / "tokens").mkdir()                                          # guards still run before a dry run
    with pytest.raises(RuntimeError, match="design preview"):
        sitegen.deploy(dist, dry_run=True)


def test_deploy_refuses_when_todays_tally_plus_plan_is_over_the_limit(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path)
    from datetime import datetime, timezone
    d1.add_rows_written(tmp_path / "datadir" / "d1-usage.json", 79_999, datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda args: pytest.fail("no wrangler call expected"))
    monkeypatch.setattr(sitegen, "log", lambda m: None)
    monkeypatch.setattr(sitegen, "_d1_id", lambda: "11111111-2222-3333-4444-555555555555")
    with pytest.raises(sitegen.BudgetExceeded, match="already written today"):
        sitegen.deploy(dist, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b")


def test_v2_manifest_file_is_separate_from_the_v1_one(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path)
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda args: "")
    monkeypatch.setattr(sitegen, "log", lambda m: None)
    (tmp_path / "datadir").mkdir(exist_ok=True)
    (tmp_path / "datadir" / "d1-manifest-local.json").write_text('{"/ihale/a/": ["old", 3]}', encoding="utf-8")   # a v1 manifest
    sitegen.deploy(dist, local=True, batch_dir=tmp_path / "b")
    assert (tmp_path / "datadir" / f"d1-manifest-local-{d1.MANIFEST_VERSION}.json").is_file()
    assert json.loads((tmp_path / "datadir" / "d1-manifest-local.json").read_text(encoding="utf-8")) == {"/ihale/a/": ["old", 3]}


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
    sitegen.build(SAMPLE, out)
    (out / "tokens").mkdir()
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
    d1.add_rows_written(tmp_path / "d1-usage.json", 85_000, "2026-11-19")          # the tally is kept per executed batch
    w = sitegen.report_d1_usage(tmp_path, d1.Plan(rows=85_000, total_bytes=124_000_000), "2026-11-19")
    assert len(w) == 2 and (tmp_path / "logs" / "d1-usage-warning.txt").is_file()
    assert any(m.startswith("WARNING") for m in logs)
    outputs["info"] = '{"file_size": 1000}'
    assert sitegen.report_d1_usage(tmp_path, d1.Plan(rows=1, total_bytes=10), "2026-11-20") == []     # a new UTC day resets it
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

# ------------------------------------------------------------------ daily write budget (80% of the free 100k rows/day)
def test_budget_exceeded_prints_both_numbers_and_writes_nothing(tmp_path):
    stage = _mk_stage(tmp_path / "s.sqlite", {f"/ihale/{i}/": f"p{i}" for i in range(35_200)})        # 35,200 rows planned
    fake = FakeD1()
    logs = []
    with pytest.raises(d1.BudgetExceeded) as ei:
        d1.sync_pages(stage_db=stage, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b", execute=fake,
                      between=lambda: pytest.fail("the Worker must not be deployed"), rows_today=44_807, log=logs.append)
    msg = str(ei.value)
    assert "44807 rows already written today" in msg and "35200 planned" in msg and "80007" in msg and "80000" in msg
    assert "Try again tomorrow" in msg and "unchanged" in msg
    assert fake.files == [] and not (tmp_path / "m.json").exists() and not (tmp_path / "b").exists()
    assert any("rows written today (UTC): 44807" in m for m in logs)                                  # the numbers are printed


def test_budget_boundary_is_inclusive(tmp_path):
    stage = _mk_stage(tmp_path / "s.sqlite", {"/ihale/a/": "a", "/ihale/b/": "b"})
    plan = d1.sync_pages(stage_db=stage, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b", execute=FakeD1(),
                         rows_today=79_998, log=lambda m: None)                                      # exactly 80,000: allowed
    assert plan.rows == 2
    with pytest.raises(d1.BudgetExceeded):
        d1.sync_pages(stage_db=_mk_stage(tmp_path / "s2.sqlite", {"/ihale/c/": "c"}), manifest_path=tmp_path / "m2.json",
                      batch_dir=tmp_path / "b2", execute=FakeD1(), rows_today=80_000, log=lambda m: None)


def test_deploy_budget_exceeded_does_no_d1_write_and_no_worker_deploy(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    dist = _fake_dist(tmp_path)
    d1.add_rows_written(tmp_path / "datadir" / "d1-usage.json", 79_999, datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    calls = []
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda args: calls.append(args) or "")
    monkeypatch.setattr(sitegen, "log", lambda m: None)
    monkeypatch.setattr(sitegen, "_d1_id", lambda: "11111111-2222-3333-4444-555555555555")
    with pytest.raises(sitegen.BudgetExceeded):
        sitegen.deploy(dist, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b")
    assert calls == []                                                     # no d1 execute, no `wrangler deploy`
    assert not (tmp_path / "b").exists() and not (tmp_path / "m.json").exists()
    assert issubclass(sitegen.BudgetExceeded, RuntimeError)

# ------------------------------------------------------------------ empty-site guard and staging location
def _write_meta(tmp_path, records):
    p = tmp_path / "datadir" / "export" / "meta.json"
    p.write_text(json.dumps({"counts": {"2026-11-18": {"records": records}}}), encoding="utf-8")


def test_guard_a_refuses_a_nearly_empty_export_and_prints_the_numbers(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path)
    _write_meta(tmp_path, 999)
    logs = []
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda args: pytest.fail("nothing may be deployed"))
    monkeypatch.setattr(sitegen, "log", logs.append)
    monkeypatch.setattr(sitegen, "_d1_id", lambda: "11111111-2222-3333-4444-555555555555")
    for dry in (False, True):                                               # the dry-run plan refuses too
        with pytest.raises(sitegen.EmptySiteError, match="only 999 records"):
            sitegen.deploy(dist, dry_run=dry, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b")
    assert any("holds 999 records (minimum 1000)" in m for m in logs)
    assert not (tmp_path / "b").exists() and not (tmp_path / "m.json").exists()
    _write_meta(tmp_path, 1000)                                             # exactly the minimum passes
    assert sitegen.deploy(dist, dry_run=True, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b") == "dry-run"
    (tmp_path / "datadir" / "export" / "meta.json").unlink()                # an unreadable export is refused as well
    with pytest.raises(sitegen.EmptySiteError, match="cannot read"):
        sitegen.deploy(dist, dry_run=True, manifest_path=tmp_path / "m.json", batch_dir=tmp_path / "b")


def test_guard_b_refuses_deleting_more_than_five_percent_of_the_deployed_pages(tmp_path):
    pages = {f"/ihale/{i:03d}/": f"p{i}" for i in range(100)}
    fake = FakeD1()
    _sync(tmp_path, _mk_stage(tmp_path / "s.sqlite", pages), fake)
    fake.files.clear()
    logs = []
    six_gone = {k: v for k, v in pages.items() if int(k[-4:-1]) >= 6}       # 6 of 100 deleted = 6%
    with pytest.raises(d1.EmptySiteError, match=r"delete 6 of 100 deployed pages \(6.0%"):
        d1.sync_pages(stage_db=_mk_stage(tmp_path / "s2.sqlite", six_gone), manifest_path=tmp_path / "m.json",
                      batch_dir=tmp_path / "b", execute=fake, log=logs.append)
    assert fake.files == [] and any("deletes 6 of 100 deployed pages (6.0%, maximum 5%)" in m for m in logs)
    assert len(d1.load_manifest(tmp_path / "m.json")) >= 100                # nothing was touched
    five_gone = {k: v for k, v in pages.items() if int(k[-4:-1]) >= 5}      # exactly 5% is allowed
    plan = d1.sync_pages(stage_db=_mk_stage(tmp_path / "s3.sqlite", five_gone), manifest_path=tmp_path / "m.json",
                         batch_dir=tmp_path / "b", execute=fake, log=lambda m: None)
    assert len(plan.deletes) == 5
    with pytest.raises(d1.EmptySiteError):                                  # an empty staged site would delete everything
        d1.sync_pages(stage_db=_mk_stage(tmp_path / "s4.sqlite", {}), manifest_path=tmp_path / "m.json",
                      batch_dir=tmp_path / "b2", execute=fake, dry_run=True, log=lambda m: None)


def test_guard_b_applies_to_the_dry_run_plan(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path)
    (tmp_path / "datadir").mkdir(exist_ok=True)
    manifest = tmp_path / "m.json"
    d1.save_manifest(manifest, {f"/ihale/gone{i}/": ["x", 1] for i in range(30)} | {"/ihale/a/": ["old", 1]})
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda args: pytest.fail("nothing may be deployed"))
    monkeypatch.setattr(sitegen, "log", lambda m: None)
    monkeypatch.setattr(sitegen, "_d1_id", lambda: "11111111-2222-3333-4444-555555555555")
    with pytest.raises(sitegen.EmptySiteError, match="delete 30 of 31"):
        sitegen.deploy(dist, dry_run=True, manifest_path=manifest, batch_dir=tmp_path / "b")


def test_guard_c_refuses_when_index_html_is_missing(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path)
    (dist / "index.html").unlink()
    logs = []
    monkeypatch.setattr(sitegen, "_run_wrangler", lambda args: pytest.fail("nothing may be deployed"))
    monkeypatch.setattr(sitegen, "log", logs.append)
    with pytest.raises(sitegen.EmptySiteError, match="nothing to deploy"):
        sitegen.deploy(dist, dry_run=True)
    assert any("guard (c)" in m and "index.html" in m for m in logs)
    assert issubclass(sitegen.EmptySiteError, RuntimeError)


def test_default_staging_lives_in_the_data_dir_not_the_repo(tmp_path):
    p = d1.staging_path(Path(sitegen.SITE_DIR) / "dist")
    assert p == (tmp_path / "datadir").resolve() / "site-build" / "dist-pages.sqlite"
    assert "OneDrive" not in str(p) and not str(p).startswith(str(Path(sitegen.SITE_DIR)))
    other = tmp_path / "x" / "dist"
    assert d1.staging_path(other) == tmp_path / "x" / "dist-pages.sqlite"        # ad-hoc output dirs keep it next to them
    st = d1.Stage(p)                                                            # creating it makes the site-build folder
    st.add("/ihale/a/", "a")
    st.close()
    assert p.is_file()


def test_missing_data_dir_fails_the_default_staging_loudly(tmp_path, monkeypatch):
    from ihale import config
    monkeypatch.delenv("IHALE_ALLOW_NEW_DATA_DIR", raising=False)
    monkeypatch.setenv("IHALE_DATA_DIR", str(tmp_path / "unplugged"))
    with pytest.raises(config.DataDirMissing):
        d1.staging_path(Path(sitegen.SITE_DIR) / "dist")
