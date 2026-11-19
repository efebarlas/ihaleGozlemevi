"""Offline tests for the KİK feasibility guards, using the saved live samples (2026-11-19)."""
from pathlib import Path

import pytest

from ihale import kik
from ihale.ekap import BlockedError

FX = Path(__file__).parent / "fixtures" / "kik"


def test_quota_response_is_a_hard_stop():
    body = (FX / "ekapv2_api_quota_429.json").read_bytes()
    with pytest.raises(BlockedError):
        kik.classify_api_response(429, body)
    with pytest.raises(BlockedError):  # even if some day it came back as 200 with that body
        kik.classify_api_response(200, body)


def test_ordinary_json_passes():
    assert kik.classify_api_response(200, b'{"list": []}') is None


def test_spa_shell_detected():
    assert kik.is_spa_shell((FX / "ekapv2_spa_shell.html").read_text(encoding="utf-8"))
    assert not kik.is_spa_shell("<html><body><form action='x'></form></body></html>")


def test_resmigazete_robots_has_no_blanket_disallow():
    txt = (FX / "resmigazete_robots.txt").read_text(encoding="utf-8", errors="replace").lower()
    assert "disallow: /\n" not in txt and "user-agent: *" not in txt
