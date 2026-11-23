"""backfill-history: fetch-only walk backwards (fake HTTP session, no network, no real sleeping)."""
import io
import json
import random
import zipfile
from datetime import date, datetime, time, timedelta, timezone

import pytest

from ihale import cli, config, ekap, pipeline
from ihale import backfill_history as bh
from ihale.store import Store

CODE2TYPE = {v: k for k, v in ekap.TYPE_CODES.items()}
NIGHT = datetime(2026, 11, 22, 23, 0, tzinfo=timezone.utc)


def zip_bytes():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.pdf", b"%PDF")
    return b.getvalue()


class Sess:
    """GET -> form; POST -> zip, or the no-bulletin notice for days in `empty`, or a login wall for `block_on`."""

    def __init__(self, form, empty=(), block_on=None):
        self.headers, self.form, self.empty, self.block_on = {}, form, set(empty), block_on
        self.posts = []

    def request(self, method, url, data=None, timeout=None, **_):
        if method == "GET":
            return ekap._Response(200, {"Content-Type": "text/html"}, self.form.encode("utf-8"))
        d = datetime.strptime(data[ekap.DATE_FIELD], "%d.%m.%Y").date()
        t = CODE2TYPE[data[ekap.TYPE_FIELD]]
        self.posts.append((d, t))
        if self.block_on == (d, t):
            return ekap._Response(200, {"Content-Type": "text/html"}, "<html>Giriş Yap</html>".encode("utf-8"))
        if (d, t) in self.empty or d in self.empty:
            return ekap._Response(200, {"Content-Type": "text/html"}, "<script>alert('Bülten bulunamadı');</script>".encode("utf-8"))
        hdr = {"Content-Type": "text/html", "Content-Disposition": f'attachment; filename="BULTEN_{d:%d%m%Y}_{t.upper()}.zip"'}
        return ekap._Response(200, hdr, zip_bytes())


class NoWait(ekap.RateLimiter):
    def wait(self):
        pass


def go(form, begin=date(2026, 10, 20), sess=None, sleeps=None, now=NIGHT, **kw):
    sess = sess or Sess(form)
    sleeps = sleeps if sleeps is not None else []
    c = ekap.EkapClient(limiter=NoWait(config.data_dir() / "ekap-last-request.txt"), session=sess, max_requests=500)
    kw.setdefault("earliest", date(2026, 10, 1))
    code = bh.run(c, begin=begin, now=lambda: now, sleep=sleeps.append, rng=random.Random(1), **kw)
    return code, sess, sleeps, c


def state():
    return json.loads((config.data_dir() / "backfill-state.json").read_text(encoding="utf-8"))


def test_walks_back_business_days_in_type_order_and_stops_at_run_budget(form_html):
    code, sess, sleeps, c = go(form_html, max_requests=7)          # 1 form GET + 6 POSTs
    assert code == 0
    # Tue 20 Oct (Wed 21st is the stored day), then Mon 19; weekend 17/18 skipped without a request
    assert sess.posts == [(date(2026, 10, 20), "mal"), (date(2026, 10, 20), "hizmet"), (date(2026, 10, 20), "yapim"),
                          (date(2026, 10, 19), "mal"), (date(2026, 10, 19), "hizmet"), (date(2026, 10, 19), "yapim")]
    assert ekap.bulletin_paths(config.bulletins_dir(), date(2026, 10, 20), "mal")[1].exists()
    assert len(sleeps) == 6 and all(150 <= s <= 240 for s in sleeps) and len(set(sleeps)) > 1   # gap before every request but the 1st
    assert "request budget" in state()["stop_reason"]
    log = (config.data_dir() / "logs" / "backfill-progress.log").read_text(encoding="utf-8")
    assert "2026-10-20 mal fetched requests_today=2" in log


