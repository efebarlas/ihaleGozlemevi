from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from . import config, ekap, pipeline

# exit codes: 0 ok, 1 error, 2 usage, 3 BLOCKED (EKAP hard stop / marker present), 4 no bulletin (fetch only),
# 5 backfill stopped at the request cap
BULLETIN_TYPES = sorted(ekap.TYPE_CODES)


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
    from .export import export_all
    print(export_all())
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
        print(f"deploy failed: {type(e).__name__}: {e}", file=sys.stderr)
        return pipeline.EXIT_ERROR
    return 0


def cmd_run(args) -> int:
    with pipeline.file_logging():
        return pipeline.run_daily(args.date, args.types, deploy=not args.no_deploy)


def cmd_backfill(args) -> int:
    with pipeline.file_logging():
        return pipeline.backfill(args.days, args.types, args.max_requests)


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

    b = sub.add_parser("build", help="build the static site from the export")
    b.add_argument("--out", type=Path, default=None,
                   help="output dir (default: <repo>/site/dist)")
    b.set_defaults(func=cmd_build)
    sub.add_parser("deploy", help="deploy the built site (via ihale.sitegen.deploy)").set_defaults(func=cmd_deploy)

    r = sub.add_parser("run", help="daily job: fetch, parse, store, flag, export, build, deploy")
    r.add_argument("--date", type=parse_day, default=None, help=day_help + " (default: today, Europe/Istanbul)")
    r.add_argument("--types", nargs="+", default=["mal"], type=str, help="e.g. mal  or  mal,hizmet")
    r.add_argument("--no-deploy", action="store_true")
    r.set_defaults(func=cmd_run)

    bf = sub.add_parser("backfill", help="load the last N days of history (sequential, rate limited)")
    bf.add_argument("--days", type=int, required=True)
    bf.add_argument("--types", nargs="+", default=["mal"], type=str)
    bf.add_argument("--max-requests", type=int, default=None,
                    help=f"raise the per-run EKAP request cap (default {ekap.MAX_REQUESTS_PER_RUN})")
    bf.set_defaults(func=cmd_backfill)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "types"):
        try:
            args.types = parse_types(args.types)
        except argparse.ArgumentTypeError as e:
            parser.error(str(e))
    if getattr(args, "days", 1) < 1:
        parser.error("--days must be >= 1")
    return args.func(args)
