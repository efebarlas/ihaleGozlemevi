"""history.db: research-only parse of the backfilled bulletins (fake parser, no pdf, no network)."""
from datetime import date

from ihale import config, history, pipeline
from ihale.store import Store
from rec_helpers import rec

D_OLD, D_WALK, D_MAIN = date(2019, 3, 5), date(2026, 9, 1), date(2026, 11, 18)


def setup(monkeypatch):
    Store().replace_day(D_MAIN, "mal", [rec(1, day=D_MAIN)])               # the daily store (ihale.db)
    monkeypatch.setattr(history, "_cached_days", lambda: [(D_OLD, "mal"), (D_WALK, "mal"), (D_WALK, "hizmet"), (D_MAIN, "mal")])
    calls = []

    def fake_parse(day, type_, store=None):
        calls.append((day, type_))
        recs = [rec(1, day=day, type_=type_, ikn=f"{day.year}/1", toplam=1, gecerli=1, bedel=90.0, maliyet=100.0),
                rec(2, day=day, type_=type_, ikn=f"{day.year}/2", toplam=3, gecerli=1, bedel=50.0, maliyet=100.0)]
        return store.replace_day(day, type_, recs)
    monkeypatch.setattr(pipeline, "parse_and_store", fake_parse)
    return calls


def test_sync_parses_only_backfilled_days_and_is_idempotent(monkeypatch):
    calls = setup(monkeypatch)
    before = Store().all_records()
    assert history.sync() == {"parsed": 3, "failed": 0, "already": 0, "pending": 0}
    assert sorted(calls) == [(D_OLD, "mal"), (D_WALK, "hizmet"), (D_WALK, "mal")]      # never the ihale.db day
    assert history.sync()["parsed"] == 0 and len(calls) == 3                          # nothing parsed twice
    assert [s.record.ikn for s in Store().all_records()] == [s.record.ikn for s in before]   # ihale.db untouched
    assert history.db_path().parent.name == "research" and history.db_path() != config.db_path()


def test_report_splits_sample_and_walk_and_computes_base_rates(monkeypatch, data_dir):
    setup(monkeypatch)
    (data_dir / "backfill-plan.txt").write_text("2019-03-05 mal\n", encoding="utf-8")
    history.sync()
    rows = {(r["year"], r["kind"], r["type"]): r for r in history.report()}
    old = rows[(2019, "sample", "mal")]
    assert old["records"] == 2 and old["tek_teklif_share"] == 0.5 and old["diger_elendi_share"] == 1.0
    assert old["bedel_ym_median"] == round((0.9 + 0.5) / 2, 3)
    assert (2026, "walk", "mal") in rows and (2026, "walk", "hizmet") in rows


def test_time_cap_leaves_the_rest_pending(monkeypatch):
    calls = setup(monkeypatch)
    assert history.sync(max_seconds=-1)["pending"] == 3 and calls == []
    assert history.sync()["parsed"] == 3


def test_writer_lock_second_holder_is_refused_then_released():
    with history.WriterLock() as a:
        assert a is True
        with history.WriterLock() as b:
            assert b is False
    with history.WriterLock() as c:
        assert c is True


def test_cli_second_run_exits_zero_while_locked(monkeypatch, capsys):
    from ihale import cli
    setup(monkeypatch)
    with history.WriterLock() as held:
        assert held
        assert cli.main(["history-parse"]) == 0
    assert "another run is active" in capsys.readouterr().out
    assert Store(history.db_path()).runs() == []          # the refused run wrote nothing
