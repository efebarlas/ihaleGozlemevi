from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from . import config, ekap, pipeline
from .keepawake import keep_awake

# exit codes: 0 ok, 1 error, 2 usage, 3 BLOCKED (EKAP hard stop / marker present), 4 no bulletin (fetch only),
# 5 backfill stopped at the request cap (also backfill-history: shared daily cap)
BULLETIN_TYPES = sorted(ekap.TYPE_CODES)
DEFAULT_TYPES = ["mal", "hizmet", "yapim"]     # run / backfill; resolved at call time (tests patch it)


def parse_day(s: str) -> date:
    """DD.MM.YYYY (as EKAP shows it) or YYYY-MM-DD."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"bad date {s!r}: use DD.MM.YYYY or YYYY-MM-DD")


def parse_types(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        for t in v.split(","):
            t = t.strip().lower()
            if not t:
                continue
            if t not in ekap.TYPE_CODES:
                raise argparse.ArgumentTypeError(f"unknown type {t!r}; expected one of {BULLETIN_TYPES}")
            if t not in out:
                out.append(t)
    if not out:
        raise argparse.ArgumentTypeError("no types given")
    return out


def cmd_fetch(args) -> int:
    try:
        pipeline.check_not_blocked()
    except pipeline.BlockedMarkerPresent as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return pipeline.EXIT_BLOCKED
    try:
        day = parse_day(args.date)
    except argparse.ArgumentTypeError as e:
        print(str(e), file=sys.stderr)
        return 2
    cache = config.data_dir() / "form-cache.html" if args.cache_form else None
    client = ekap.EkapClient(form_cache=cache)
    try:
        d = client.fetch(day, args.type, force=args.force)
    except ekap.BlockedError as e:
        pipeline.write_blocked_marker(str(e))
        print(f"BLOCKED: {e}", file=sys.stderr)
        return pipeline.EXIT_BLOCKED
    except ekap.NoBulletinError as e:
        print(f"NO BULLETIN: {e}", file=sys.stderr)
        return pipeline.EXIT_NO_BULLETIN
    print(f"{d} ({client.requests_made} EKAP request(s))")
    return 0


def cmd_parse(args) -> int:
    try:
        n = pipeline.parse_and_store(args.date, args.type)
    except Exception as e:  # noqa: BLE001
        print(f"parse failed: {type(e).__name__}: {e}", file=sys.stderr)
        return pipeline.EXIT_ERROR
    print(f"stored {n} records for {args.date} {args.type}")
    return 0


def cmd_flag(args) -> int:
    counts = pipeline.flag_all()
    print(f"flags: {counts or 'none'}")
    return 0


def cmd_export(args) -> int:
    print(pipeline.export_step())
    return 0


def cmd_export_open(args) -> int:
    """Private OCDS + FollowTheMoney files under <data>/exports/ (never deployed; not part of the daily run)."""
    from . import openexport
    from .store import Store
    store = Store()
    if args.all:
        days = store.dates()
    elif args.date:
        days = [args.date]
    else:
        days = None          # latest stored day
    paths = openexport.export_open(store, days)
    for p in paths:
        print(p)
    if not paths:
        print("nothing to export (no stored records for the requested day)", file=sys.stderr)
    return 0


def cmd_drift(args) -> int:
    from . import drift
    from .store import Store
    p = drift.write_weekly(Store().all_records(), force=args.force)
    print(p if p else "this week's drift summary already exists (use --force to rewrite it)")
    return 0


def cmd_build(args) -> int:
    try:
        pipeline.build_site(args.out)
    except Exception as e:  # noqa: BLE001
        print(f"build failed: {type(e).__name__}: {e}", file=sys.stderr)
        return pipeline.EXIT_ERROR
    return 0


def cmd_deploy(args) -> int:
    try:
        pipeline.deploy_site()
    except Exception as e:  # noqa: BLE001
        if pipeline.is_budget_exceeded(e):
            print(f"not deployed, try tomorrow: {e}", file=sys.stderr)
            return pipeline.EXIT_BUDGET
        print(f"deploy failed: {type(e).__name__}: {e}", file=sys.stderr)
        return pipeline.EXIT_ERROR
    return 0


def cmd_run(args) -> int:
    with keep_awake(), pipeline.file_logging():
        return pipeline.run_daily(args.date, args.types, deploy=not args.no_deploy)


def cmd_backfill(args) -> int:
    with pipeline.file_logging():
        return pipeline.backfill(args.days, args.types, args.max_requests)


def cmd_backfill_history(args) -> int:
    from . import backfill_history as bh
    try:
        window = bh.parse_window(args.window_utc)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    plan = None
    if not args.no_plan:
        pf = args.plan or bh.plan_path()
        if args.plan or pf.is_file():
            try:
                plan = bh.load_plan(pf)
            except (OSError, ValueError) as e:
                print(f"bad plan file: {e}", file=sys.stderr)
                return 2
    if args.dry_run:      # no EKAP, no state files: show what would be asked first
        todo = [e for e in (plan or []) if not ekap.bulletin_paths(config.bulletins_dir(), e.day, e.type)[1].exists()]
        print(f"plan: {len(plan or [])} targets, {len(todo)} not cached yet; first 10:")
        for e in todo[:10]:
            print(f"  {e.day.isoformat()} {e.type}")
        return 0
    with keep_awake(), pipeline.file_logging():
        client = ekap.EkapClient(max_requests=args.max_requests + 5)   # run() enforces --max-requests itself
        code = bh.run(client, begin=args.start, earliest=args.earliest, types=args.types,
                      max_requests=args.max_requests, min_gap=args.min_gap_seconds,
                      max_gap=max(args.min_gap_seconds, args.max_gap_seconds), window=window, plan=plan)
        if code != pipeline.EXIT_BLOCKED and not args.no_history_parse:
            try:        # research only (<data>/research/history.db): offline, after the fetching; never changes the exit code
                from . import history
                history.sync(max_seconds=args.history_parse_minutes * 60)   # ~44 s per bulletin: stay clear of the 21:30 daily run
                history.write_report()
            except Exception as e:  # noqa: BLE001
                pipeline._log_exc("history-parse after backfill failed (ignored)", e)
        return code


def cmd_history_parse(args) -> int:
    from . import history
    with pipeline.file_logging():
        if not args.report_only:
            print("history-parse:", history.sync(reflag=args.reflag, limit=args.limit,
                                          max_seconds=args.max_minutes * 60 if args.max_minutes else None))
        out = history.write_report()
    print(f"report -> {out}")
    return 0


def cmd_backfill_plan(args) -> int:
    from . import backfill_plan as bp
    text = bp.render(args.seed)
    if not args.write:
        print(text, end="")
        return 0
    from . import backfill_history as bh
    path = bh.plan_path()
    if path.exists() and not args.force:
        print(f"{path} exists; not overwritten (--force to replace)", file=sys.stderr)
        return 2
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ihale", description="Ihale Gozlemevi pipeline")
    sub = p.add_subparsers(dest="command", required=True)
    day_help = "DD.MM.YYYY or YYYY-MM-DD"

    f = sub.add_parser("fetch", help="download an EKAP bulletin into the data dir")
    f.add_argument("--date", required=True, help=day_help)  # kept as the string given (M0 test)
    f.add_argument("--type", default="mal", choices=BULLETIN_TYPES)
    f.add_argument("--force", action="store_true", help="re-download even if cached")
    f.add_argument("--cache-form", action="store_true", help="dev: reuse a saved form page (skips the GET)")
    f.set_defaults(func=cmd_fetch)

    pa = sub.add_parser("parse", help="parse a local SONUC pdf and store its records")
    pa.add_argument("--date", required=True, type=parse_day, help=day_help)
    pa.add_argument("--type", default="mal", choices=BULLETIN_TYPES)
    pa.set_defaults(func=cmd_parse)

    sub.add_parser("flag", help="recompute flags for all stored records").set_defaults(func=cmd_flag)
    sub.add_parser("export", help="write export/meta.json and export/days/*.json").set_defaults(func=cmd_export)

    eo = sub.add_parser("export-open", help="private OCDS 1.1 + FollowTheMoney exports under <data>/exports/")
    g = eo.add_mutually_exclusive_group()
    g.add_argument("--date", type=parse_day, help=day_help + " (default: the latest stored day)")
    g.add_argument("--all", action="store_true", help="every stored day")
    eo.set_defaults(func=cmd_export_open)

    dr = sub.add_parser("drift", help="weekly drift summary (idare procedure mix vs own history) into the logs")
    dr.add_argument("--force", action="store_true", help="rewrite this ISO week's file")
    dr.set_defaults(func=cmd_drift)

    b = sub.add_parser("build", help="build the static site from the export")
    b.add_argument("--out", type=Path, default=None,
                   help="output dir (default: <repo>/site/dist)")
    b.set_defaults(func=cmd_build)
    sub.add_parser("deploy", help="deploy the built site (via ihale.sitegen.deploy)").set_defaults(func=cmd_deploy)

    r = sub.add_parser("run", help="daily job: fetch, parse, store, flag, export, build, deploy")
    r.add_argument("--date", type=parse_day, default=None, help=day_help + " (default: today, Europe/Istanbul)")
    r.add_argument("--types", nargs="+", default=None, type=str,
                   help="default: mal hizmet yapim; e.g. mal  or  mal,hizmet")
    r.add_argument("--no-deploy", action="store_true")
    r.set_defaults(func=cmd_run)

    bf = sub.add_parser("backfill", help="load the last N days of history (sequential, rate limited)")
    bf.add_argument("--days", type=int, required=True)
    bf.add_argument("--types", nargs="+", default=None, type=str, help="default: mal hizmet yapim")
    bf.add_argument("--max-requests", type=int, default=None,
                    help=f"raise the per-run EKAP request cap (default {ekap.MAX_REQUESTS_PER_RUN})")
    bf.set_defaults(func=cmd_backfill)

    bh = sub.add_parser("backfill-history", help="fetch ONLY: old bulletins into the cache, walking back from the oldest "
                        "stored day, slowly, inside a night window (no parse, no DB, no site)")
    bh.add_argument("--max-requests", type=int, default=150, help="EKAP requests this run may use (default 150)")
    bh.add_argument("--min-gap-seconds", type=float, default=150.0, help="min gap between requests (default 150)")
    bh.add_argument("--max-gap-seconds", type=float, default=240.0, help="max gap; the gap is random in between (default 240)")
    bh.add_argument("--window-utc", default="22:00-04:30",
                    help="only run inside this UTC window HH:MM-HH:MM (default 22:00-04:30 = 01:00-07:30 TRT)")
    bh.add_argument("--types", nargs="+", default=None, type=str, help="default: mal hizmet yapim, in that order")
    bh.add_argument("--start", type=parse_day, default=None, help="first day to try (default: day before the oldest stored)")
    bh.add_argument("--earliest", type=parse_day, default=date(2010, 1, 1), help="stop at this day (default 2010-01-01)")
    bh.add_argument("--plan", type=Path, default=None,
                    help="ordered `YYYY-MM-DD type` targets fetched before the walk (default: <data>/backfill-plan.txt if present)")
    bh.add_argument("--no-plan", action="store_true", help="ignore the plan file: day-by-day walk only")
    bh.add_argument("--no-history-parse", action="store_true",
                    help="skip the offline parse into research/history.db after the run")
    bh.add_argument("--history-parse-minutes", type=float, default=40.0,
                    help="time cap for the after-run parse; the rest stays pending (default 40)")
    bh.add_argument("--dry-run", action="store_true", help="print the first 10 uncached plan targets and exit (no EKAP)")
    bh.set_defaults(func=cmd_backfill_history)

    hp = sub.add_parser("history-parse", help="parse the backfilled bulletins into <data>/research/history.db (research only)")
    hp.add_argument("--reflag", action="store_true", help="recompute flags even if nothing new was parsed")
    hp.add_argument("--max-minutes", type=float, default=None, help="stop starting new bulletins after N minutes")
    hp.add_argument("--limit", type=int, default=None, help="parse at most N bulletins this run")
    hp.add_argument("--report-only", action="store_true", help="skip parsing; just rewrite history-report.json")
    hp.set_defaults(func=cmd_history_parse)

    bp = sub.add_parser("backfill-plan", help="print (or --write into the data dir) the seeded phase-1 target list")
    bp.add_argument("--seed", type=int, default=20261123)
    bp.add_argument("--write", action="store_true")
    bp.add_argument("--force", action="store_true", help="overwrite an existing plan file")
    bp.set_defaults(func=cmd_backfill_plan)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "types"):
        try:
            args.types = parse_types(args.types or DEFAULT_TYPES)
        except argparse.ArgumentTypeError as e:
            parser.error(str(e))
    if getattr(args, "days", 1) < 1:
        parser.error("--days must be >= 1")
    return args.func(args)
