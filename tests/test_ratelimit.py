import pytest

from ihale import ekap


class FakeTime:
    def __init__(self, t=1000.0):
        self.t = t
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def make(tmp_path, ft):
    return ekap.RateLimiter(tmp_path / "last.txt", min_interval=10, clock=ft.clock, sleep=ft.sleep)


def test_first_request_does_not_wait(tmp_path):
    ft = FakeTime()
    make(tmp_path, ft).wait()
    assert ft.sleeps == []


def test_second_request_waits_full_gap(tmp_path):
    ft = FakeTime()
    rl = make(tmp_path, ft)
    rl.wait()
    ft.t += 3
    rl.wait()
    assert sum(ft.sleeps) == pytest.approx(7)


def test_gap_is_across_instances_like_processes(tmp_path):
    ft = FakeTime()
    make(tmp_path, ft).wait()
    other = make(tmp_path, ft)  # a "second process" sharing the state file
    other.wait()
    assert sum(ft.sleeps) == pytest.approx(10)


def test_mark_after_slow_response_counts(tmp_path):
    ft = FakeTime()
    rl = make(tmp_path, ft)
    rl.wait()
    ft.t += 30  # long download
    rl.mark()
    rl.wait()
    assert sum(ft.sleeps) == pytest.approx(10)


def test_no_wait_when_gap_already_elapsed(tmp_path):
    ft = FakeTime()
    rl = make(tmp_path, ft)
    rl.wait()
    ft.t += 11
    rl.wait()
    assert ft.sleeps == []


def test_client_wraps_every_request_and_caps(tmp_path, form_html):
    ft = FakeTime()

    class Resp:
        status_code = 200
        headers = {"Content-Type": "text/html"}
        encoding = "utf-8"
        content = form_html.encode("utf-8")

    class Sess:
        headers = {}
        calls = 0

        def request(self, *a, **k):
            Sess.calls += 1
            return Resp()

    c = ekap.EkapClient(limiter=make(tmp_path, ft), session=Sess(), max_requests=2)
    c._request("GET")
    c._request("GET")
    assert sum(ft.sleeps) == pytest.approx(10)
    with pytest.raises(ekap.RequestBudgetExceeded):
        c._request("GET")
    assert Sess.calls == 2
