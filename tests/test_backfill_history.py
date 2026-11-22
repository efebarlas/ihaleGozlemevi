"""backfill-history: fetch-only walk backwards (fake HTTP session, no network, no real sleeping)."""
import io
import json
import random
import zipfile
from datetime import date, datetime, time, timezone

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
