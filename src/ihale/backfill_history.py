"""History backfill FETCHER (M5f): walks backwards from the oldest stored day, downloads bulletin zips into the cache
only (no parse, no DB, no site), very slowly, only inside a night window.

Hard stops (SPEC §6/§7): any BlockedError (or an existing BLOCKED marker) stops everything and is never worked
around. Spacing is on top of ekap.RateLimiter: `min_gap`..`max_gap` seconds (random) between EKAP requests.

With a plan (data dir `backfill-plan.txt`, see backfill_plan.py) the listed (date, type) targets come first, in file
order, then the day-by-day walk continues.

The per-run request cap counts requests of THIS run (client.requests_made); the per-UTC-day counter is a shared
backstop only, so its reset at 00:00 UTC cannot let a run exceed max_requests.

Exit codes: 0 done / request budget of this run used / outside the window, 1 error, 3 BLOCKED, 5 shared daily cap.
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import config, ekap, pipeline
from .store import Store

log = logging.getLogger("ihale")

DEFAULT_MAX_REQUESTS = 150
DEFAULT_MIN_GAP = 150.0
DEFAULT_MAX_GAP = 240.0
# Spec-owner ramp (after 3 clean nights): gaps 120-200 s for runs STARTING on or after 2026-11-26 (UTC); a run that
# starts earlier keeps 150-240 s for its whole length. Any block puts it back to 150-240 s (change RAMP_FROM / the pair).
RAMP_FROM = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)   # before the 14:00 PST (22:00 UTC) run of that day
RAMP_GAPS = (120.0, 200.0)


def default_gaps(started_utc: datetime) -> tuple[float, float]:
    return RAMP_GAPS if started_utc >= RAMP_FROM else (DEFAULT_MIN_GAP, DEFAULT_MAX_GAP)
DEFAULT_WINDOW_UTC = "22:00-04:30"       # 01:00-07:30 Europe/Istanbul
DEFAULT_EARLIEST = date(2010, 1, 1)
TYPES = ("mal", "hizmet", "yapim")


MAX_HOPS = 3                                  # planned day without any bulletin: try up to 3 following business days
PLAN_FILE = "backfill-plan.txt"


@dataclass(frozen=True)
class PlanEntry:
    day: date
    type: str
    origin: date          # the day the plan asked for (a hop moves `day` on, never `origin`)
    hop: int = 0


def _next_business_day(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def plan_path() -> Path:
    return config.data_dir() / PLAN_FILE


def load_plan(path: Path | None = None) -> list[PlanEntry]:
    """Ordered targets, one `YYYY-MM-DD type` per line ('#' comments and blank lines ignored). Append more lines (a
    later phase) at the end and they are fetched before the day-by-day walk. Unknown types / dates raise ValueError."""
    path = path or plan_path()
    out: list[PlanEntry] = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2 or parts[1] not in TYPES:
            raise ValueError(f"{path}:{n}: expected 'YYYY-MM-DD <{'|'.join(TYPES)}>', got {raw!r}")
        d = date.fromisoformat(parts[0])
        out.append(PlanEntry(d, parts[1], d))
    return out


def parse_window(s: str) -> tuple[dtime, dtime]:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", s or "")
    if not m:
        raise ValueError(f"bad window {s!r}: use HH:MM-HH:MM (UTC)")
    a, b, c, d = (int(x) for x in m.groups())
    if not (a < 24 and c < 24 and b < 60 and d < 60):
        raise ValueError(f"bad window {s!r}")
    return dtime(a, b), dtime(c, d)


def in_window(now_utc: datetime, window: tuple[dtime, dtime]) -> bool:
    """True when now (UTC) is inside [start, end); a window with start > end wraps past midnight."""
    t = now_utc.astimezone(timezone.utc).time().replace(tzinfo=None)
    start, end = window
    if start == end:
        return True
    return start <= t < end if start < end else (t >= start or t < end)


def start_day(store: Store | None = None) -> date | None:
    """Day before the oldest stored day (derived from the DB, never hardcoded)."""
    days = (store or Store()).dates()
    return min(days) - timedelta(days=1) if days else None


class _Progress:
    def __init__(self, data: Path):
        self.log_file = data / "logs" / "backfill-progress.log"
        self.state_file = data / "backfill-state.json"
        self.state: dict = {}

    def line(self, day, type_, result: str, used: int) -> None:
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {day or '-'} {type_ or '-'} {result} "
                         f"requests_today={used}\n")
        except OSError as e:  # noqa: BLE001
            log.error("cannot write progress log: %s", e)

    def write_state(self, **kw) -> None:
        self.state.update(kw)
        self.state["updated_utc"] = f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}"
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        except OSError as e:  # noqa: BLE001
            log.error("cannot write backfill state: %s", e)


def run(client: ekap.EkapClient, *, begin: date | None = None, earliest: date = DEFAULT_EARLIEST, types=TYPES,
        max_requests: int = DEFAULT_MAX_REQUESTS, min_gap: float = DEFAULT_MIN_GAP, max_gap: float = DEFAULT_MAX_GAP,
        window: tuple[dtime, dtime] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], None] = time.sleep, rng: random.Random | None = None,
        bulletins: Path | None = None, plan: list | None = None) -> int:
    rng = rng or random.Random()
    window = window or parse_window(DEFAULT_WINDOW_UTC)
    data = config.data_dir()
    prog = _Progress(data)
    root = bulletins or config.bulletins_dir()
    used = lambda: client.budget.used()  # noqa: E731
    prog.write_state(started_utc=f"{now():%Y-%m-%dT%H:%M:%SZ}", window_utc=f"{window[0]:%H:%M}-{window[1]:%H:%M}",
                     max_requests=max_requests, fetched=0, no_bulletin=0, skipped_cached=0, skipped_empty=0,
                     stop_reason=None)

    def done(code: int, reason: str, day=None) -> int:
        prog.write_state(exit_code=code, stop_reason=reason, next_day=day, requests_this_run=client.requests_made,
                         requests_today=used())
        prog.line(day, None, f"STOP {reason}", used())
        log.info("backfill-history stop (exit %d): %s", code, reason)
        return code

    if not in_window(now(), window):
        return done(0, f"outside window {window[0]:%H:%M}-{window[1]:%H:%M} UTC now={now():%H:%M}")
    try:
        pipeline.check_not_blocked()
    except pipeline.BlockedMarkerPresent as e:
        log.error("%s", e)
        return done(pipeline.EXIT_BLOCKED, "BLOCKED marker present")
    if begin is None:
        begin = start_day()
    if begin is None:
        return done(pipeline.EXIT_ERROR, "no stored days; cannot derive the starting day")
    known = pipeline._known_no_bulletin()
    prog.line(begin, None, f"START resume_from window={window[0]:%H:%M}-{window[1]:%H:%M}Z max_requests={max_requests}", used())

    def paced(fn):
        """Run one EKAP-touching call with the random gap before it (none before the run's first request)."""
        if client.requests_made > 0:
            sleep(rng.uniform(min_gap, max(min_gap, max_gap)))
        if not in_window(now(), window):
            raise _WindowClosed()
        return fn()

    class _Stop(Exception):
        def __init__(self, code: int, reason: str, day):
            self.code, self.reason, self.day = code, reason, day

    def handle(day: date, t: str) -> str:
        """One (day, type) target. Returns cached | empty | fetched | no_bulletin; raises _Stop when the run must end.
        The cache is looked at right before every request, so a file that appeared meanwhile (another process, an
        earlier plan entry) is never fetched twice."""
        if ekap.bulletin_paths(root, day, t)[1].exists():
            prog.state["skipped_cached"] += 1
            return "cached"
        if f"{day.isoformat()} {t}" in known:
            prog.state["skipped_empty"] += 1
            return "empty"
        if client.requests_made >= max_requests:
            raise _Stop(0, f"request budget of this run used ({client.requests_made}/{max_requests})", day)
        if used() >= client.budget.limit:
            raise _Stop(pipeline.EXIT_CAP, f"shared daily cap reached ({used()}/{client.budget.limit})", day)
        if client._form is None:
            paced(client.load_form)   # the one form GET counts as a request (and gets its own gap)
            if client.requests_made >= max_requests or used() >= client.budget.limit:
                raise _Stop(0 if client.requests_made >= max_requests else pipeline.EXIT_CAP,
                            "budget used by the form request", day)
        try:
            paced(lambda: client.fetch(day, t, root=root))
            result = "fetched"
            prog.state["fetched"] += 1
        except ekap.NoBulletinError:
            result = "no_bulletin"
            pipeline._remember_no_bulletin(day, t)
            known.add(f"{day.isoformat()} {t}")
            prog.state["no_bulletin"] += 1
        prog.line(day, t, result, used())
        prog.write_state(last_day=day, last_type=t, requests_this_run=client.requests_made, requests_today=used())
        return result

    day = begin
    try:
        # ---- phase A: the planned (date, type) list, in file order; a day whose types all came back empty is retried
        # on the next business day at the END of the list (the "second pass"), at most MAX_HOPS times
        if plan:
            queue = deque(plan)
            per_origin = {}
            for e in plan:
                per_origin.setdefault(e.origin, set()).add(e.type)
            empties: dict[date, set] = {}
            prog.write_state(plan_total=len(plan), plan_done=0)
            n_done = 0
            while queue:
                e = queue.popleft()
                day = e.day
                if handle(e.day, e.type) in ("empty", "no_bulletin"):
                    empties.setdefault((e.origin, e.day), set()).add(e.type)
                    if empties[(e.origin, e.day)] >= per_origin[e.origin] and e.hop < MAX_HOPS:
                        nxt = _next_business_day(e.day)
                        queue.extend(PlanEntry(nxt, t2, e.origin, e.hop + 1) for t2 in sorted(per_origin[e.origin], key=TYPES.index))
                n_done += 1
                prog.write_state(plan_done=n_done, plan_left=len(queue))
            prog.write_state(plan_exhausted=True)
            day = begin
        # ---- phase B: the day-by-day walk backwards
        while day >= earliest:
            if day.weekday() >= 5:
                day -= timedelta(days=1)
                continue
            for t in types:
                handle(day, t)
            prog.write_state(oldest_reached=day)
            day -= timedelta(days=1)
    except _Stop as e:
        return done(e.code, e.reason, e.day)
    except _WindowClosed:
        return done(0, "window closed while waiting", day)
    except ekap.BlockedError as e:
        if not pipeline.blocked_marker().exists():
            pipeline.write_blocked_marker(str(e))
        prog.line(day, None, f"BLOCKED {e}", used())
        return done(pipeline.EXIT_BLOCKED, f"BLOCKED: {e}", day)
    except ekap.RequestBudgetExceeded as e:
        return done(pipeline.EXIT_CAP, f"budget: {e}", day)
    except Exception as e:  # noqa: BLE001  (unexpected page, mismatch, network): stop, a human looks
        log.error("backfill-history stopped by %s: %s", type(e).__name__, e)
        prog.line(day, None, f"ERROR {type(e).__name__}: {e}", used())
        return done(pipeline.EXIT_ERROR, f"{type(e).__name__}: {e}", day)
    return done(0, f"done: reached {earliest}", day)


class _WindowClosed(Exception):
    pass
