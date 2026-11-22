"""Offline guarantee: any attempt to open a network connection fails the test."""
import socket
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*a, **k):
        raise AssertionError("test tried to use the network (tests must be offline)")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Isolated data root, deliberately with non-ASCII characters in the path."""
    d = tmp_path / "veri-Masaüstü-İhale"
    monkeypatch.setenv("IHALE_DATA_DIR", str(d))
    # tests start from an empty store on purpose; the missing-data guard is tested in test_config.py
    monkeypatch.setenv("IHALE_ALLOW_NEW_DATA_DIR", "1")
    # peer-group tests are written against the legacy rules; production default is table_first (test_classify)
    monkeypatch.setenv("IHALE_PEER_CLASSIFIER", "legacy")
    return d


@pytest.fixture
def form_html():
    return (FIXTURES / "bultenindirme_form.html").read_text(encoding="utf-8")
