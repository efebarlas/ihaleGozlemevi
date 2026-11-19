import sqlite3
from datetime import date

import pytest

from ihale import config
from ihale.model import Money
from ihale.store import SCHEMA_VERSION, Store

from rec_helpers import money, rec

D = date(2026, 11, 18)


def test_db_created_at_config_path_with_schema_version(data_dir):
    s = Store()
    assert config.db_path().exists() and s.schema_version() == SCHEMA_VERSION


def test_roundtrip_money_json_and_dates():
    r = rec(1, maliyet=47407500.0, bedel=154050.0, conf={"sozlesme_bedeli": 0.5}, warnings=["w1 İ"])
    r.yaklasik_maliyet = Money(4740750000, "TRY", Money(107247500, "EUR"))
    r.sozlesme_bedeli = Money(15405000, "EUR")
    Store().replace_day(D, "mal", [r])
    (got,) = Store().all_records()
    g = got.record
    assert g == r
    assert g.yaklasik_maliyet.alt == Money(107247500, "EUR")
    assert g.confidence["sozlesme_bedeli"] == 0.5 and g.warnings == ["w1 İ"]
    with sqlite3.connect(config.db_path()) as c:
        k, cur = c.execute("SELECT sozlesme_bedeli_kurus, sozlesme_bedeli_cur FROM records").fetchone()
    assert (k, cur) == (15405000, "EUR")   # integer kuruş, not a float


def test_none_fields_roundtrip():
    r = rec(1, maliyet=None, bedel=None, gecerli=None, toplam=None)
    r.sozlesme_tarihi = None
    Store().replace_day(D, "mal", [r])
    assert Store().all_records()[0].record == r


def test_replace_day_is_idempotent_and_replaces():
    s = Store()
    s.replace_day(D, "mal", [rec(1), rec(2)])
    s.replace_day(D, "mal", [rec(1), rec(2)])
    assert len(s.all_records()) == 2
    s.replace_day(D, "mal", [rec(1, bedel=5.0)])        # re-parse found fewer records
    got = s.all_records()
    assert len(got) == 1 and got[0].record.sozlesme_bedeli == money(5.0)


def test_other_days_and_types_untouched():
    s = Store()
    s.replace_day(D, "mal", [rec(1)])
    s.replace_day(date(2026, 11, 17), "mal", [rec(1, day=date(2026, 11, 17))])
    s.replace_day(D, "hizmet", [rec(1, type_="hizmet")])
    s.replace_day(D, "mal", [])
    assert [(x.record.bulletin_date, x.record.bulletin_type) for x in s.all_records()] == [
        (date(2026, 11, 17), "mal"), (D, "hizmet")]


def test_same_seq_in_different_sections_are_distinct():
    s = Store()
    s.replace_day(D, "mal", [rec(1, section="A"), rec(1, section="B")])
    assert len(s.all_records()) == 2


def test_wrong_day_rejected():
    with pytest.raises(ValueError):
        Store().replace_day(D, "mal", [rec(1, day=date(2026, 1, 1))])


def test_runs_table():
    s = Store()
    s.replace_day(D, "mal", [rec(1, warnings=["a", "b"]), rec(2)], parse_accuracy=0.97)
    (run,) = s.runs()
    assert (run["bulletin_date"], run["bulletin_type"], run["record_count"], run["warning_count"],
            run["parse_accuracy"]) == ("2026-11-18", "mal", 2, 2, 0.97)


def test_set_flags_persist():
    s = Store()
    s.replace_day(D, "mal", [rec(1)])
    sid = s.all_records()[0].id
    s.set_flags({sid: {"flags": [{"code": "x", "value": 1, "text": "Şş"}], "unreadable": ["ikn"], "kisim_n": 3,
                       "score": 2, "score_parts": ["a"], "idare_stats": {"records": 7},
                       "indicators": {"usul_turu": "acik"}, "structural": {"id": "x", "text": "t"}, "score_raw": 2.5, "value_weight": 1.2}})
    got = s.all_records()[0]
    assert got.flags == [{"code": "x", "value": 1, "text": "Şş"}] and got.unreadable == ["ikn"] and got.kisim_n == 3
    assert (got.score, got.score_parts, got.idare_stats) == (2, ["a"], {"records": 7})
    assert got.indicators == {"usul_turu": "acik"} and got.structural == {"id": "x", "text": "t"}
    assert (got.score_raw, got.value_weight) == (2.5, 1.2)


def test_reopen_keeps_data():
    Store().replace_day(D, "mal", [rec(1)])
    assert len(Store().all_records()) == 1
