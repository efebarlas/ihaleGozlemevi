"""The daily pipeline: fetch → parse → store → flag → export → build → deploy, and the history backfill.

Seams for tests (monkeypatch these): make_client(), parse_module(), sitegen_module(), repo_root().
`ihale.parse` and `ihale.sitegen` are imported lazily: other builders write them.
"""
from __future__ import annotations

import importlib
import logging
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config, ekap
from .export import TR_TZ, export_all, export_dir
from .flags import compute_flags_full
from .store import Store

log = logging.getLogger("ihale")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 3          # EKAP hard stop, or the BLOCKED marker is present (same code as `fetch`)
EXIT_NO_BULLETIN = 4      # `fetch` only; `run` treats it as a normal day
EXIT_CAP = 5              # backfill stopped at the request cap; re-run to continue


def today_istanbul() -> date:
    return datetime.now(TR_TZ).date()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def make_client(max_requests: int | None = None) -> ekap.EkapClient:
    if max_requests is None:
        return ekap.EkapClient()
    return ekap.EkapClient(max_requests=max_requests)


def parse_module():
    return importlib.import_module("ihale.parse")


def sitegen_module():
    return importlib.import_module("ihale.sitegen")


# ---------------------------------------------------------------- BLOCKED marker (SPEC §6)
def blocked_marker() -> Path:
    return config.data_dir() / "BLOCKED"


class BlockedMarkerPresent(Exception):
    pass


def check_not_blocked() -> None:
    """The single gate before any scraping. Raises if a human has not yet cleared a previous hard stop."""
    m = blocked_marker()
    if m.exists():
        raise BlockedMarkerPresent(
            f"{m} exists: EKAP blocked us earlier. Do not scrape. Read it, resolve the cause, then delete it.\n"
            + m.read_text(encoding="utf-8", errors="replace"))


def write_blocked_marker(reason: str) -> Path:
    m = blocked_marker()
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(
        f"BLOCKED at {datetime.now(TR_TZ).isoformat(timespec='seconds')}\n{reason}\n\n"
        "EKAP blocked, rate-limited or challenged this client. All scraping is suspended (SPEC §6).\n"
        "A human must investigate and then delete this file before any run will contact EKAP again.\n",
        encoding="utf-8")
    return m


# ---------------------------------------------------------------- logging
@contextmanager
def file_logging():
    """Append to <data>/logs/YYYY-MM-DD.log (and echo to stdout) for the duration of one command."""
    logs = config.data_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(logs / f"{today_istanbul().isoformat()}.log", mode="a", encoding="utf-8")
    sh = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handlers = (fh, sh)
    for h in handlers:
        h.setFormatter(fmt)
        log.addHandler(h)
    old_level = log.level
    log.setLevel(logging.INFO)
    try:
        yield
    finally:
        for h in handlers:
            log.removeHandler(h)
            h.close()
        log.setLevel(old_level)


# ---------------------------------------------------------------- steps
def find_sonuc_pdf(day: date, type_: str, root: Path | None = None) -> Path | None:
    d, _ = ekap.bulletin_paths(root or config.bulletins_dir(), day, type_)
    exact = d / f"BULTEN_{day:%d%m%Y}_{type_.upper()}_SONUC.pdf"
    if exact.exists():
        return exact
    for p in sorted(d.glob("*.pdf")) if d.exists() else []:
        if p.name.upper().endswith(f"_{type_.upper()}_SONUC.PDF"):
            return p
    return None


def parse_and_store(day: date, type_: str, store: Store | None = None) -> int:
    pdf = find_sonuc_pdf(day, type_)
    if pdf is None:
        raise FileNotFoundError(f"no local SONUC pdf for {day} {type_} (run fetch first)")
    records = parse_module().parse_bulletin(pdf, day, type_)
    warnings = sum(len(r.warnings) for r in records)
    n = (store or Store()).replace_day(day, type_, records)
    log.info("parsed %s %s: %d records, %d warnings (%s)", day, type_, n, warnings, pdf.name)
    return n


def flag_all(store: Store | None = None) -> dict[str, int]:
    store = store or Store()
    stored = store.all_records()
    results, part_rates = compute_flags_full(stored)
    store.set_meta("part_rates", part_rates)
    store.set_flags({i: {"flags": r.flags, "unreadable": r.unreadable, "kisim_n": r.kisim_n, "score": r.score,
                         "score_parts": r.score_parts, "idare_stats": r.idare_stats, "indicators": r.indicators,
                         "structural": r.structural} for i, r in results.items()})
    counts: dict[str, int] = {}
    for r in results.values():
        for f in r.flags:
            counts[f["code"]] = counts.get(f["code"], 0) + 1
    log.info("flagged %d records: %s", len(stored), counts or "none")
    return counts


def export_step(store: Store | None = None) -> Path:
    """Export JSON for the site, then the local-only oracle candidates (a failure there never stops the run)."""
    from .oracle import write_candidates
    store = store or Store()
    out = export_all(store)
    try:
        log.info("oracle candidates: %s", write_candidates(store))
    except Exception as e:  # noqa: BLE001
        _log_exc("oracle candidates failed (continuing)", e)
    return out


def build_site(out_dir: Path | None = None) -> None:
    out_dir = out_dir or repo_root() / "site" / "dist"
    sitegen_module().build(export_dir(), out_dir)
    log.info("site built in %s", out_dir)


def deploy_site() -> None:
    sitegen_module().deploy()
    log.info("site deployed")


def _log_exc(msg: str, e: BaseException) -> None:
    log.error("%s: %s: %s", msg, type(e).__name__, e)


