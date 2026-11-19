"""Evaluate the sonuç parser (--type mal|hizmet|yapim) on the full local PDF against the hand labels.

    .venv\\Scripts\\python.exe scripts\\eval_parser.py [--labels PATH] [--pdf PATH] [--show N]

Comparison rules (SPEC §5): text compares after whitespace normalization only (no case
folding); money compares as exact kuruş + currency; a field is "correct" when the parser
value equals the label, and "correct and confident" when additionally confidence >= 0.9.
Records are matched on (section, seq). The labels are never modified.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
from decimal import Decimal
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ihale import config  # noqa: E402
from ihale.model import CONFIDENT, CORE_FIELDS, Money  # noqa: E402
from ihale.parse import parse_bulletin_read  # noqa: E402

DEFAULT_LABELS = ROOT / "tests" / "labels" / "mal_2026-11-18.json"
BULLETIN_DATE = date(2026, 11, 18)
MONEY_FIELDS = {"sozlesme_bedeli", "yaklasik_maliyet", "esas_kisim_yaklasik_maliyet"}
INT_FIELDS = {"gecerli_teklif", "toplam_teklif"}
DATE_FIELDS = {"ihale_tarihi", "sozlesme_tarihi"}


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


_NUM = r"(\d{1,3}(?:\.\d{3})*,\d{2})"


def _money_from_label(v):
    """Accept 'N,NN CUR' strings or {'amount'|'kurus', 'currency', 'alt'?} dicts.

    Returns (kurus, currency, alt) with alt None or (kurus, currency); exact decimal math.
    """
    if v is None:
        return None
    if isinstance(v, dict):
        if "kurus" in v:
            k = int(v["kurus"])
        elif "amount" in v:
            k = int((Decimal(str(v["amount"])) * 100).to_integral_exact())
        else:
            return ("?", repr(v), None)
        alt = _money_from_label(v["alt"]) if v.get("alt") else None
        return (k, v.get("currency"), (alt[0], alt[1]) if alt else None)
    m = re.match(rf"^\s*{_NUM}\s*([A-Za-z]{{2,4}})", str(v))
    if m:
        return (int(m.group(1).replace(".", "").replace(",", "")), m.group(2), None)
    return ("?", str(v), None)


def norm_label(field: str, v):
    if v is None:
        return None
    if field in MONEY_FIELDS:
        return _money_from_label(v)
    if field in INT_FIELDS:
        return int(v)
    if field in DATE_FIELDS:
        return str(v)
    return _ws(str(v))


def norm_parsed(field: str, v):
    if v is None:
        return None
    if isinstance(v, Money):
        return (v.kurus, v.currency, (v.alt.kurus, v.alt.currency) if v.alt else None)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        return _ws(v)
    return v


def load_labels(path: Path) -> dict[tuple[str, int], dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("records", "labels", "items"):
            if key in data:
                data = data[key]
                break
    out = {}
    for item in data:
        fields = item.get("fields", item)
        out[(item["section"], int(item["seq"]))] = {**fields, **{k: item[k] for k in item if k not in fields}}
    return out


def raw_ihalent_table(read, recs, labels) -> None:
    """ihalent's own Award per notice (no adapter fixes): what the library alone gives."""
    from ihalent.bulletin import award_from_notice

    rejected = {x.position for x in read.rejected}
    notices = iter(read.notices)
    awards = {}
    for pos, r in enumerate(recs, start=1):
        if pos in rejected:
            continue
        awards[(r.section, r.seq)] = award_from_notice(next(notices))

    def try_(v):
        return None if v is None else (round(v * 100), "TRY")

    getters = {
        "ikn": lambda a: a.ikn,
        "idare": lambda a: a.authority and _ws(a.authority),
        "yuklenici": lambda a: a.winner and _ws(a.winner),
        "sozlesme_bedeli": lambda a: try_(a.contract_try),
        "yaklasik_maliyet": lambda a: try_(a.estimate_try),
        "gecerli_teklif": lambda a: a.valid_bid_count,
    }
    print("\nihalent raw (Award per notice, TRY only; no adapter, no confidence):")
    for f, g in getters.items():
        n = ok = 0
        bad = []
        for key, lab in labels.items():
            a = awards.get(key)
            if a is None or f not in lab:
                continue
            exp = norm_label(f, lab[f])
            if f in MONEY_FIELDS and exp is not None:
                exp = (exp[0], exp[1])  # Award has no alt figure
            n += 1
            got = g(a)
            if got == exp:
                ok += 1
            else:
                bad.append((key, exp, got))
        print(f"  {f:18s} {n:3d} {100*ok/max(n,1):6.1f}%  {bad[:4]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=("mal", "hizmet", "yapim"), default="mal")
    ap.add_argument("--labels", type=Path, default=None)
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--show", type=int, default=60, help="max mismatches to print")
    args = ap.parse_args()

    btype = args.type
    labels_path = args.labels or ROOT / "tests" / "labels" / f"{btype}_2026-11-18.json"
    pdf = args.pdf or config.bulletins_dir() / "2026-11-18" / f"BULTEN_18112026_{btype.upper()}_SONUC.pdf"
    t0 = time.time()
    recs, read = parse_bulletin_read(pdf, BULLETIN_DATE, btype)
    dt = time.time() - t0
    print(f"parsed {pdf.name}: {len(recs)} records, {len({r.ikn for r in recs})} distinct ikn, {dt:.1f}s")

    # ------------------------------------------------- ihalent's own evidence
    print(f"ihalent: {len(read.notices)} notices read, {len(read.rejected)} rejected, "
          f"ToC lists {len(read.toc_ikns)}, missing {len(read.missing)}, unlisted {len(read.unlisted)}, "
          f"complete={read.complete}")
    for x in read.rejected[:10]:
        print(f"  rejected #{x.position} p.{x.page}: {x.reason[:100]}")

    # ---------------------------------------------------------------- sanity
    n_all_conf = sum(all(r.confident(f) for f in CORE_FIELDS) for r in recs)
    print(f"records with every core field confident: {n_all_conf}/{len(recs)} ({100*n_all_conf/len(recs):.1f}%)")
    for f in CORE_FIELDS:
        bad = sum(1 for r in recs if not r.confident(f))
        print(f"  not confident: {f:18s} {bad}")
    by = collections.defaultdict(list)
    for r in recs:
        by[r.ikn].append(r)
    checked = over = 0
    odd = []
    for ikn, rs in by.items():
        est = next((r.yaklasik_maliyet for r in rs if r.yaklasik_maliyet), None)
        bed = [r.sozlesme_bedeli for r in rs]
        if est is None or any(b is None for b in bed) or {b.currency for b in bed} != {est.currency}:
            continue
        # dedupe by (yuklenici, bedel) as the contract does
        seen = {(r.yuklenici, r.sozlesme_bedeli.kurus): r.sozlesme_bedeli.kurus for r in rs}
        ratio = sum(seen.values()) / est.kurus
        checked += 1
        over += ratio > 1.0
        if ratio > 1.2 or ratio < 0.005:
            odd.append((ikn, len(rs), round(ratio, 3)))
    print(f"per-ikn sum(bedel)/yaklasik_maliyet (same currency, deduped): {checked} ikns, {over} above 1.0, "
          f"{len(odd)} outside [0.005, 1.2]: {odd[:8]}")
    warn = collections.Counter(w.split(":")[0][:50] for r in recs for w in r.warnings)
    print(f"warnings: {sum(warn.values())} {warn.most_common(6)}")

    # --------------------------------------------------------------- labels
    if not labels_path.exists():
        print(f"\nno labels at {labels_path}; accuracy not computed")
        return 0
    labels = load_labels(labels_path)
    by_key = {(r.section, r.seq): r for r in recs}
    stats = {f: collections.Counter() for f in CORE_FIELDS}
    mism = []
    missing = [k for k in labels if k not in by_key]
    for key, lab in sorted(labels.items()):
        r = by_key.get(key)
        if r is None:
            continue
        for f in CORE_FIELDS:
            if f not in lab:
                continue
            exp = norm_label(f, lab[f])
            got = norm_parsed(f, getattr(r, f))
            ok = exp == got
            conf = r.confidence.get(f, 0.0) >= CONFIDENT
            s = stats[f]
            s["n"] += 1
            s["correct"] += ok
            if ok and conf:
                s["conf_ok"] += 1
            if not ok or not conf:
                mism.append((key, r.page_start, f, exp, got, r.confidence.get(f), ok))
    print(f"\nlabels: {len(labels)} (unmatched labels: {len(missing)} {missing[:5]})")
    print(f"{'field':20s} {'n':>5s} {'correct':>9s} {'correct+confident':>19s}")
    worst = 1.0
    for f in CORE_FIELDS:
        s = stats[f]
        if not s["n"]:
            continue
        a, b = s["correct"] / s["n"], s["conf_ok"] / s["n"]
        worst = min(worst, b)
        print(f"{f:20s} {s['n']:5d} {100*a:8.1f}% {100*b:18.1f}%")
    raw_ihalent_table(read, recs, labels)
    print(f"\nmismatches / unconfident ({len(mism)}):")
    for key, page, f, exp, got, conf, ok in mism[: args.show]:
        why = "WRONG" if not ok else "unconfident"
        print(f"  {key[0]}-{key[1]} p.{page} {f}: {why} label={exp!r} parsed={got!r} conf={conf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
