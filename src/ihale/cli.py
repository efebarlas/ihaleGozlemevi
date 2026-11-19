from __future__ import annotations

import argparse
import sys

from . import config, ekap


def cmd_fetch(args) -> int:
    day = ekap.parse_date(args.date)
    cache = config.data_dir() / "form-cache.html" if args.cache_form else None
    client = ekap.EkapClient(form_cache=cache)
    try:
        d = client.fetch(day, args.type, force=args.force)
    except ekap.BlockedError as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 3
    except ekap.NoBulletinError as e:
        print(f"NO BULLETIN: {e}", file=sys.stderr)
        return 4
    print(f"{d} ({client.requests_made} EKAP request(s))")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ihale", description="Ihale Gozlemevi pipeline")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="download an EKAP bulletin into the data dir")
    f.add_argument("--date", required=True, help="DD.MM.YYYY")
    f.add_argument("--type", default="mal", choices=sorted(ekap.TYPE_CODES))
    f.add_argument("--force", action="store_true", help="re-download even if cached")
    f.add_argument("--cache-form", action="store_true", help="dev: reuse a saved form page (skips the GET)")
    f.set_defaults(func=cmd_fetch)
    # Future subcommands (later milestones): parse, flag, export, build, run
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
