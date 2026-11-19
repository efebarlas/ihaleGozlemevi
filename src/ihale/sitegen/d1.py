"""Bulk pages in Cloudflare D1 (M4 infra).

The build keeps core pages as static assets and stages the bulk pages (`/ihale/<id>/`, `/idare/<slug>/...`,
`/yuklenici/<slug>/...`, `/gun/<date>/<n>/`) in a local SQLite file with a sha per page. `sync_pages` diffs that
against the last deployed manifest and writes only the changes to D1 as SQL batch files; each page is stored gzip-compressed
(one BLOB row per page in the normal case) and decompressed in the Worker.

The path classifier here is mirrored exactly by site/worker/index.js; keep both in sync.
"""
from __future__ import annotations

import gzip
import hashlib
import html as _html
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

PART_BYTES = 40_000           # raw gzip bytes per part: a hex literal doubles it, so a statement stays well under 90 KB
MAX_STATEMENT_BYTES = 90_000
BATCH_BYTES = 3_000_000       # one `wrangler d1 execute --file` per batch (the first full upload used 2.9 MB files)
D1_DAILY_LIMIT = 100_000      # D1 free tier: rows written per UTC day
D1_MAX_ROWS_PER_RUN = 80_000  # budget: 80% of the daily limit, counting today's tally plus this run's plan


class BudgetExceeded(RuntimeError):
    """Today's D1 rows written plus the planned rows would pass the budget: nothing is written or deployed."""
MANIFEST_VERSION = "v2"       # v2 = gzip BLOB table `pg`; a v1 manifest (table `pages`) is never reused

JV_LABEL = "Gerçek kişi içeren iş ortaklığı"

# One row per page part: the sha lives on part 0 (no separate meta table, which would cost a row per page).
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS pg(path TEXT NOT NULL, part INTEGER NOT NULL, sha TEXT, gz BLOB NOT NULL, "
    "PRIMARY KEY(path, part)) WITHOUT ROWID;\n"
)
# The v1 tables are dropped in the deletion phase, after the Worker that reads `pg` is live.
DROP_V1 = "DROP TABLE IF EXISTS pages;\nDROP TABLE IF EXISTS page_meta;\n"

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


# ---- SQL generation (gzip BLOBs, one row per page in the normal case)
def sql_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def gzip_page(html: str) -> bytes:
    """Deterministic gzip (mtime 0) of the page, one single member: DecompressionStream reads it in the Worker."""
    return gzip.compress(html.encode("utf-8"), 9, mtime=0)


def gz_parts(gz: bytes, size: int | None = None) -> list[bytes]:
    """Split the *compressed* bytes (never separate gzip members) so every INSERT stays under the statement limit."""
    size = size or PART_BYTES
    return [gz[i:i + size] for i in range(0, len(gz), size)] or [b""]


def page_statements(path: str, gz: bytes, sha: str) -> list[str]:
    """Replace a page: delete its old parts, insert the new ones (sha on part 0). Replay-safe: the group starts with a
    DELETE, so running a batch twice (e.g. after a transient upload error) leaves the same rows."""
    out = [f"DELETE FROM pg WHERE path={sql_quote(path)};"]
    for i, part in enumerate(gz_parts(gz)):
        out.append(f"INSERT INTO pg(path,part,sha,gz) VALUES({sql_quote(path)},{i},{sql_quote(sha) if i == 0 else 'NULL'},X'{part.hex()}');")
    for s in out:
        if len(s.encode("utf-8")) > MAX_STATEMENT_BYTES:
            raise ValueError(f"SQL statement over {MAX_STATEMENT_BYTES} bytes for {path}")
    return out


def delete_statements(path: str) -> list[str]:
    return [f"DELETE FROM pg WHERE path={sql_quote(path)};"]


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
    total_bytes: int = 0          # HTML bytes of every staged page
    changed_html_bytes: int = 0
    gz_bytes: int = 0             # gzip bytes of the changed pages (what is actually stored)
    max_html_bytes: int = 0
    max_gz_bytes: int = 0
    gz: dict = field(default_factory=dict)                              # path -> gzip bytes of changed pages


