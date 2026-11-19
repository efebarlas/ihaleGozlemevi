"""CLI / pipeline behaviour with EKAP client, parser and sitegen replaced by fakes (fully offline)."""
import json
from datetime import date
from types import SimpleNamespace

import pytest

from ihale import cli, config, ekap, pipeline
from ihale.store import Store

from rec_helpers import rec

D = date(2026, 11, 18)  # a Wednesday


class FakeClient:
    """Stands in for EkapClient. `plan` maps date → 'ok' | 'none' | 'blocked' | 'budget' | Exception."""

    instances = []
    requests_made = 0

    def __init__(self, plan=None, max_requests=None):
        self.plan = plan or {}
        self.max_requests = max_requests
        self.calls = []
        FakeClient.instances.append(self)

    def fetch(self, day, type_, root=None, force=False):
        self.calls.append((day, type_))
        what = self.plan.get(day, "ok")
        if what == "none":
            raise ekap.NoBulletinError("no bulletin")
        if what == "blocked":
            raise ekap.BlockedError("HTTP 429")
        if what == "budget":
            raise ekap.RequestBudgetExceeded("cap")
        if isinstance(what, Exception):
            raise what
        d, zpath = ekap.bulletin_paths(config.bulletins_dir(), day, type_)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"BULTEN_{day:%d%m%Y}_{type_.upper()}_SONUC.pdf").write_bytes(b"%PDF fake")
        zpath.write_bytes(b"PK")
        return d


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Fakes for client, parser, sitegen; returns a namespace to inspect what happened."""
    FakeClient.instances = []
    e = SimpleNamespace(plan={}, built=[], deployed=[], parse_calls=[], parse_error=None,
                        build_error=None, today=D)

    def make_client(max_requests=None):
        return FakeClient(e.plan, max_requests)

    def parse_bulletin(pdf, day, type_):
        e.parse_calls.append((pdf.name, day, type_))
        if e.parse_error:
            raise e.parse_error
        return [rec(1, day=day, type_=type_), rec(2, day=day, type_=type_, ikn="2026/2", yuklenici="B", gecerli=1, toplam=1)]

    def build(export_dir, out_dir):
        if e.build_error:
            raise e.build_error
        e.built.append((export_dir, out_dir))

    monkeypatch.setattr(pipeline, "make_client", make_client)
    monkeypatch.setattr(pipeline, "parse_module", lambda: SimpleNamespace(parse_bulletin=parse_bulletin))
    monkeypatch.setattr(pipeline, "sitegen_module",
                        lambda: SimpleNamespace(build=build, deploy=lambda: e.deployed.append(True)))
    monkeypatch.setattr(pipeline, "repo_root", lambda: tmp_path / "repo")
    monkeypatch.setattr(pipeline, "today_istanbul", lambda: e.today)
    return e


def run(*argv):
    return cli.main(list(argv))


# ------------------------------------------------------------------ run
def test_run_happy_path(env, data_dir):
    assert run("run", "--date", "18.11.2026") == 0
    (client,) = FakeClient.instances
    assert client.calls == [(D, "mal")]
    assert env.parse_calls == [("BULTEN_18112026_MAL_SONUC.pdf", D, "mal")]
    assert len(Store().all_records()) == 2
    meta = json.loads((data_dir / "export" / "meta.json").read_text(encoding="utf-8"))
    assert meta["latest_date"] == "2026-11-18"
    assert env.built == [(data_dir / "export", env.built[0][1])]
    assert env.built[0][1].parts[-2:] == ("site", "dist")
    assert env.deployed == [True]
    assert (data_dir / "logs" / "2026-11-18.log").read_text(encoding="utf-8").count("run done") == 1


def test_run_default_date_is_today_istanbul(env):
    assert run("run") == 0
    assert FakeClient.instances[0].calls == [(D, "mal")]


def test_run_no_deploy(env):
    assert run("run", "--no-deploy") == 0
    assert env.built and env.deployed == []


def test_run_no_bulletin_still_exports_builds_deploys(env, data_dir):
    Store().replace_day(date(2026, 11, 17), "mal", [rec(1, day=date(2026, 11, 17))])
    env.plan[D] = "none"
    assert run("run") == 0
    assert env.parse_calls == []
    meta = json.loads((data_dir / "export" / "meta.json").read_text(encoding="utf-8"))
    assert meta["dates"] == ["2026-11-17"]
    assert env.built and env.deployed == [True]
    assert not (data_dir / "BLOCKED").exists()


def test_run_blocked_writes_marker_no_build_no_deploy(env, data_dir):
    env.plan[D] = "blocked"
    code = run("run")
    assert code == pipeline.EXIT_BLOCKED == 3
    marker = data_dir / "BLOCKED"
    assert marker.exists() and "HTTP 429" in marker.read_text(encoding="utf-8")
    assert env.deployed == [] and env.built == []


def test_run_refuses_to_scrape_while_marker_present(env, data_dir):
    pipeline.write_blocked_marker("earlier block")
    assert run("run") == 3
    assert FakeClient.instances == [] and env.deployed == [] and env.built == []
    # deleting the marker is the human's release
    (data_dir / "BLOCKED").unlink()
    assert run("run") == 0 and env.deployed == [True]


def test_fetch_and_backfill_also_refuse_with_marker(env, data_dir):
    pipeline.write_blocked_marker("x")
    assert run("fetch", "--date", "18.11.2026") == 3
    assert run("backfill", "--days", "3") == 3
    assert FakeClient.instances == []


def test_run_parse_failure_exits_1_without_deploy(env):
    env.parse_error = RuntimeError("boom")
    assert run("run") == 1
    assert env.deployed == []


def test_run_other_ekap_error_exits_1_without_deploy(env):
    env.plan[D] = ekap.UnexpectedResponseError("weird")
    assert run("run") == 1
    assert env.deployed == [] and env.built == []


def test_run_build_failure_does_not_deploy(env):
    env.build_error = RuntimeError("template broke")
    assert run("run") == 1 and env.deployed == []


def test_run_multiple_types(env):
    assert run("run", "--types", "mal,hizmet") == 0
    assert FakeClient.instances[0].calls == [(D, "mal"), (D, "hizmet")]


def test_run_rejects_unknown_type(env):
    with pytest.raises(SystemExit) as e:
        run("run", "--types", "bogus")
    assert e.value.code == 2


def test_run_rerun_same_day_is_idempotent(env):
    run("run")
    run("run")
    assert len(Store().all_records()) == 2


def test_log_handlers_cleaned_up(env):
    import logging
    run("run")
    assert logging.getLogger("ihale").handlers == []


# ------------------------------------------------------------------ backfill
def test_backfill_oldest_first_skips_weekends_and_nobulletin(env):
    env.today = date(2026, 11, 23)   # Monday; window Tue 17 … Mon 23, with Sat 21 / Sun 22 inside
    env.plan[date(2026, 11, 19)] = "none"   # holiday
    assert run("backfill", "--days", "7", "--max-requests", "40") == 0
    (client,) = FakeClient.instances
    assert [c[0].day for c in client.calls] == [17, 18, 19, 20, 23]
    assert client.max_requests == 40
    assert sorted(r.record.bulletin_date.day for r in Store().all_records()) == [17, 17, 18, 18, 20, 20, 23, 23]
    assert env.built == [] and env.deployed == []     # backfill never builds or deploys
    assert (config.data_dir() / "export" / "meta.json").exists()


def test_backfill_default_cap_not_raised(env):
    run("backfill", "--days", "2")
    assert FakeClient.instances[0].max_requests is None   # EkapClient default applies


def test_backfill_skips_days_already_local_and_stored(env):
    run("backfill", "--days", "1")                  # Wed 18th fetched + parsed
    FakeClient.instances.clear()
    env.parse_calls.clear()
    run("backfill", "--days", "1")
    assert FakeClient.instances[0].calls == [] and env.parse_calls == []


def test_backfill_parses_local_bulletin_missing_from_store(env):
    FakeClient(env.plan).fetch(D, "mal")            # put the pdf + zip on disk only
    FakeClient.instances.clear()
    run("backfill", "--days", "1")
    assert FakeClient.instances[0].calls == [] and len(env.parse_calls) == 1


def test_backfill_stops_immediately_on_block(env, data_dir):
    env.today = date(2026, 11, 20)
    env.plan[date(2026, 11, 18)] = "blocked"
    assert run("backfill", "--days", "4") == 3
    assert [c[0].day for c in FakeClient.instances[0].calls] == [17, 18]
    assert (data_dir / "BLOCKED").exists()


def test_backfill_cap_reached_reports_5_and_keeps_progress(env):
    env.today = date(2026, 11, 20)
    env.plan[date(2026, 11, 19)] = "budget"
    assert run("backfill", "--days", "4") == 5
    assert sorted({r.record.bulletin_date.day for r in Store().all_records()}) == [17, 18]


def test_backfill_requires_positive_days(env):
    with pytest.raises(SystemExit):
        run("backfill", "--days", "0")


# ------------------------------------------------------------------ other commands
def test_parse_command_stores_local_bulletin(env):
    FakeClient(env.plan).fetch(D, "mal")
    assert run("parse", "--date", "2026-11-18", "--type", "mal") == 0
    assert len(Store().all_records()) == 2


def test_parse_command_without_local_pdf_fails(env):
    assert run("parse", "--date", "18.11.2026") == 1


def test_flag_and_export_commands(env, data_dir):
    Store().replace_day(D, "mal", [rec(1, gecerli=1, toplam=1)])
    assert run("flag") == 0 and run("export") == 0
    day = json.loads((data_dir / "export" / "days" / "2026-11-18.json").read_text(encoding="utf-8"))
    assert day["tenders"][0]["flags"][0]["code"] == "tek_teklif"


def test_build_and_deploy_commands(env, data_dir):
    assert run("build") == 0 and run("deploy") == 0
    assert env.built[0][0] == data_dir / "export" and env.deployed == [True]


def test_fetch_still_works_and_marks_block(env, data_dir, monkeypatch):
    monkeypatch.setattr(ekap, "EkapClient", lambda form_cache=None: FakeClient(env.plan))
    assert run("fetch", "--date", "18.11.2026") == 0
    env.plan[D] = "none"
    assert run("fetch", "--date", "18.11.2026", "--force") == 4
    env.plan[D] = "blocked"
    assert run("fetch", "--date", "18.11.2026") == 3 and (data_dir / "BLOCKED").exists()


def test_fetch_parser_keeps_date_string():
    a = cli.build_parser().parse_args(["fetch", "--date", "18.11.2026", "--type", "mal"])
    assert (a.date, a.type) == ("18.11.2026", "mal")


def test_parse_day_formats():
    assert cli.parse_day("18.11.2026") == D == cli.parse_day("2026-11-18")
