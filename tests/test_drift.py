"""M5d: weekly drift summary (log only)."""
import json
from datetime import date, timedelta

from rec_helpers import rec

from ihale import drift
from ihale.store import StoredRecord

LAST = date(2026, 11, 20)


def mk(i, day, usul, idare="DENEME BELEDİYE BAŞKANLIĞI"):
    r = rec(i, day=day, ikn=f"2026/{i}", idare=idare, yuklenici=f"F{i} Limited Şirketi")
    r.ihale_usulu = usul
    return StoredRecord(id=i, record=r, score_parts=[])


def history(n_prior, n_recent, prior_usul, recent_usul, **kw):
    out, i = [], 0
    for k in range(n_prior):
        i += 1
        out.append(mk(i, LAST - timedelta(days=8 + (k % 20)), prior_usul if k % 5 else "Açık", **kw))
    for k in range(n_recent):
        i += 1
        out.append(mk(i, LAST - timedelta(days=k % 6), recent_usul, **kw))
    return out


def test_shift_in_procedure_mix_is_listed_with_both_sides():
    res = drift.compute(history(20, 8, "Açık", "Pazarlık (MD 21 B)"), LAST)
    (row,) = res["shifts"]
    kinds = {c["what"] for c in row["changes"]}
    assert "pazarlık 21/b payı" in kinds and "açık dışı usul payı" in kinds
    assert row["recent_n"] == 8 and row["prior_n"] == 20
    assert "look here" in res["note"]


def test_no_shift_and_small_samples_are_silent():
    assert drift.compute(history(20, 8, "Açık", "Açık"), LAST)["shifts"] == []
    assert drift.compute(history(20, 3, "Açık", "Pazarlık (MD 21 B)"), LAST)["shifts"] == []      # < 5 recent
    assert drift.compute(history(6, 8, "Açık", "Pazarlık (MD 21 B)"), LAST)["shifts"] == []       # < 10 prior


def test_volume_jump_is_listed():
    res = drift.compute(history(20, 20, "Açık", "Açık"), LAST)
    assert any(c["what"] == "haftalık hacim" for c in res["shifts"][0]["changes"])


def test_weekly_file_written_once(tmp_path, monkeypatch):
    monkeypatch.setattr(drift.config, "data_dir", lambda: tmp_path)
    stored = history(20, 8, "Açık", "Pazarlık (MD 21 B)")
    p = drift.write_weekly(stored, LAST)
    assert p.name == "drift-2026-W47.json" and p.with_suffix(".txt").is_file()
    assert "D1" in p.with_suffix(".txt").read_text(encoding="utf-8")
    assert drift.write_weekly(stored, LAST) is None                       # same ISO week: not rewritten
    assert drift.write_weekly(stored, LAST, force=True) == p