def test_skips_cached_and_known_empty_and_persists_empty(form_html):
    pipeline._remember_no_bulletin(date(2026, 10, 20), "mal")
    ekap.save_zip(config.bulletins_dir(), date(2026, 10, 20), "hizmet", zip_bytes())
    sess = Sess(form_html, empty={date(2026, 10, 19)})
    code, sess, _, _ = go(form_html, sess=sess, max_requests=20, earliest=date(2026, 10, 19))
    assert code == 0
    assert sess.posts == [(date(2026, 10, 20), "yapim"), (date(2026, 10, 19), "mal"),
                          (date(2026, 10, 19), "hizmet"), (date(2026, 10, 19), "yapim")]
    assert "2026-10-19 mal" in pipeline._known_no_bulletin()
    st = state()
    assert st["skipped_cached"] == 1 and st["skipped_empty"] == 1 and st["no_bulletin"] == 3 and "done" in st["stop_reason"]
    # a second run asks for nothing
    code, sess2, _, c2 = go(form_html, max_requests=20, earliest=date(2026, 10, 19))
    assert code == 0 and sess2.posts == [] and c2.requests_made == 0


def test_block_stops_at_once_writes_marker_and_saves_evidence(form_html, data_dir):
    sess = Sess(form_html, block_on=(date(2026, 10, 20), "hizmet"))
    code, sess, _, _ = go(form_html, sess=sess, max_requests=50)
    assert code == pipeline.EXIT_BLOCKED
    assert sess.posts[-1] == (date(2026, 10, 20), "hizmet") and len(sess.posts) == 2
    assert pipeline.blocked_marker().exists()
    assert list((data_dir / "logs" / "blocked-responses").glob("*-hizmet-2026-10-20.html"))
    # and the marker is honoured on the next start: nothing is sent
    code, sess2, _, c2 = go(form_html, max_requests=50)
    assert code == pipeline.EXIT_BLOCKED and c2.requests_made == 0


def test_shared_daily_cap_exit_5(form_html):
    b = ekap.DailyBudget(config.data_dir(), 200)
    for _ in range(199):
        b.reserve()
    code, sess, _, _ = go(form_html, max_requests=50)             # form GET takes the 200th
    assert code == pipeline.EXIT_CAP and sess.posts == []


def test_outside_window_sends_nothing(form_html):
    code, sess, _, c = go(form_html, now=datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc))
    assert code == 0 and c.requests_made == 0 and "outside window" in state()["stop_reason"]


def test_window_closing_during_wait_stops(form_html):
    ticks = iter([NIGHT, NIGHT, datetime(2026, 11, 23, 4, 31, tzinfo=timezone.utc)])
    last = [NIGHT]

    def now():
        last[0] = next(ticks, last[0])
        return last[0]
    sess = Sess(form_html)
    c = ekap.EkapClient(limiter=NoWait(config.data_dir() / "ekap-last-request.txt"), session=sess, max_requests=500)
    code = bh.run(c, begin=date(2026, 10, 20), earliest=date(2026, 10, 1), now=now, sleep=lambda s: None)
    assert code == 0 and "window closed" in state()["stop_reason"] and sess.posts == []


def test_window_wraps_midnight():
    w = bh.parse_window("22:00-04:30")
    assert bh.in_window(datetime(2026, 1, 1, 22, 0, tzinfo=timezone.utc), w)
    assert bh.in_window(datetime(2026, 1, 2, 4, 29, tzinfo=timezone.utc), w)
    assert not bh.in_window(datetime(2026, 1, 2, 4, 30, tzinfo=timezone.utc), w)
    assert not bh.in_window(datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc), w)
    with pytest.raises(ValueError):
        bh.parse_window("nonsense")


def test_start_day_derived_from_store_and_cli(form_html, monkeypatch):
    from tests.rec_helpers import rec
    store = Store()
    assert bh.start_day(store) is None
    store.replace_day(date(2026, 10, 21), "mal", [rec(1, day=date(2026, 10, 21))])
    store.replace_day(date(2026, 11, 18), "mal", [rec(1, day=date(2026, 11, 18))])
    assert bh.start_day(store) == date(2026, 10, 20)
    # CLI: outside the window -> exit 0 and nothing sent; bad window -> usage error 2
    assert cli.main(["backfill-history", "--window-utc", "12:00-12:01"]) in (0,)
    assert cli.main(["backfill-history", "--window-utc", "bogus"]) == 2
    p = cli.build_parser().parse_args(["backfill-history"])
    assert (p.max_requests, p.min_gap_seconds, p.max_gap_seconds, p.window_utc) == (150, 150.0, 240.0, "22:00-04:30")