# ---------------------------------------------------------------- loading days (shared by run catch-up and backfill)
CATCH_UP_DAYS = 7


def _no_bulletin_file() -> Path:
    return config.data_dir() / "no-bulletin.txt"


def _known_no_bulletin() -> set[str]:
    try:
        return set(_no_bulletin_file().read_text(encoding="utf-8").split("\n")) - {""}
    except OSError:
        return set()


def _remember_no_bulletin(day: date, type_: str) -> None:
    """Holidays are stable: remember them so catch-up does not ask EKAP again every day."""
    f = _no_bulletin_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(f"{day.isoformat()} {type_}\n")


def load_days(client, store: Store, window: list[date], types, *, skip_known_empty: bool = False,
              reserve_requests: int = 0) -> None:
    """Fetch + parse every workday of `window` (oldest first) that has no stored records yet.

    Weekends are skipped without a request. A bulletin already on disk is not re-downloaded, only parsed if the
    store has nothing for it. NoBulletin is a skip. BlockedError propagates. RequestBudgetExceeded propagates,
    except that with `reserve_requests` the loop stops quietly that many requests before the cap.
    """
    known = _known_no_bulletin() if skip_known_empty else set()
    cap = getattr(client, "max_requests", None)
    for day in window:
        if day.weekday() >= 5:
            log.info("%s: weekend, skipped", day)
            continue
        for t in types:
            if store.has_day(day, t):
                log.info("%s %s: already stored, skipped", day, t)
                continue
            if f"{day.isoformat()} {t}" in known:
                log.info("%s %s: known no-bulletin day, skipped", day, t)
                continue
            cached = ekap.bulletin_paths(config.bulletins_dir(), day, t)[1].exists()
            if not cached:
                if reserve_requests and cap is not None and getattr(client, "requests_made", 0) >= cap - reserve_requests:
                    log.warning("%s %s: request budget nearly used (%s/%s); stopping catch-up", day, t,
                                client.requests_made, cap)
                    return
                try:
                    client.fetch(day, t)
                except ekap.NoBulletinError:
                    log.info("%s %s: no bulletin, skipped", day, t)
                    _remember_no_bulletin(day, t)
                    continue
            parse_and_store(day, t, store)


# ---------------------------------------------------------------- run
def run_daily(day: date | None = None, types=("mal",), deploy: bool = True) -> int:
    """fetch → parse → store → flag → export → build → deploy. Returns the process exit code."""
    day = day or today_istanbul()
    log.info("run start: %s types=%s deploy=%s", day, ",".join(types), deploy)
    try:
        check_not_blocked()
    except BlockedMarkerPresent as e:
        log.error("%s", e)
        return EXIT_BLOCKED
    try:
        client = make_client()
        store = Store()
        # Efe's PC is sometimes off: first catch up workdays of the last 7 days that have no stored records.
        # Shares the per-run request cap; one request is kept in reserve for today's bulletin.
        window = [day - timedelta(days=i) for i in range(CATCH_UP_DAYS, 0, -1)]
        load_days(client, store, window, types, skip_known_empty=True, reserve_requests=len(types))
        for t in types:
            try:
                client.fetch(day, t)
            except ekap.NoBulletinError as e:
                log.info("no %s bulletin for %s (%s); keeping the existing data", t, day, e)
                continue
            parse_and_store(day, t, store)
        flag_all(store)
        export_step(store)
        build_site()
        if deploy:
            deploy_site()
        else:
            log.info("--no-deploy: skipping deploy")
    except ekap.BlockedError as e:
        m = write_blocked_marker(str(e))
        log.error("EKAP BLOCKED: %s. Wrote %s. Not deploying; all scraping is suspended.", e, m)
        return EXIT_BLOCKED
    except Exception as e:  # noqa: BLE001: a failed run must exit non-zero and not deploy
        _log_exc("run failed (not deployed)", e)
        return EXIT_ERROR
    log.info("run done")
    return EXIT_OK


# ---------------------------------------------------------------- backfill
def backfill(days: int, types=("mal",), max_requests: int | None = None, today: date | None = None) -> int:
    """Fetch+parse the last `days` calendar days (ending today), oldest first, strictly sequentially.

    Weekends are skipped without a request. A day with a local bulletin is not re-downloaded, but is parsed if
    the store has nothing for it. NoBulletin is a skip; BlockedError stops at once and writes the marker.
    """
    today = today or today_istanbul()
    log.info("backfill start: last %d days to %s types=%s max_requests=%s", days, today, ",".join(types), max_requests)
    try:
        check_not_blocked()
    except BlockedMarkerPresent as e:
        log.error("%s", e)
        return EXIT_BLOCKED
    code = EXIT_OK
    try:
        client = make_client(max_requests)
        store = Store()
        window = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
        load_days(client, store, window, types)
    except ekap.BlockedError as e:
        m = write_blocked_marker(str(e))
        log.error("EKAP BLOCKED: %s. Wrote %s. Backfill stopped.", e, m)
        return EXIT_BLOCKED
    except ekap.RequestBudgetExceeded as e:
        log.warning("backfill stopped: %s. Re-run (optionally with --max-requests) to continue.", e)
        code = EXIT_CAP
    except Exception as e:  # noqa: BLE001
        _log_exc("backfill failed", e)
        return EXIT_ERROR
    try:
        flag_all(store)
        export_all(store)
    except Exception as e:  # noqa: BLE001
        _log_exc("backfill: flag/export failed", e)
        return EXIT_ERROR
    log.info("backfill done (exit %d)", code)
    return code
