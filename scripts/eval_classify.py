"""Score the idare classifiers against the independent hand labels (SPEC §11 offline A/B test).

Usage:  python scripts/eval_classify.py [--labels tests/labels/idare_types.jsonl] [--table data/idare_table.jsonl]

For `keywords`, `table`, `hybrid` and `table_first` it reports, over the labeled idares:
  * accuracy per field (turu, il) over ALL labeled rows (an implementation with no answer counts as wrong) and over
    the rows it covers; coverage = share of rows with an answer;
  * a confusion table for turu (labeled → predicted), compact: only the off-diagonal cells;
  * self-consistency of the table if it holds two runs (turu_run1/turu_run2, il_run1/il_run2).
The label file is made by an independent labeler and is never edited here.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from ihale import classify
from ihale.keys import normalize_key

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:5.1f}%" if d else "    - "


def evaluate(labels: list[dict], impl: str) -> dict:
    """Per-implementation numbers; pure, used by the tests."""
    n = len(labels)
    covered = turu_ok = il_ok = turu_ok_cov = il_ok_cov = 0
    confusion: Counter = Counter()
    wrong: list[dict] = []
    for row in labels:
        pred = classify.classify(row["idare"], impl)
        has = pred.turu is not None
        t_ok = has and pred.turu == row["turu"]
        i_ok = has and pred.il == row.get("il")
        covered += has
        turu_ok += t_ok
        il_ok += i_ok
        turu_ok_cov += t_ok
        il_ok_cov += i_ok
        confusion[(row["turu"], pred.turu or "(yok)")] += 1
        if has and not (t_ok and i_ok):
            wrong.append({"idare": row["idare"], "label": (row["turu"], row.get("il")), "pred": (pred.turu, pred.il),
                          "source": pred.source})
    return {"n": n, "covered": covered, "turu_correct": turu_ok, "il_correct": il_ok,
            "turu_correct_covered": turu_ok_cov, "il_correct_covered": il_ok_cov,
            "confusion": confusion, "wrong": wrong}


def self_consistency(table_rows: list[dict]) -> dict | None:
    two = [r for r in table_rows if "turu_run1" in r and "turu_run2" in r]
    if not two:
        return None
    out = {"rows": len(two), "turu_agree": sum(r["turu_run1"] == r["turu_run2"] for r in two)}
    il = [r for r in two if "il_run1" in r and "il_run2" in r]
    out["il_rows"] = len(il)
    out["il_agree"] = sum(r["il_run1"] == r["il_run2"] for r in il)
    return out


def report(labels: list[dict], table_rows: list[dict], out=print) -> None:
    n = len(labels)
    out(f"{n} labeled idares; table rows: {len(table_rows)}")
    out(f"\n{'implementation':<10} {'coverage':>9} {'turu acc':>9} {'turu|cov':>9} {'il acc':>8} {'il|cov':>8}")
    results = {}
    for impl in classify.IMPLEMENTATIONS:
        r = results[impl] = evaluate(labels, impl)
        out(f"{impl:<10} {pct(r['covered'], n):>9} {pct(r['turu_correct'], n):>9} "
            f"{pct(r['turu_correct_covered'], r['covered']):>9} {pct(r['il_correct'], n):>8} "
            f"{pct(r['il_correct_covered'], r['covered']):>8}")
    for impl, r in results.items():
        off = sorted(((c, k) for k, c in r["confusion"].items() if k[0] != k[1]), reverse=True)
        out(f"\nConfusion (turu), {impl}: labeled → predicted, off-diagonal ({sum(c for c, _ in off)} of {n})")
        for c, (lab, pred) in off[:25]:
            out(f"  {c:>4}  {lab:<24} → {pred}")
        if not off:
            out("  (none)")
    sc = self_consistency(table_rows)
    out("\nTable self-consistency:")
    if sc is None:
        out("  no turu_run1/turu_run2 columns in the table file")
    else:
        out(f"  turu: {sc['turu_agree']}/{sc['rows']} agree ({pct(sc['turu_agree'], sc['rows'])})")
        if sc["il_rows"]:
            out(f"  il:   {sc['il_agree']}/{sc['il_rows']} agree ({pct(sc['il_agree'], sc['il_rows'])})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--labels", type=Path, default=classify.repo_root() / "tests" / "labels" / "idare_types.jsonl")
    ap.add_argument("--table", type=Path, default=None, help="default: data/idare_table.jsonl (or $IHALE_IDARE_TABLE)")
    args = ap.parse_args(argv)
    if args.table:
        os.environ[classify.TABLE_ENV] = str(args.table)
    if not args.labels.exists():
        print(f"no label file at {args.labels}", file=sys.stderr)
        return 2
    labels = read_jsonl(args.labels)
    table_path = classify.table_path()
    table_rows = read_jsonl(table_path) if table_path.exists() else []
    report(labels, table_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