def make_plan(stage_db: Path, manifest: dict[str, list]) -> Plan:
    plan = Plan()
    db = sqlite3.connect(stage_db)
    try:
        seen = set()
        for path, sha, html in db.execute("SELECT path, sha, html FROM staged ORDER BY path"):
            seen.add(path)
            nbytes = len(html.encode("utf-8"))
            plan.total_bytes += nbytes
            old = manifest.get(path)
            if old and old[0] == sha:
                plan.unchanged += 1
                continue
            gz = gzip_page(html)
            parts = len(gz_parts(gz))
            plan.upserts.append((path, sha, parts))
            plan.gz[path] = gz
            plan.changed_html_bytes += nbytes
            plan.gz_bytes += len(gz)
            plan.max_html_bytes = max(plan.max_html_bytes, nbytes)
            plan.max_gz_bytes = max(plan.max_gz_bytes, len(gz))
            plan.rows += (old[1] if old else 0) + parts           # old parts deleted + new parts inserted
        for path, old in manifest.items():
            if path.startswith("__"):
                continue                                            # bookkeeping keys, not pages
            if path not in seen:
                plan.deletes.append(path)
                plan.rows += old[1]
    finally:
        db.close()
    return plan


def plan_report(plan: Plan, *, rows_today: int = 0, max_rows: int = D1_MAX_ROWS_PER_RUN) -> str:
    n = len(plan.upserts)
    batches = batch_files([[f"x{'0' * (len(gz) * 2 + 120)}"] for gz in plan.gz.values()]) if n else []
    sizes = [sum(len(g[0]) + 1 for g in b) for b in batches]
    return "\n".join([
        f"D1 plan: {n} changed/new pages, {len(plan.deletes)} deletions, {plan.unchanged} unchanged",
        f"  rows to write: {plan.rows} ({plan.rows / n:.2f} per changed page)" if n else f"  rows to write: {plan.rows}",
        f"  HTML bytes of changed pages: {plan.changed_html_bytes:,} (mean {plan.changed_html_bytes // max(n, 1):,}, max {plan.max_html_bytes:,})",
        f"  gzip bytes stored: {plan.gz_bytes:,} (mean {plan.gz_bytes // max(n, 1):,}, max {plan.max_gz_bytes:,})",
        f"  SQL batch files: {len(batches)} (about {max(sizes, default=0) / 1e6:.1f} MB max, {sum(sizes) / 1e6:.1f} MB total)",
        f"  all staged pages: {plan.total_bytes / 1e6:.1f} MB of HTML",
        f"  rows written today (UTC): {rows_today}; with this run {rows_today + plan.rows} of the {max_rows} allowed",
    ])


def sync_pages(*, stage_db: Path, manifest_path: Path, batch_dir: Path, execute: Callable[[Path], None],
               between: Callable[[], None] | None = None, max_rows: int = D1_MAX_ROWS_PER_RUN,
               rows_today: int = 0, dry_run: bool = False, log: Callable[[str], None] = print) -> Plan:
    """Push changed pages to D1, run `between` (the Worker deploy), then push deletions (and drop the v1 tables);
    update the manifest after each successful batch. Idempotent: a re-run after a failure repeats only what is not
    in the manifest. With dry_run nothing is written (no batch files, no execute, no manifest change)."""
    manifest = load_manifest(manifest_path)
    plan = make_plan(stage_db, manifest)
    log(plan_report(plan, rows_today=rows_today, max_rows=max_rows))
    if rows_today + plan.rows > max_rows:
        raise BudgetExceeded(f"D1 write budget: {rows_today} rows already written today (UTC) + {plan.rows} planned = "
                             f"{rows_today + plan.rows}, over the budget of {max_rows} (80% of the free {D1_DAILY_LIMIT}/day). "
                             "Nothing was written or deployed; the live site is unchanged. Try again tomorrow.")
    if dry_run:
        return plan
    batch_dir.mkdir(parents=True, exist_ok=True)
    for old in batch_dir.glob("batch-*.sql"):
        old.unlink()

    groups = [page_statements(path, plan.gz[path], sha) for path, sha, _ in plan.upserts]
    n = 0
    idx = 0
    first_run = not manifest                                      # nothing deployed under this manifest yet
    for batch in batch_files(groups) if (groups or first_run) else []:
        text = SCHEMA + "".join(s + "\n" for g in batch for s in g)
        f = batch_dir / f"batch-{n:04d}.sql"
        f.write_text(text, encoding="utf-8", newline="\n")
        execute(f)
        for _ in batch:
            path, sha, parts = plan.upserts[idx]
            manifest[path] = [sha, parts]
            idx += 1
        save_manifest(manifest_path, manifest)
        n += 1

    if between:
        between()

    drop_v1 = "__v1_dropped__" not in manifest                   # one-time: remove the v1 tables once `pg` is live
    steps = [plan.deletes[k:k + 500] for k in range(0, len(plan.deletes), 500)] or ([[]] if drop_v1 else [])
    for part in steps:
        f = batch_dir / f"batch-{n:04d}.sql"
        f.write_text((DROP_V1 if drop_v1 else "") + "".join(s + "\n" for p in part for s in delete_statements(p)),
                     encoding="utf-8", newline="\n")
        execute(f)
        drop_v1 = False
        manifest["__v1_dropped__"] = ["1", 0]
        for p in part:
            manifest.pop(p, None)
        save_manifest(manifest_path, manifest)
        n += 1
    return plan


