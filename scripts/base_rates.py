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

from ihale.flags import BUGUN_CUTOFF, PART_CODES, compute_flags_full
from ihale.store import Store

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:5.1f}%" if d else "    - "


def table(title: str, groups: dict[str, list]) -> None:
    print(f"\n{title}")
    print(f"  {'group':<28}{'records':>8}  {'tek':>7}  {'bedel>=.97':>10}  {'repeat':>7}  {'score>=3':>8}")
    for k, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        n = len(rows)
        print(f"  {k[:27]:<28}{n:>8}  {pct(sum(r['tek'] for r in rows), n)}  "
              f"{pct(sum(r['bedel'] for r in rows), n):>10}  {pct(sum(r['rep'] for r in rows), n)}  "
              f"{pct(sum(r['score'] >= BUGUN_CUTOFF for r in rows), n):>8}")


def _quantiles(vals: list[float]) -> str:
    if not vals:
        return "n=0"
    v = sorted(vals)
    q = lambda p: v[min(len(v) - 1, int(p * (len(v) - 1) + 0.5))]  # noqa: E731
    return (f"n={len(v):<6} mean={sum(v) / len(v):8.3f}  p10={q(.1):8.3f}  p50={q(.5):8.3f}  "
            f"p90={q(.9):8.3f}  max={v[-1]:8.3f}")


def part_rate_tables(part_rates: dict, rows: list[dict]) -> None:
    """Each score part's base rate p per usul_turu (what the rarity weights come from), and the share of records
    over the Bugün cut-off per usul_turu."""
    short = {"tek_teklif": "tek", "diger_teklifler_elendi": "diğer", "bedel_orani": "bedel",
             "tekrarlayan_eslesik": "tekrar", "idare_orani": "idare"}
    print(f"\nPart base rates p by <type>/<usul group> (ln(1/p) points; groups with n < 100 use <type>/hepsi)")
    print(f"  {'group':<20}{'n':>7}  " + "  ".join(f"{short[c]:>7}" for c in PART_CODES)
          + f"  {'tek share*':>10}  {'bedel med.':>11}  {'score>=' + str(BUGUN_CUTOFF):>9}")
    by_group: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_group[r["usul_turu"]].append(r)
        by_group[f"{r['type']}/hepsi"].append(r)
    for g in sorted(part_rates, key=lambda k: (k.split('/')[0], not k.endswith('/hepsi'), -part_rates[k]["n"])):
        rs = by_group.get(g, [])
        over = pct(sum(1 for r in rs if r["score"] >= BUGUN_CUTOFF), len(rs)) if rs else "    - "
        direct = pct(sum(r["tek_teklif"] for r in rs), len(rs)) if rs else "    - "
        med = part_rates[g].get("bedel_median_try")
        print(f"  {g:<20}{part_rates[g]['n']:>7}  " + "  ".join(f"{part_rates[g][c]:>7.4f}" for c in PART_CODES)
              + f"  {direct:>10}  {('%.0f' % med) if med else '-':>11}  {over:>9}")
    print("  (* direct share of tek_teklif flags among the rows shown; p for tek should match it when no --date is set)")


def indicator_tables(rows: list[dict]) -> None:
    """Distribution of each §4.2 indicator, overall and by usul_turu and section (not yet in the score)."""
    numeric = ("elenen_orani", "karar_suresi_gun", "yuklenici_payi")
    for key, title in (("usul_turu", "usul_turu"), ("section", "section")):
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            groups["(hepsi)"].append(r)
            groups[f"{r['type']}/{r['ind'].get('usul_turu') or '(bilinmiyor)'}" if key == "usul_turu"
                   else f"{r['type']}/{r['section']}"].append(r)
        print(f"\nIndicators by {title}")
        for g, rs in sorted(groups.items(), key=lambda kv: (kv[0] != "(hepsi)", -len(kv[1]))):
            print(f"  [{g}]  records={len(rs)}  acik_olmayan={pct(sum(1 for r in rs if r['ind'].get('acik_olmayan')), len(rs))}")
            for name in numeric:
                vals = [r["ind"][name] for r in rs if r["ind"].get(name) is not None]
                print(f"    {name:<18}{_quantiles(vals)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", type=date.fromisoformat, help="only report records of this bulletin date")
    ap.add_argument("--db", type=Path, help="database path (default: the configured data dir)")
    args = ap.parse_args(argv)

    store = Store(args.db)
    stored = store.all_records()
    res, part_rates = compute_flags_full(stored)
    rows = []
    for s in stored:
        r, f = s.record, res[s.id]
        if args.date and r.bulletin_date != args.date:
            continue
        have = {x["code"] for x in f.flags}
        rows.append({
            "date": r.bulletin_date, "type": r.bulletin_type, "ikn": r.ikn, "usul": r.ihale_usulu or "(boş)", "section": r.section,
            "tek": bool(have & {"tek_teklif", "diger_teklifler_elendi"}),
            "tek_teklif": "tek_teklif" in have, "diger": "diger_teklifler_elendi" in have,
            "ind": f.indicators or {}, "bedel": "bedel_orani" in have,
            "rep": "tekrarlayan_yuklenici" in have, "score": f.score,
            "unread": bool(f.unreadable), "parts": tuple(p["code"] for p in f.score_parts),
            "usul_turu": f.usul_group or "(bilinmiyor)"})
    if not rows:
        print("no records stored")
        return 0

    days = sorted({r["date"] for r in rows})
    n = len(rows)
    print(f"{n} records, {len(days)} bulletin day(s): {days[0]} .. {days[-1]}")
    print(f"tek geçerli teklif   {pct(sum(r['tek'] for r in rows), n)}  (either of the two below)")
    print(f"  tek teklif         {pct(sum(r['tek_teklif'] for r in rows), n)}")
    print(f"  diğerleri elendi   {pct(sum(r['diger'] for r in rows), n)}")
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
          f"score>={BUGUN_CUTOFF} {pct(sum(t['score'] >= BUGUN_CUTOFF for t in tenders.values()), tn)}")

    by_type, by_usul, by_section = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        by_type[r["type"]].append(r)
        by_usul[r["usul"]].append(r)
        by_section[r["section"]].append(r)
    table("By type", by_type)
    table("By usul", by_usul)
    table("By section", by_section)

    part_rate_tables(part_rates, rows)
    indicator_tables(rows)

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
          f"{sum(1 for r in rows if 'tekrarlayan_eslesik' in r['parts'])} of them are paired with another scored part")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