# ---------------------------------------------------------------- planned dates, cap, mid-run cache

from ihale import backfill_plan as bp          # noqa: E402


def _plan(*pairs):
    return [bh.PlanEntry(d, t, d) for d, t in pairs]


def test_plan_first_then_walk_when_exhausted(form_html):
    plan = _plan((date(2019, 3, 5), "mal"), (date(2019, 3, 5), "hizmet"))
    code, sess, _, _ = go(form_html, plan=plan, max_requests=6, earliest=date(2026, 10, 19))
    assert code == 0
    # form GET + 2 planned + 3 of the walk's first day: list exhausted -> day-by-day walk from `begin`
    assert sess.posts == [(date(2019, 3, 5), "mal"), (date(2019, 3, 5), "hizmet"),
                          (date(2026, 10, 20), "mal"), (date(2026, 10, 20), "hizmet"), (date(2026, 10, 20), "yapim")][:len(sess.posts)]
    assert len(sess.posts) == 5 and state()["plan_exhausted"] is True and state()["plan_total"] == 2


def test_plan_skips_cached_and_known_empty(form_html):
    ekap.save_zip(config.bulletins_dir(), date(2019, 3, 5), "mal", zip_bytes())
    pipeline._remember_no_bulletin(date(2019, 3, 5), "hizmet")
    plan = _plan((date(2019, 3, 5), "mal"), (date(2019, 3, 5), "hizmet"), (date(2019, 3, 5), "yapim"))
    code, sess, _, c = go(form_html, plan=plan, max_requests=4, earliest=date(2026, 10, 21))
    assert sess.posts == [(date(2019, 3, 5), "yapim")]
    st = state()
    assert st["skipped_cached"] == 1 and st["skipped_empty"] == 1


def test_plan_stops_at_run_budget_and_resumes(form_html):
    plan = _plan(*[(date(2019, 3, 4 + i), "mal") for i in range(1)] + [(date(2020, 3, 4), "mal"), (date(2021, 3, 4), "mal")])
    code, sess, _, _ = go(form_html, plan=plan, max_requests=3)          # form + 2
    assert code == 0 and len(sess.posts) == 2 and "request budget" in state()["stop_reason"]
    code, sess2, _, _ = go(form_html, plan=plan, max_requests=3, earliest=date(2026, 10, 21))   # next night: only the 3rd
    assert sess2.posts == [(date(2021, 3, 4), "mal")]


def test_plan_day_without_any_bulletin_hops_to_next_business_day_at_the_end(form_html):
    mon = date(2019, 3, 4)
    plan = _plan((mon, "mal"), (mon, "hizmet"), (date(2020, 3, 4), "mal"))
    sess = Sess(form_html, empty={mon})
    code, sess, _, _ = go(form_html, sess=sess, plan=plan, max_requests=20, earliest=date(2026, 10, 21))
    assert sess.posts == [(mon, "mal"), (mon, "hizmet"), (date(2020, 3, 4), "mal"),
                          (date(2019, 3, 5), "mal"), (date(2019, 3, 5), "hizmet")]       # the hop comes last


def test_plan_hops_at_most_three_times(form_html):
    mon = date(2019, 3, 4)
    sess = Sess(form_html, empty={date(2019, 3, d) for d in (4, 5, 6, 7, 8)})
    code, sess, _, _ = go(form_html, sess=sess, plan=_plan((mon, "mal")), max_requests=20, earliest=date(2026, 10, 21))
    assert [d for d, _ in sess.posts] == [mon, date(2019, 3, 5), date(2019, 3, 6), date(2019, 3, 7)]


