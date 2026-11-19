"""SQLite store (docs/data-contract.md §2). Money is integer kuruş + currency; confidence/warnings are JSON."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from . import config
from .model import Money, Record

SCHEMA_VERSION = 4

MONEY_FIELDS = ("yaklasik_maliyet", "esas_kisim_yaklasik_maliyet", "sozlesme_bedeli")
DATE_FIELDS = ("ihale_tarihi", "sozlesme_tarihi")
TEXT_FIELDS = ("ikn", "title", "idare", "ihale_turu", "ihale_usulu", "konu", "sozlesme_suresi",
               "yuklenici", "yuklenici_uyrugu", "yuklenici_adresi")
INT_FIELDS = ("toplam_teklif", "gecerli_teklif")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bulletin_date TEXT NOT NULL,
    bulletin_type TEXT NOT NULL,
    section TEXT NOT NULL,
    seq INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    ikn TEXT, title TEXT, idare TEXT, ihale_tarihi TEXT, ihale_turu TEXT, ihale_usulu TEXT,
    yaklasik_maliyet_kurus INTEGER, yaklasik_maliyet_cur TEXT,
    yaklasik_maliyet_alt_kurus INTEGER, yaklasik_maliyet_alt_cur TEXT,
    esas_kisim_yaklasik_maliyet_kurus INTEGER, esas_kisim_yaklasik_maliyet_cur TEXT,
    esas_kisim_yaklasik_maliyet_alt_kurus INTEGER, esas_kisim_yaklasik_maliyet_alt_cur TEXT,
    konu TEXT, toplam_teklif INTEGER, gecerli_teklif INTEGER,
    sozlesme_tarihi TEXT,
    sozlesme_bedeli_kurus INTEGER, sozlesme_bedeli_cur TEXT,
    sozlesme_bedeli_alt_kurus INTEGER, sozlesme_bedeli_alt_cur TEXT,
    sozlesme_suresi TEXT, yuklenici TEXT, yuklenici_uyrugu TEXT, yuklenici_adresi TEXT,
    confidence TEXT NOT NULL DEFAULT '{}',
    warnings TEXT NOT NULL DEFAULT '[]',
    raw_fields TEXT NOT NULL DEFAULT '[]',
    flags TEXT, unreadable TEXT, kisim_n INTEGER,
    score INTEGER, score_parts TEXT, idare_stats TEXT, indicators TEXT, structural TEXT,
    UNIQUE (bulletin_date, bulletin_type, section, seq)
);
CREATE INDEX IF NOT EXISTS records_ikn ON records (ikn);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    bulletin_date TEXT NOT NULL,
    bulletin_type TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL,
    parse_accuracy REAL
);
"""


@dataclass
class StoredRecord:
    id: int
    record: Record
    flags: list[dict] | None = None
    unreadable: list | None = None
    kisim_n: int | None = None
    score: int | None = None
    score_parts: list | None = None
    idare_stats: dict | None = None
    indicators: dict | None = None
    structural: dict | None = None


def _money_cols(name: str, m: Money | None) -> dict:
    alt = m.alt if m else None
    return {
        f"{name}_kurus": m.kurus if m else None,
        f"{name}_cur": m.currency if m else None,
        f"{name}_alt_kurus": alt.kurus if alt else None,
        f"{name}_alt_cur": alt.currency if alt else None,
    }


def _money_from(row: sqlite3.Row, name: str) -> Money | None:
    k = row[f"{name}_kurus"]
    if k is None:
        return None
    alt = None
    if row[f"{name}_alt_kurus"] is not None:
        alt = Money(row[f"{name}_alt_kurus"], row[f"{name}_alt_cur"])
    return Money(k, row[f"{name}_cur"], alt)


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def record_to_row(r: Record) -> dict:
    row = {
        "bulletin_date": r.bulletin_date.isoformat(), "bulletin_type": r.bulletin_type,
        "section": r.section, "seq": r.seq, "source_file": r.source_file,
        "page_start": r.page_start, "page_end": r.page_end,
        "confidence": json.dumps(r.confidence, ensure_ascii=False, sort_keys=True),
        "warnings": json.dumps(r.warnings, ensure_ascii=False),
        "raw_fields": json.dumps(r.raw_fields, ensure_ascii=False),
    }
    for f in TEXT_FIELDS + INT_FIELDS:
        row[f] = getattr(r, f)
    for f in DATE_FIELDS:
        v = getattr(r, f)
        row[f] = v.isoformat() if v else None
    for f in MONEY_FIELDS:
        row.update(_money_cols(f, getattr(r, f)))
    return row


