"""Print the measured base rates from the local DB (docs/data-contract.md §4.1).

Usage:  python scripts/base_rates.py [--date YYYY-MM-DD] [--db PATH]

Flags are computed fresh in memory from the stored records (the same code as `ihale flag`), so this works even
if `flag` has not been run. Rates are per record unless marked "per ikn" (a kısmi tender counts once).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from ihale.flags import compute_flags
from ihale.store import Store

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:5.1f}%" if d else "    - "


def table(title: str, groups: dict[str, list]) -> None:
    print(f"\n{title}")
    print(f"  {'group':<28}{'records':>8}  {'tek':>7}  {'bedel>=.97':>10}  {'repeat':>7}  {'score>=2':>8}")
    for k, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        n = len(rows)
        print(f"  {k[:27]:<28}{n:>8}  {pct(sum(r['tek'] for r in rows), n)}  "
              f"{pct(sum(r['bedel'] for r in rows), n):>10}  {pct(sum(r['rep'] for r in rows), n)}  "
              f"{pct(sum(r['score'] >= 2 for r in rows), n):>8}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", type=date.fromisoformat, help="only report records of this bulletin date")
    ap.add_argument("--db", type=Path, help="database path (default: the configured data dir)")
    args = ap.parse_args(argv)

    store = Store(args.db)
    stored = store.all_records()
    res = compute_flags(stored)
    rows = []
    for s in stored:
        r, f = s.record, res[s.id]
        if args.date and r.bulletin_date != args.date:
            continue
        have = {x["code"] for x in f.flags}
        rows.append({
            "date": r.bulletin_date, "ikn": r.ikn, "usul": r.ihale_usulu or "(boş)", "section": r.section,
            "tek": "tek_gecerli_teklif" in have, "bedel": "bedel_orani" in have,
            "rep": "tekrarlayan_yuklenici" in have, "score": f.score,
            "unread": bool(f.unreadable), "parts": tuple(f.score_parts)})
    if not rows:
        print("no records stored")
        return 0

    days = sorted({r["date"] for r in rows})
    n = len(rows)
    print(f"{n} records, {len(days)} bulletin day(s): {days[0]} .. {days[-1]}")
    print(f"tek geçerli teklif   {pct(sum(r['tek'] for r in rows), n)}")
    print(f"bedel >= 0.97        {pct(sum(r['bedel'] for r in rows), n)}")
    reps = [r for r in rows if r["rep"]]
    print(f"tekrarlayan          {pct(len(reps), n)}  ({len(reps)} records)")
    print(f"any unreadable       {pct(sum(r['unread'] for r in rows), n)}")

    tenders: dict = {}
    for r in rows:
        tenders.setdefault(r["ikn"] or id(r), r)
    tn = len(tenders)
    print(f"\nper ikn ({tn} tenders): tek {pct(sum(t['tek'] for t in tenders.values()), tn)}, "
          f"bedel>=.97 {pct(sum(t['bedel'] for t in tenders.values()), tn)}, "
          f"score>=2 {pct(sum(t['score'] >= 2 for t in tenders.values()), tn)}")

    by_usul, by_section = defaultdict(list), defaultdict(list)
    for r in rows:
        by_usul[r["usul"]].append(r)
        by_section[r["section"]].append(r)
    table("By usul", by_usul)
    table("By section", by_section)

    print("\nScore distribution (records)")
    dist = Counter(r["score"] for r in rows)
    cum = 0
    for sc in sorted(dist, reverse=True):
        cum += dist[sc]
        print(f"  score {sc}: {dist[sc]:>6}  ({pct(dist[sc], n)})   cumulative >= {sc}: {cum} ({pct(cum, n)})")
    print("\nScore parts")
    for part, c in Counter(p for r in rows for p in r["parts"]).most_common():
        print(f"  {part:<24}{c:>6}  ({pct(c, n)})")
    print(f"\nRepeat pairs: {len(reps)} records flagged tekrarlayan; "
          f"{sum(1 for r in reps if r['tek'] or r['bedel'])} of them also carry tek/bedel (scored +2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
