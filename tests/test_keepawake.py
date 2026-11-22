import sys
import pytest
from ihale import keepawake


def test_sets_then_clears(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(keepawake, "_set", lambda f: calls.append(f) or 1)
    with keepawake.keep_awake() as held:
        assert held is True
    assert calls == [keepawake.ES_CONTINUOUS | keepawake.ES_SYSTEM_REQUIRED, keepawake.ES_CONTINUOUS]


def test_cleared_on_error(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(keepawake, "_set", lambda f: calls.append(f) or 1)
    with pytest.raises(RuntimeError):
        with keepawake.keep_awake():
            raise RuntimeError("x")
    assert calls[-1] == keepawake.ES_CONTINUOUS


def test_failure_never_breaks_job(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    def boom(f): raise OSError("no")
    monkeypatch.setattr(keepawake, "_set", boom)
    with keepawake.keep_awake() as held:
        assert held is False


def test_noop_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(keepawake, "_set", lambda f: pytest.fail("called"))
    with keepawake.keep_awake() as held:
        assert held is False