def row_to_record(row: sqlite3.Row) -> Record:
    kw = {f: row[f] for f in TEXT_FIELDS + INT_FIELDS}
    for f in DATE_FIELDS:
        kw[f] = _d(row[f])
    for f in MONEY_FIELDS:
        kw[f] = _money_from(row, f)
    return Record(
        bulletin_date=date.fromisoformat(row["bulletin_date"]), bulletin_type=row["bulletin_type"],
        source_file=row["source_file"], section=row["section"], seq=row["seq"],
        page_start=row["page_start"], page_end=row["page_end"],
        confidence=json.loads(row["confidence"]), warnings=json.loads(row["warnings"]),
        raw_fields=[tuple(t) for t in json.loads(row["raw_fields"])], **kw)


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config.db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _conn(self):
        """One short-lived connection per operation, always closed (OneDrive/Windows file handles)."""
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            with conn:  # commit / rollback
                yield conn

    def _init(self):
        with self._conn() as c:
            c.executescript(_SCHEMA)
            row = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is None:
                c.execute("INSERT INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            elif int(row["value"]) < SCHEMA_VERSION:   # v1/v2 → v3: add whichever columns are missing
                have = {r["name"] for r in c.execute("PRAGMA table_info(records)")}
                for col, decl in (("raw_fields", "TEXT NOT NULL DEFAULT '[]'"), ("score", "INTEGER"),
                                  ("score_parts", "TEXT"), ("idare_stats", "TEXT"), ("indicators", "TEXT"),
                                  ("structural", "TEXT")):
                    if col not in have:
                        c.execute(f"ALTER TABLE records ADD COLUMN {col} {decl}")
                c.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(SCHEMA_VERSION),))
            elif int(row["value"]) != SCHEMA_VERSION:
                raise RuntimeError(f"database schema {row['value']} != supported {SCHEMA_VERSION}; migrate or rebuild")

    def schema_version(self) -> int:
        with self._conn() as c:
            return int(c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()["value"])

    # ------------------------------------------------------------ write
    def replace_day(self, day: date, bulletin_type: str, records: list[Record],
                    parse_accuracy: float | None = None, now: datetime | None = None) -> int:
        """Replace all stored records of (day, type) with `records`, atomically. Idempotent.

        Flags of the replaced rows are dropped; re-run flagging afterwards.
        """
        for r in records:
            if r.bulletin_date != day or r.bulletin_type != bulletin_type:
                raise ValueError(f"record {r.section}-{r.seq} is for {r.bulletin_date}/{r.bulletin_type}, "
                                 f"not {day}/{bulletin_type}")
        with self._conn() as c:
            c.execute("DELETE FROM records WHERE bulletin_date=? AND bulletin_type=?",
                      (day.isoformat(), bulletin_type))
            for r in records:
                row = record_to_row(r)
                cols = ", ".join(row)
                marks = ", ".join(":" + k for k in row)
                # OR REPLACE: a duplicated (section, seq) inside one parse keeps the last one.
                c.execute(f"INSERT OR REPLACE INTO records ({cols}) VALUES ({marks})", row)
            stored = c.execute("SELECT COUNT(*) FROM records WHERE bulletin_date=? AND bulletin_type=?",
                               (day.isoformat(), bulletin_type)).fetchone()[0]
            c.execute("INSERT INTO runs (run_at, bulletin_date, bulletin_type, record_count, warning_count,"
                      " parse_accuracy) VALUES (?,?,?,?,?,?)",
                      ((now or datetime.now()).isoformat(timespec="seconds"), day.isoformat(), bulletin_type,
                       stored, sum(len(r.warnings) for r in records), parse_accuracy))
        return stored

    def set_flags(self, results: dict[int, dict]) -> None:
        """results: record id → {flags, unreadable, kisim_n, score, score_parts, idare_stats, indicators}."""
        dump = lambda v: json.dumps(v, ensure_ascii=False)  # noqa: E731
        with self._conn() as c:
            c.executemany(
                "UPDATE records SET flags=?, unreadable=?, kisim_n=?, score=?, score_parts=?, idare_stats=?, indicators=?, structural=? WHERE id=?",
                [(dump(r["flags"]), dump(r["unreadable"]), r["kisim_n"], r["score"], dump(r["score_parts"]),
                  dump(r["idare_stats"]), dump(r["indicators"]), dump(r["structural"]), i) for i, r in results.items()])

    # ------------------------------------------------------------ read
    def all_records(self) -> list[StoredRecord]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM records ORDER BY bulletin_date, bulletin_type, section, seq").fetchall()
        out = []
        for row in rows:
            out.append(StoredRecord(
                id=row["id"], record=row_to_record(row),
                flags=json.loads(row["flags"]) if row["flags"] is not None else None,
                unreadable=json.loads(row["unreadable"]) if row["unreadable"] is not None else None,
                kisim_n=row["kisim_n"], score=row["score"],
                score_parts=json.loads(row["score_parts"]) if row["score_parts"] is not None else None,
                idare_stats=json.loads(row["idare_stats"]) if row["idare_stats"] is not None else None,
                indicators=json.loads(row["indicators"]) if row["indicators"] is not None else None,
                structural=json.loads(row["structural"]) if row["structural"] is not None else None))
        return out

    def dates(self) -> list[date]:
        with self._conn() as c:
            return [date.fromisoformat(r[0]) for r in
                    c.execute("SELECT DISTINCT bulletin_date FROM records ORDER BY bulletin_date")]

    def has_day(self, day: date, bulletin_type: str) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM records WHERE bulletin_date=? AND bulletin_type=? LIMIT 1",
                             (day.isoformat(), bulletin_type)).fetchone() is not None

    def runs(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM runs ORDER BY id")]
