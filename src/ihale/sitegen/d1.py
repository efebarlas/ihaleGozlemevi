"""Bulk pages in Cloudflare D1 (M4 infra).

The build keeps core pages as static assets and stages the bulk pages (`/ihale/<id>/`, `/idare/<slug>/...`,
`/yuklenici/<slug>/...`, `/gun/<date>/<n>/`) in a local SQLite file with a sha per page. `sync_pages` diffs that
against the last deployed manifest and writes only the changes to D1 as SQL batch files.

The path classifier here is mirrored exactly by site/worker/index.js; keep both in sync.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

CHUNK_CHARS = 16_000          # <= 4 bytes/char, quote doubling only on ' -> every statement stays well under 90 KB
MAX_STATEMENT_BYTES = 90_000
BATCH_BYTES = 3_000_000       # one `wrangler d1 execute --file` per batch
D1_MAX_ROWS_PER_RUN = 90_000  # D1 free tier: 100k rows written per day

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS pages(path TEXT NOT NULL, part INTEGER NOT NULL, html TEXT NOT NULL, "
    "PRIMARY KEY(path, part)) WITHOUT ROWID;\n"
    "CREATE TABLE IF NOT EXISTS page_meta(path TEXT PRIMARY KEY, sha TEXT NOT NULL, parts INTEGER NOT NULL, "
    "updated TEXT NOT NULL) WITHOUT ROWID;\n"
)

# ---- classifier (URL path with trailing slash). `liste` is reserved: /idare/liste/<n>/ is a static index page.
_BULK = (
    re.compile(r"^/ihale/[^/]+/$"),
    re.compile(r"^/idare/(?!liste/)[^/]+/(?:\d+/)?$"),
    re.compile(r"^/yuklenici/(?!liste/)[^/]+/(?:\d+/)?$"),
    re.compile(r"^/gun/[^/]+/\d+/$"),
)


def url_path(rel: str) -> str | None:
    """'ihale/x/index.html' -> '/ihale/x/'; None for non-page files."""
    rel = rel.replace("\\", "/")
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return None


def is_bulk(path: str) -> bool:
    return any(r.match(path) for r in _BULK)


def staging_path(out_dir: Path) -> Path:
    return out_dir.with_name(out_dir.name + "-pages.sqlite")


def sha_of(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


class Stage:
    """Local SQLite staging store for bulk pages (path, sha, html)."""

    def __init__(self, path: Path):
        self.path = path
        for suffix in ("", "-journal", "-wal", "-shm"):
            p = Path(str(path) + suffix)
            if p.exists():
                p.unlink()
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE staged(path TEXT PRIMARY KEY, sha TEXT NOT NULL, html TEXT NOT NULL)")

    def add(self, path: str, html: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO staged VALUES (?,?,?)", (path, sha_of(html), html))

    def close(self) -> None:
        self.db.commit()
        self.db.close()


def read_stage(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path)


def staged_paths(path: Path) -> list[tuple[str, str]]:
    db = sqlite3.connect(path)
    try:
        return db.execute("SELECT path, sha FROM staged ORDER BY path").fetchall()
    finally:
        db.close()


def staged_html(path: Path, url: str) -> str | None:
    db = sqlite3.connect(path)
    try:
        r = db.execute("SELECT html FROM staged WHERE path=?", (url,)).fetchone()
        return r[0] if r else None
    finally:
        db.close()


# ---- SQL generation
def sql_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def chunks(html: str, size: int | None = None) -> list[str]:
    size = size or CHUNK_CHARS
    return [html[i:i + size] for i in range(0, len(html), size)] or [""]


def page_statements(path: str, html: str, sha: str, updated: str) -> list[str]:
    """Replace a page: delete all its parts, insert the new parts, upsert its meta row."""
    parts = chunks(html)
    out = [f"DELETE FROM pages WHERE path={sql_quote(path)};"]
    for i, c in enumerate(parts):
        out.append(f"INSERT INTO pages(path,part,html) VALUES({sql_quote(path)},{i},{sql_quote(c)});")
    out.append(f"INSERT OR REPLACE INTO page_meta(path,sha,parts,updated) VALUES({sql_quote(path)},{sql_quote(sha)},"
               f"{len(parts)},{sql_quote(updated)});")
    for s in out:
        if len(s.encode("utf-8")) > MAX_STATEMENT_BYTES:
            raise ValueError(f"SQL statement over {MAX_STATEMENT_BYTES} bytes for {path}")
    return out


def delete_statements(path: str) -> list[str]:
    return [f"DELETE FROM pages WHERE path={sql_quote(path)};", f"DELETE FROM page_meta WHERE path={sql_quote(path)};"]


def batch_files(statement_groups: list[list[str]], limit: int | None = None) -> list[list[list[str]]]:
    """Group statement groups (one group per page, kept together) into batches of at most `limit` bytes."""
    limit = limit or BATCH_BYTES
    batches: list[list[list[str]]] = []
    cur: list[list[str]] = []
    size = 0
    for g in statement_groups:
        n = sum(len(s.encode("utf-8")) + 1 for s in g)
        if cur and size + n > limit:
            batches.append(cur)
            cur, size = [], 0
        cur.append(g)
        size += n
    if cur:
        batches.append(cur)
    return batches


# ---- manifest + plan
def load_manifest(path: Path) -> dict[str, list]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_manifest(path: Path, manifest: dict[str, list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


@dataclass
class Plan:
    upserts: list[tuple[str, str, int]] = field(default_factory=list)   # path, sha, new parts
    deletes: list[str] = field(default_factory=list)
    rows: int = 0
    unchanged: int = 0
    total_bytes: int = 0


def make_plan(stage_db: Path, manifest: dict[str, list]) -> Plan:
    plan = Plan()
    db = sqlite3.connect(stage_db)
    try:
        seen = set()
        for path, sha, nbytes, nchars in db.execute("SELECT path, sha, length(CAST(html AS BLOB)), length(html) FROM staged ORDER BY path"):
            seen.add(path)
            plan.total_bytes += nbytes
            old = manifest.get(path)
            if old and old[0] == sha:
                plan.unchanged += 1
                continue
            parts = max(1, -(-nchars // CHUNK_CHARS))
            plan.upserts.append((path, sha, parts))
            # rows written: old parts deleted + new parts + meta (delete/replace counted once)
            plan.rows += (old[1] if old else 0) + parts + 1
        for path, old in manifest.items():
            if path not in seen:
                plan.deletes.append(path)
                plan.rows += old[1] + 1
    finally:
        db.close()
    return plan


def sync_pages(*, stage_db: Path, manifest_path: Path, batch_dir: Path, execute: Callable[[Path], None],
               between: Callable[[], None] | None = None, updated: str, max_rows: int = D1_MAX_ROWS_PER_RUN,
               log: Callable[[str], None] = print) -> Plan:
    """Push changed pages to D1, run `between` (the Worker deploy), then push deletions; update the manifest
    after each successful batch. Idempotent: a re-run after a failure repeats only what is not in the manifest."""
    manifest = load_manifest(manifest_path)
    plan = make_plan(stage_db, manifest)
    log(f"D1 plan: {len(plan.upserts)} changed/new pages, {len(plan.deletes)} deletions, {plan.unchanged} unchanged; "
        f"{plan.rows} rows to write, {plan.total_bytes / 1e6:.1f} MB of bulk HTML stored in total")
    if plan.rows > max_rows:
        raise RuntimeError(f"refusing: {plan.rows} D1 rows to write in one run exceeds the limit of {max_rows} "
                           f"(free tier: 100,000 rows/day). Nothing was written.")
    batch_dir.mkdir(parents=True, exist_ok=True)
    for old in batch_dir.glob("batch-*.sql"):
        old.unlink()

    db = sqlite3.connect(stage_db)
    try:
        groups, meta_for = [], []
        for path, sha, parts in plan.upserts:
            html = db.execute("SELECT html FROM staged WHERE path=?", (path,)).fetchone()[0]
            groups.append(page_statements(path, html, sha, updated))
            meta_for.append((path, sha, parts))
    finally:
        db.close()

    n = 0
    idx = 0
    for batch in batch_files(groups) if groups else [[]]:
        text = SCHEMA + "".join(s + "\n" for g in batch for s in g)
        f = batch_dir / f"batch-{n:04d}.sql"
        f.write_text(text, encoding="utf-8", newline="\n")
        execute(f)
        for _ in batch:
            path, sha, parts = meta_for[idx]
            manifest[path] = [sha, parts]
            idx += 1
        save_manifest(manifest_path, manifest)
        n += 1

    if between:
        between()

    if plan.deletes:
        for k in range(0, len(plan.deletes), 500):
            part = plan.deletes[k:k + 500]
            f = batch_dir / f"batch-{n:04d}.sql"
            f.write_text("".join(s + "\n" for p in part for s in delete_statements(p)), encoding="utf-8", newline="\n")
            execute(f)
            for p in part:
                manifest.pop(p, None)
            save_manifest(manifest_path, manifest)
            n += 1
    return plan
