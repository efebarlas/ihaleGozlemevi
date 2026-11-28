"""M5-audit-guard: the daily run checks every shown flag number before it exports or deploys.

A real mismatch (a stored flag the rules do not give) stops the run with exit 8, writes AUDIT-FAILED-<date>.txt and
deploys nothing; a clean run deploys as before; the code reaches the scheduler wrapper unchanged.
"""
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import date
from pathlib import Path

import pytest

from ihale import config, pipeline
from ihale.store import Store
from rec_helpers import rec

DAY = date(2026, 11, 18)
REPO = Path(__file__).resolve().parent.parent


def seed():
    Store().replace_day(DAY, "mal", [rec(1, ikn="2026/1", toplam=3, gecerli=3),
                                    rec(2, ikn="2026/2", toplam=1, gecerli=1, yuklenici="B Ltd. Şti.")])


def corrupt():
    """A stored flag the documented rule does not give: tek_teklif on a 3-bid tender."""
    with sqlite3.connect(config.db_path()) as c:
        (i,) = c.execute("SELECT id FROM records WHERE ikn='2026/1'").fetchone()
        c.execute("UPDATE records SET flags=? WHERE id=?",
                  (json.dumps([{"code": "tek_teklif", "value": 1, "text": "Tek teklif verildi"}]), i))


@pytest.fixture
def steps(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "make_client", lambda: object())
    monkeypatch.setattr(pipeline, "load_days", lambda *a, **k: None)
    for name in ("export_step", "drift_step", "build_site", "deploy_site"):
        monkeypatch.setattr(pipeline, name, lambda *a, _n=name, **k: calls.append(_n))
    return calls


def test_clean_run_audits_then_deploys(steps):
    seed()
    assert pipeline.run_daily(DAY, types=()) == pipeline.EXIT_OK
    assert steps == ["export_step", "drift_step", "build_site", "deploy_site"]
    assert not list(config.data_dir().glob("AUDIT-FAILED-*.txt"))


def test_mismatch_blocks_export_and_deploy_and_writes_the_file(steps, monkeypatch):
    seed()
    real_flag_all = pipeline.flag_all

    def flag_then_corrupt(store=None):
        out = real_flag_all(store)
        corrupt()
        return out
    monkeypatch.setattr(pipeline, "flag_all", flag_then_corrupt)
    assert pipeline.run_daily(DAY, types=()) == pipeline.EXIT_AUDIT == 8
    assert steps == []                                          # the site keeps the last good build
    f = config.data_dir() / f"AUDIT-FAILED-{DAY.isoformat()}.txt"
    text = f.read_text(encoding="utf-8")
    assert "1 mismatches" in text and "tek_teklif: 1" in text and "2026/1" in text
    # nothing to clear by hand: once the data is right again, the next run deploys
    monkeypatch.setattr(pipeline, "flag_all", real_flag_all)
    assert pipeline.run_daily(DAY, types=()) == pipeline.EXIT_OK and steps[-1] == "deploy_site"


def test_informational_lists_never_block(steps):
    # a 30x ratio is shown with its note and listed as an outlier, but it is not a mismatch
    Store().replace_day(DAY, "mal", [rec(1, ikn="2026/9", bedel=3000.0, maliyet=100.0)])
    assert pipeline.run_daily(DAY, types=()) == pipeline.EXIT_OK and steps[-1] == "deploy_site"


def test_exit_codes_do_not_collide():
    codes = [pipeline.EXIT_OK, pipeline.EXIT_ERROR, pipeline.EXIT_BLOCKED, pipeline.EXIT_NO_BULLETIN,
             pipeline.EXIT_CAP, pipeline.EXIT_BUDGET, 7, pipeline.EXIT_AUDIT]     # 7 = wrapper: data dir missing
    assert len(set(codes)) == len(codes) and pipeline.EXIT_AUDIT == 8


@pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell.exe")
                    or not (REPO / ".venv" / "Scripts" / "python.exe").exists(),
                    reason="needs Windows PowerShell and the repo venv (the scheduler's environment)")
def test_exit_8_reaches_the_scheduler_wrapper():
    seed()
    pipeline.flag_all()
    corrupt()
    env = dict(os.environ, IHALE_DATA_DIR=str(config.data_dir()))
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(REPO / "scripts" / "run_daily.ps1"), "audit"], env=env, timeout=300)
    assert p.returncode == 8
    logs = list((config.data_dir() / "logs").glob("scheduler-*.log"))
    assert logs and "finished with exit code 8" in logs[0].read_text(encoding="utf-8")