# ---- deploy-time masking guard (SPEC §6.1)
_YK = re.compile(r'<span class="yk" data-yk(?:="(own)")?>([^<]*)</span>')
_TITLE = re.compile(r"<title>(.*?) · İhale Gözlemevi</title>", re.S)
_DETAIL = re.compile(r"^/ihale/[^/]+/$")


def masking_violations(url: str, html: str) -> list[str]:
    """Marked yüklenici elements that show a name `is_natural_person` would mask. Only a record's own detail page
    may show such a name, and only in an element marked data-yk="own". Raw text is not scanned (company names can
    contain a founder's name; item texts can too)."""
    from .persons import PERSON_LABEL, is_natural_person
    out = []
    for m in _YK.finditer(html):
        own, name = m.group(1), _html.unescape(m.group(2))
        if own:
            if not _DETAIL.match(url):
                out.append(f"{url}: own-page marker outside a detail page ({name!r})")
        elif name not in (PERSON_LABEL, JV_LABEL, "okunamadı") and is_natural_person(name):   # placeholders are not names
            out.append(f"{url}: unmasked natural person {name!r}")
    if re.match(r"^/yuklenici/(?!liste/)[^/]+/", url):          # a dossier page (not the index or its pages)
        t = _TITLE.search(html)
        if t and is_natural_person(_html.unescape(t.group(1))):
            out.append(f"{url}: yüklenici page for a natural person ({_html.unescape(t.group(1))!r})")
    return out


def check_masking(dist: Path, stage_db: Path | None) -> None:
    """Raise RuntimeError if any page in `dist` or in the staged bulk pages leaks a masked name."""
    bad: list[str] = []
    for f in sorted(Path(dist).rglob("*.html")):
        rel = f.relative_to(dist).as_posix()
        url = url_path(rel)
        if url is not None:
            bad += masking_violations(url, f.read_text(encoding="utf-8"))
    if stage_db and Path(stage_db).is_file():
        db = sqlite3.connect(stage_db)
        try:
            for url, html in db.execute("SELECT path, html FROM staged"):
                bad += masking_violations(url, html)
        finally:
            db.close()
    if bad:
        raise RuntimeError("refusing to deploy: natural-person masking guard failed:\n  " + "\n  ".join(bad[:10])
                           + (f"\n  ... and {len(bad) - 10} more" if len(bad) > 10 else ""))


# ---- D1 free-tier usage warnings (80% of any limit)
LIMITS = {
    "rows written per day": 100_000,
    "rows read per day": 5_000_000,
    "total storage": 5_000_000_000,
    "database size": 500_000_000,
}
WARN_FRACTION = 0.8


def usage_warnings(*, rows_written_today: int | None, rows_read_today: int | None, db_bytes: int | None,
                   stored_bytes: int | None = None) -> list[str]:
    cur = {"rows written per day": rows_written_today, "rows read per day": rows_read_today,
           "total storage": db_bytes, "database size": db_bytes if db_bytes is not None else stored_bytes}
    out = []
    for name, limit in LIMITS.items():
        v = cur.get(name)
        if v is not None and v >= WARN_FRACTION * limit:
            out.append(f"D1 {name}: {v:,} is {100 * v / limit:.0f}% of the free limit ({limit:,})")
    return out


def rows_written_today(usage_path: Path, today: str) -> int:
    if usage_path.is_file():
        data = json.loads(usage_path.read_text(encoding="utf-8"))
        if data.get("date") == today:
            return int(data.get("rows_written", 0))
    return 0


