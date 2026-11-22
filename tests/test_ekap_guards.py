"""Hard-stop guards inside EkapClient: BLOCKED marker before every request, shared daily budget (offline, mocked transport)."""
from datetime import datetime, timezone

import pytest

from ihale import config, ekap, pipeline


class Sess:
    def __init__(self):
        self.headers = {}
        self.calls = 0

    def request(self, method, url, data=None, timeout=None, **_):
        self.calls += 1
        return ekap._Response(200, {"Content-Type": "text/html"}, b"<html></html>")


class NoWait(ekap.RateLimiter):
    def wait(self):  # the gap is tested in test_ratelimit.py
        pass


def client(sess=None, **kw):
    limiter = NoWait(config.data_dir() / "ekap-last-request.txt")
    return ekap.EkapClient(limiter=limiter, session=sess or Sess(), **kw)


def test_marker_present_sends_nothing():
    pipeline.write_blocked_marker("test")
    sess = Sess()
    c = client(sess)
    with pytest.raises(ekap.BlockedError):
        c._request("GET")
    with pytest.raises(ekap.BlockedError):
        c.load_form()
    assert sess.calls == 0 and c.requests_made == 0
    assert c.budget.used() == 0          # a refused request costs no budget


def test_marker_checked_before_every_request_not_just_the_first():
    sess = Sess()
    c = client(sess)
    c._request("GET")
    assert sess.calls == 1
    pipeline.write_blocked_marker("appeared mid-run")
    with pytest.raises(ekap.BlockedError):
        c._request("GET")
    assert sess.calls == 1


def test_daily_budget_boundary_200_allowed_201st_refused():
    sess = Sess()
    c = client(sess, max_requests=1000)
    for _ in range(200):
        c._request("GET")
    assert sess.calls == 200
    with pytest.raises(ekap.RequestBudgetExceeded):
        c._request("GET")
    assert sess.calls == 200 and c.budget.used() == 200


def test_two_clients_share_the_daily_budget():
    s1, s2 = Sess(), Sess()
    a, b = client(s1, max_requests=1000), client(s2, max_requests=1000)
    for _ in range(150):
        a._request("GET")
    for _ in range(50):
        b._request("GET")
    with pytest.raises(ekap.RequestBudgetExceeded):
        a._request("GET")
    with pytest.raises(ekap.RequestBudgetExceeded):
        b._request("GET")
    assert s1.calls + s2.calls == 200
    # a fresh client in a "new process" does not reset the day
    with pytest.raises(ekap.RequestBudgetExceeded):
        client(Sess(), max_requests=1000)._request("GET")


def test_per_run_cap_still_applies_and_costs_no_daily_budget():
    c = client(max_requests=2)
    c._request("GET"); c._request("GET")
    with pytest.raises(ekap.RequestBudgetExceeded):
        c._request("GET")
    assert c.budget.used() == 2


def test_budget_resets_on_next_utc_day_and_limit_is_constructor_only(monkeypatch):
    now = [datetime(2026, 11, 21, 23, 59, tzinfo=timezone.utc)]
    d = ekap.DailyBudget(config.data_dir(), 2, now=lambda: now[0])
    d.reserve(); d.reserve()
    with pytest.raises(ekap.RequestBudgetExceeded):
        d.reserve()
    now[0] = datetime(2026, 11, 22, 0, 1, tzinfo=timezone.utc)
    assert d.reserve() == 1
    monkeypatch.setenv("IHALE_DAILY_LIMIT", "1000")      # no env var can raise it
    assert client().budget.limit == 200
    assert client(daily_limit=5).budget.limit == 5


# ---------------------------------------------------------------- block evidence (logs/blocked-responses)
import json as _json
from datetime import date


class BlockSess:
    def __init__(self, status=200, body=b"<html>Giri\xc5\x9f Yap</html>", ctype="text/html; charset=utf-8"):
        self.headers = {}
        self.resp = (status, body, ctype)

    def request(self, method, url, data=None, timeout=None, **_):
        return ekap._Response(self.resp[0], {"Content-Type": self.resp[2]}, self.resp[1])


def test_blocked_response_is_saved_with_sidecar_and_still_raises(data_dir):
    c = client(BlockSess())
    with pytest.raises(ekap.BlockedError):
        c.load_form()
    out = data_dir / "logs" / "blocked-responses"
    bodies = list(out.glob("*.html"))
    sidecars = list(out.glob("*.json"))
    assert len(bodies) == 1 and len(sidecars) == 1
    assert bodies[0].read_bytes() == "<html>Giriş Yap</html>".encode("utf-8")
    meta = _json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert meta["status"] == 200 and meta["type"] is None and meta["body_file"] == bodies[0].name
    assert "login wall" in meta["reason"]


def test_http_403_saved_as_bin_when_not_text(data_dir):
    c = client(BlockSess(403, b"\x00\x01nope", "application/octet-stream"))
    with pytest.raises(ekap.BlockedError):
        c._classify(c._request("GET"), "mal", date(2026, 10, 20))
    f = list((data_dir / "logs" / "blocked-responses").glob("*-mal-2026-10-20.bin"))
    assert len(f) == 1


def test_evidence_failure_never_masks_the_stop(data_dir, monkeypatch):
    def boom(self, *a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(ekap.Path, "mkdir", boom)
    c = client(BlockSess(429, b"x"))
    with pytest.raises(ekap.BlockedError):
        c._classify(ekap._Response(429, {}, b"x"))
    assert ekap.save_blocked_response(data_dir, status=1, content_type="", body=b"", url="", type_=None, day=None,
                                      reason="r") is None
