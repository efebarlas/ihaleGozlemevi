import sqlite3
from datetime import date

from ihale import config
from ihale.store import SCHEMA_VERSION, Store

from rec_helpers import rec

D = date(2026, 11, 18)

V1_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO meta VALUES ('schema_version', '1');
CREATE TABLE records (id INTEGER PRIMARY KEY AUTOINCREMENT, bulletin_date TEXT NOT NULL, bulletin_type TEXT NOT NULL,
  section TEXT NOT NULL, seq INTEGER NOT NULL, source_file TEXT NOT NULL, page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL, ikn TEXT, title TEXT, idare TEXT, ihale_tarihi TEXT, ihale_turu TEXT, ihale_usulu TEXT,
  yaklasik_maliyet_kurus INTEGER, yaklasik_maliyet_cur TEXT, yaklasik_maliyet_alt_kurus INTEGER,
  yaklasik_maliyet_alt_cur TEXT, esas_kisim_yaklasik_maliyet_kurus INTEGER, esas_kisim_yaklasik_maliyet_cur TEXT,
  esas_kisim_yaklasik_maliyet_alt_kurus INTEGER, esas_kisim_yaklasik_maliyet_alt_cur TEXT, konu TEXT,
  toplam_teklif INTEGER, gecerli_teklif INTEGER, sozlesme_tarihi TEXT, sozlesme_bedeli_kurus INTEGER,
  sozlesme_bedeli_cur TEXT, sozlesme_bedeli_alt_kurus INTEGER, sozlesme_bedeli_alt_cur TEXT, sozlesme_suresi TEXT,
  yuklenici TEXT, yuklenici_uyrugu TEXT, yuklenici_adresi TEXT, confidence TEXT NOT NULL DEFAULT '{}',
  warnings TEXT NOT NULL DEFAULT '[]', flags TEXT, unreadable TEXT, kisim_n INTEGER,
  UNIQUE (bulletin_date, bulletin_type, section, seq));
CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT NOT NULL, bulletin_date TEXT NOT NULL,
  bulletin_type TEXT NOT NULL, record_count INTEGER NOT NULL, warning_count INTEGER NOT NULL, parse_accuracy REAL);
"""


def test_raw_fields_roundtrip():
    r = rec(1)
    r.raw_fields = [("0", "İhale kayıt numarası", "2026/1"), ("4", "Yüklenicisi", "Şişli Ltd.")]
    Store().replace_day(D, "mal", [r])
    got = Store().all_records()[0].record
    assert got.raw_fields == r.raw_fields and all(isinstance(t, tuple) for t in got.raw_fields)


def test_v1_database_is_migrated():
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(V1_SCHEMA)
    con.close()
    s = Store()
    assert s.schema_version() == SCHEMA_VERSION
    r = rec(1)
    r.raw_fields = [("1", "a", "b")]
    s.replace_day(D, "mal", [r])
    assert s.all_records()[0].record.raw_fields == [("1", "a", "b")]