def test_file_cached_by_someone_else_mid_run_is_not_fetched(form_html):
    target = (date(2019, 3, 5), "hizmet")
    fired = []

    def sleeper(sec):                       # while we wait, another process drops the file into the shared cache
        if not fired:
            fired.append(1)
            ekap.save_zip(config.bulletins_dir(), *target, zip_bytes())
    sess = Sess(form_html)
    c = ekap.EkapClient(limiter=NoWait(config.data_dir() / "ekap-last-request.txt"), session=sess, max_requests=500)
    plan = _plan((date(2019, 3, 5), "mal"), target, (date(2019, 3, 5), "yapim"))
    bh.run(c, begin=date(2026, 10, 20), earliest=date(2026, 10, 21), now=lambda: NIGHT, sleep=sleeper, rng=random.Random(1),
           max_requests=20, plan=plan)
    assert (date(2019, 3, 5), "hizmet") not in sess.posts and len(sess.posts) == 2


def test_run_cap_is_per_run_even_when_the_utc_day_counter_resets(form_html, data_dir):
    """The shared counter restarting at 00:00 UTC (36 -> 1) must not add to the run's own cap."""
    clock = {"t": datetime(2026, 11, 22, 23, 55, tzinfo=timezone.utc)}
    budget = ekap.DailyBudget(data_dir, 200, now=lambda: clock["t"])
    for _ in range(36):
        budget.reserve()
    sess = Sess(form_html)
    c = ekap.EkapClient(limiter=NoWait(data_dir / "ekap-last-request.txt"), session=sess, max_requests=500, budget=budget)

    def sleeper(sec):
        clock["t"] += timedelta(seconds=sec + 3600)      # crosses 00:00 UTC after the first gap
    code = bh.run(c, begin=date(2026, 10, 20), earliest=date(2026, 9, 1), now=lambda: NIGHT, sleep=sleeper,
                  rng=random.Random(1), max_requests=10)
    assert code == 0 and c.requests_made == 10 and len(sess.posts) == 9
    assert budget.used() < 36                            # the counter did reset; the run still stopped at its own 10


def test_load_plan_and_errors(tmp_path):
    f = tmp_path / "p.txt"
    f.write_text("# c\n2019-03-05 mal\n\n2020-01-02 yapim  # x\n", encoding="utf-8")
    assert [(e.day, e.type) for e in bh.load_plan(f)] == [(date(2019, 3, 5), "mal"), (date(2020, 1, 2), "yapim")]
    f.write_text("2019-03-05 bogus\n", encoding="utf-8")
    with pytest.raises(ValueError):
        bh.load_plan(f)


def test_generator_is_fixed_by_the_seed():
    t = bp.generate()
    assert bp.SEED == 20261123 and t == bp.generate(20261123) and t != bp.generate(1)
    days = sorted({d for d, _ in t})
    assert len(days) == 105 and len(t) == 315
    assert all(d.weekday() < 5 for d in days)
    ms = [d for d in days if d.year >= 2019]
    assert len(ms) == 93 and len({(d.year, d.month) for d in ms}) == 93 and max(ms) <= date(2026, 9, 30)
    qs = [d for d in days if d.year <= 2018]
    assert len(qs) == 12 and len({(d.year, (d.month - 1) // 3) for d in qs}) == 12
    # all three types per day, mal/hizmet/yapim in this order; newest year first, years interleaved
    assert [x for _, x in t[:3]] == ["mal", "hizmet", "yapim"]
    firsts = [d.year for d, _ in t[::3]]
    assert firsts[:3] == [2026, 2025, 2024] and firsts[:11] == sorted(firsts[:11], reverse=True)
    assert len({d.year for d, _ in t[:33]}) == 11


def test_dry_run_prints_first_ten_without_ekap(form_html, data_dir, capsys, monkeypatch):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "backfill-plan.txt").write_text(bp.render(), encoding="utf-8")

    class Boom:
        def __init__(self, *a, **k):
            raise AssertionError("EKAP client must not be created in a dry run")
    monkeypatch.setattr(ekap, "EkapClient", Boom)
    assert cli.main(["backfill-history", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "315 targets" in out and out.count("\n  20") == 10