def add_rows_written(usage_path: Path, rows: int, today: str) -> int:
    """Keep a per-UTC-day tally of rows we wrote (D1 resets its daily counters at 00:00 UTC); return today's total."""
    data = {}
    if usage_path.is_file():
        data = json.loads(usage_path.read_text(encoding="utf-8"))
    total = (data.get("rows_written", 0) if data.get("date") == today else 0) + rows
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    usage_path.write_text(json.dumps({"date": today, "rows_written": total}), encoding="utf-8")
    return total


def _sum_keys(obj, names: set[str]) -> int | None:
    found: list[int] = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower().replace("_", "") in names and isinstance(v, (int, float)):
                    found.append(int(v))
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return sum(found) if found else None


def parse_info_size(text: str) -> int | None:
    """Database size in bytes from `wrangler d1 info --json` output (None if not present)."""
    try:
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        return None
    return _sum_keys(data, {"filesize", "databasesize", "size", "sizeafter"})


def parse_rows_read(text: str) -> int | None:
    """Rows read (last day) from `wrangler d1 insights --json` output (None if not present)."""
    try:
        start = min(i for i in (text.find("["), text.find("{")) if i >= 0)
        data = json.loads(text[start:max(text.rfind("]"), text.rfind("}")) + 1])
    except (ValueError, TypeError):
        return None
    return _sum_keys(data, {"rowsread", "sumrowsread", "totalrowsread"})

# ---- maintainer identity guard (SPEC §6: no maintainer name, account or repo link on the site until G-Public)
ALLOWED_URLS = ("https://github.com/gulmezeren2-byte/ihalent",)         # the ihalent credit in Yöntem only
_ALWAYS = re.compile(r"github\.com|efebarlas", re.I)                     # forbidden anywhere, data included
_NAMES = re.compile(r"\b(?:Efe|Barlas)\b")                              # forbidden in page chrome and authored text
_MAIN = re.compile(r"<main\b.*?</main>", re.S)
# Pages whose <main> is authored text (not bulletin data): the name check covers their whole body.
_AUTHORED = ("/yontem/", "/404.html", "/arsiv/")


def identity_violations(url: str, text: str) -> list[str]:
    """`github.com` (except the ihalent URL) and `efebarlas` are forbidden everywhere. `Efe` / `Barlas` as whole words
    are forbidden in the page chrome (head, header, footer, headers files, Worker source) and on authored pages; inside
    the <main> of data pages they can be part of a contractor's name printed in the bulletin (e.g. «Efe Taşınmaz
    Değerleme …»), which is data, not the maintainer."""
    t = text
    for u in ALLOWED_URLS:
        t = t.replace(u, "")
    out = [f"{url}: {m.group(0)!r}" for m in _ALWAYS.finditer(t)]
    if url.endswith(".html") or url.endswith("/"):
        # <title> of a data page repeats the contractor / idare name, which is data too
        scan = t if url in _AUTHORED or not _MAIN.search(t) else re.sub(r"<title>.*?</title>", " ", _MAIN.sub(" ", t), flags=re.S)
    else:
        scan = t                                                    # _headers, robots.txt, Worker source, JSON, CSS
    if url.endswith(".json") and url != "/worker/index.js":
        scan = ""                                                   # search index of idare names: data
    out += [f"{url}: {m.group(0)!r}" for m in _NAMES.finditer(scan)]
    return out


def check_identity(dist: Path, stage_db: Path | None, worker_js: Path | None = None) -> None:
    """Raise RuntimeError if the site would publish the maintainer's identity (static files, staged D1 pages, the
    `_headers` file or the Worker source that sets response headers)."""
    bad: list[str] = []
    dist = Path(dist)
    for f in sorted(dist.rglob("*")):
        if f.is_file() and (f.suffix in (".html", ".txt", ".css", ".json", ".js", ".xml") or f.name == "_headers"):
            rel = f.relative_to(dist).as_posix()
            url = url_path(rel) or "/" + rel
            bad += identity_violations(url, f.read_text(encoding="utf-8", errors="replace"))
    if stage_db and Path(stage_db).is_file():
        db = sqlite3.connect(stage_db)
        try:
            for url, html in db.execute("SELECT path, html FROM staged"):
                bad += identity_violations(url, html)
        finally:
            db.close()
    if worker_js and Path(worker_js).is_file():
        bad += identity_violations("/worker/index.js", Path(worker_js).read_text(encoding="utf-8"))
    if bad:
        raise RuntimeError("refusing to deploy: maintainer identity guard failed:\n  " + "\n  ".join(bad[:10])
                           + (f"\n  ... and {len(bad) - 10} more" if len(bad) > 10 else ""))
