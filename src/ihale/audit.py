"""M5-audit core: independent recompute of every shown flag number, straight from ihale.db rows.

Deliberately does NOT call ihale.flags (no compute_flags_full, no helpers from it): it re-derives each figure from
the record's own columns and the documented rule (SPEC §Flags, PLAN fixes), then compares with what is stored and
shown. Only the key normalizer and the confidence threshold are shared, since they define identity, not the rule.

Run by the daily job after flagging (pipeline.audit_step): any mismatch stops the run before export/deploy
(exit 8, AUDIT-FAILED-<date>.txt). CLI: `ihale audit [--db PATH] [--json OUT]`, or scripts/audit_flags.py.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from .keys import normalize_key            # identity, not a rule
from .model import CONFIDENT

RATIO_CUT = 0.97          # bedel_orani fires at total/estimate >= 0.97
LARGE = 1.5               # above: shown with a check-the-source note, no points (spec owner 2026-11-27)
KALEM_MAX, KALEM_BIDS = 0.30, 4
REPEAT_MIN, REPEAT_DAYS = 3, 365


def money(row, base):
    k = row[f"{base}_kurus"]
    return None if k is None else (k, row[f"{base}_cur"])


class Rec:
    def __init__(self, row):
        self.id = row["id"]
        self.day = date.fromisoformat(row["bulletin_date"])
        self.type = row["bulletin_type"]
        self.conf = json.loads(row["confidence"] or "{}")
        self.ikn, self.idare, self.yuk = row["ikn"], row["idare"], row["yuklenici"]
        self.ym = money(row, "yaklasik_maliyet")
        self.esas = money(row, "esas_kisim_yaklasik_maliyet")
        self.bedel = money(row, "sozlesme_bedeli")
        self.toplam, self.gecerli = row["toplam_teklif"], row["gecerli_teklif"]
        self.usul = row["ihale_usulu"]
        self.flags = json.loads(row["flags"] or "[]")
        self.parts = json.loads(row["score_parts"] or "[]")
        self.ind = json.loads(row["indicators"] or "{}")
        self.score = row["score"] or 0.0

    def ok(self, name):
        return getattr(self, {"yaklasik_maliyet": "ym", "esas_kisim_yaklasik_maliyet": "esas",
                              "sozlesme_bedeli": "bedel", "toplam_teklif": "toplam", "gecerli_teklif": "gecerli",
                              "yuklenici": "yuk"}.get(name, name)) is not None and self.conf.get(name, 0) >= CONFIDENT

    def codes(self):
        return {f["code"] for f in self.flags}

    def part_codes(self):
        return {p["code"] if isinstance(p, dict) else p for p in self.parts}


def load(db: Path) -> list[Rec]:
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return [Rec(r) for r in c.execute("SELECT * FROM records ORDER BY id")]


def expected_ratio(r: Rec, by_ikn: dict) -> tuple[float | None, str, int]:
    """(ratio, why-not, number of contracts summed). Rule: estimate = esas-kısım YM if confident else YM if confident.
    A notice's own esas that differs from YM = the lots this contract covers -> own bedel. Otherwise the İKN's
    deduped contracts (ikn, yüklenici key, bedel) summed. Any doubtful/other-currency bedel -> no ratio. Kalem shape
    (esas absent or = YM, >= 4 bids, sum < .30) -> not comparable."""
    if r.ok("esas_kisim_yaklasik_maliyet"):
        est, own = r.esas, not (r.ok("yaklasik_maliyet") and r.ym == r.esas)
    elif r.ok("yaklasik_maliyet"):
        # rule B: notices of one İKN printing different YMs -> each YM is that notice's own
        yms = {m.ym for m in by_ikn[r.ikn] if m.ok("yaklasik_maliyet")} if r.ok("ikn") else set()
        est, own = r.ym, len(yms) >= 2
    else:
        return None, "no estimate", 0
    if est[0] <= 0:
        return None, "zero estimate", 0
    if own or not r.ok("ikn"):
        members = [r]
    else:
        seen = {}
        for m in by_ikn[r.ikn]:
            b = m.bedel
            seen.setdefault((normalize_key(m.yuk), b[0] if b else None, b[1] if b else None), m)
        members = list(seen.values())
    if any(not m.ok("sozlesme_bedeli") for m in members):
        return None, "bedel unread", len(members)
    if any(m.bedel[1] != est[1] for m in members):
        return None, "currency", len(members)
    if any(m.bedel[0] <= 0 for m in members):
        return None, "zero bedel", len(members)
    v = sum(m.bedel[0] for m in members) / est[0]
    if (not own and v < KALEM_MAX and r.ok("toplam_teklif") and r.toplam >= KALEM_BIDS and r.ok("yaklasik_maliyet")
            and (r.esas is None or r.esas == r.ym)):
        return None, "kalem", len(members)
    return v, "", len(members)


def pct_from_text(text: str) -> float | None:
    m = re.search(r"\(%(\d+),(\d+)\)", text)          # over the estimate: (%110,0)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r"%(\d+)'", text)                     # %97'si
    return float(m.group(1)) if m else None


def audit(recs: list[Rec]) -> dict:
    by_ikn = defaultdict(list)
    for r in recs:
        if r.ok("ikn"):
            by_ikn[r.ikn].append(r)
    hist = defaultdict(list)
    for r in recs:
        if r.ok("ikn") and r.ok("idare") and r.ok("yuklenici"):
            ik, yk = normalize_key(r.idare), normalize_key(r.yuk)
            if ik and yk:
                hist[(ik, yk)].append((r.day, r.ikn))
    latest = max(r.day for r in recs)
    out = defaultdict(list)
    stats = Counter()
    for r in recs:
        shown = r.codes() | r.part_codes()
        # ---- tek_teklif / diger_teklifler_elendi
        counts = r.ok("toplam_teklif") and r.ok("gecerli_teklif")
        exp_tek = counts and r.toplam == 1
        exp_el = counts and r.toplam > 1 and r.gecerli == 1
        if exp_tek != ("tek_teklif" in r.codes()):
            out["tek_teklif"].append((r.id, f"expected {exp_tek}, toplam {r.toplam} geçerli {r.gecerli}"))
        if exp_el != ("diger_teklifler_elendi" in r.codes()):
            out["diger_teklifler_elendi"].append((r.id, f"expected {exp_el}, toplam {r.toplam} geçerli {r.gecerli}"))
        for f in r.flags:
            if f["code"] == "diger_teklifler_elendi" and (f["value"] != r.toplam or f"{r.toplam} teklif" not in f["text"]):
                out["diger_teklifler_elendi_number"].append((r.id, f"shown {f['value']} / {f['text']!r}, toplam {r.toplam}"))
        # ---- bedel_orani
        v, why, n = expected_ratio(r, by_ikn)
        fl = next((f for f in r.flags if f["code"] == "bedel_orani"), None)
        stored = r.ind.get("bedel_orani")
        if (v is None) != (stored is None) or (v is not None and abs(v - stored) > 1e-9):
            out["bedel_orani_value"].append((r.id, f"expected {v} ({why}), stored {stored}"))
        exp_flag = v is not None and v >= RATIO_CUT
        if exp_flag != (fl is not None):
            out["bedel_orani_flag"].append((r.id, f"expected flag {exp_flag}, ratio {v}"))
        if fl is not None and v is not None:
            p = pct_from_text(fl["text"])
            dec = len(re.search(r"\(%\d+,(\d+)\)", fl["text"]).group(1)) if v > 1 and "(%" in fl["text"] else 0
            want = int(v * 100 * 10 ** dec + 1e-9) / 10 ** dec if v > 1 else int(round(v * 100, 6))
            if p is None or abs(p - want) > 1e-9:
                out["bedel_orani_text"].append((r.id, f"text {fl['text']!r}, ratio {v:.4f}"))
            # typo (power of ten) or large (> 1.5): shown with a note, but no points
            doubtful = v > LARGE or any(abs(v / 10 ** k - 1) <= 0.01 + 1e-9 for k in range(-6, 7) if k)
            if doubtful and "bedel_orani" in r.part_codes():
                out["doubtful_ratio_scored"].append((r.id, f"ratio {v:.3f} earns points"))
            if (n > 1) != fl["text"].startswith("Bu ihalenin"):
                out["bedel_orani_text_scope"].append((r.id, f"{n} contracts summed, text {fl['text'][:40]!r}"))
        # ---- outliers that still reach flags/points (task 2)
        if v is not None and (v > 1.5 or v < 0.1) and ("bedel_orani" in shown):
            sc = (fl or {}).get("source_check") or "none"
            pts = "bedel_orani" in r.part_codes()
            out[f"outlier_flagged_check={sc}_points={pts}"].append((r.id, f"ratio {v:.3f}, n {n}, score {r.score}"))
        if v is not None and (v > 1.5 or v < 0.1):
            stats["ratio_outlier_any"] += 1
        if stored is not None and ((r.ym and r.ym[0] == 0) or (r.bedel and r.bedel[0] <= 0) or r.bedel is None):
            out["ratio_from_zero_or_missing"].append((r.id, f"ym {r.ym} bedel {r.bedel} ratio {stored}"))
        if why == "currency" and ("bedel_orani" in shown):
            out["currency_scored"].append((r.id, f"est {r.esas or r.ym} bedel {r.bedel}"))
        # ---- tekrarlayan_yuklenici
        exp_n = None
        if r.ok("ikn") and r.ok("idare") and r.ok("yuklenici"):
            ik, yk = normalize_key(r.idare), normalize_key(r.yuk)
            if ik and yk:
                lo = r.day - timedelta(days=REPEAT_DAYS)
                exp_n = len({i for d, i in hist[(ik, yk)] if lo <= d <= r.day})
        fr = next((f for f in r.flags if f["code"] == "tekrarlayan_yuklenici"), None)
        if (exp_n is not None and exp_n >= REPEAT_MIN) != (fr is not None):
            out["tekrarlayan_flag"].append((r.id, f"expected {exp_n}"))
        elif fr is not None and (fr["value"] != exp_n or f"{exp_n} sözleşme" not in fr["text"]):
            out["tekrarlayan_number"].append((r.id, f"shown {fr['value']}, expected {exp_n}"))
        # ---- bid counts (task 4)
        if counts and r.gecerli > r.toplam:
            out["gecerli_gt_toplam"].append((r.id, f"toplam {r.toplam} geçerli {r.gecerli}"))
        stats["records"] += 1
        stats["flagged_or_scored"] += bool(shown)
    # ---- repeat inflation through suffixed İKNs (task 3): 2025/739147-6 style
    base = lambda i: re.sub(r"-\d+$", "", i)
    for r in recs:
        fr = next((f for f in r.flags if f["code"] == "tekrarlayan_yuklenici"), None)
        if fr is None:
            continue
        ik, yk = normalize_key(r.idare), normalize_key(r.yuk)
        lo = r.day - timedelta(days=REPEAT_DAYS)
        ikns = {i for d, i in hist[(ik, yk)] if lo <= d <= r.day}
        bases = {base(i) for i in ikns}
        if len(bases) < len(ikns):
            out["repeat_suffix_ikn"].append((r.id, f"{len(ikns)} İKNs but {len(bases)} base İKNs; shown {fr['value']}"))
    # lots in an İKN vs tender-level bid count (task 4)
    for ikn, ms in by_ikn.items():
        winners = {normalize_key(m.yuk) for m in ms if m.ok("yuklenici")}
        tops = {m.toplam for m in ms if m.ok("toplam_teklif")}
        if len(winners) >= 2 and len(tops) == 1:          # one tender-level count printed on every lot
            t = next(iter(tops))
            stats["ikn_uniform_toplam_multiwinner"] += 1
            if t < len(winners):
                out["uniform_toplam_lt_winners"].append((ms[0].id, f"İKN {ikn}: {len(winners)} winners, toplam {t}"))
            for m in ms:
                if "tek_teklif" in m.codes():
                    out["tek_teklif_with_2plus_winners"].append((m.id, f"İKN {ikn}: {len(winners)} winners, toplam {t}"))
    return {"latest": latest.isoformat(), "stats": dict(stats), "findings": {k: v for k, v in out.items()}}


# findings that are lists for a human, never a mismatch (they never block the daily run)
INFO_PREFIXES = ("outlier", "uniform_toplam", "tek_teklif_with")


def mismatches(res: dict) -> dict:
    return {k: v for k, v in res["findings"].items() if not k.startswith(INFO_PREFIXES)}


def summary(res: dict, recs: list | None = None, limit: int = 3) -> str:
    byid = {r.id: r for r in recs or []}
    lines = [f"records {res['stats'].get('records', 0)}, flagged/scored {res['stats'].get('flagged_or_scored', 0)}, "
             f"latest {res['latest']}"]
    mm = mismatches(res)
    lines.append(f"mismatches: {sum(len(v) for v in mm.values())}")
    for k, v in sorted(res["findings"].items()):
        tag = "" if k in mm else " (info, never blocks)"
        lines.append(f"{k}: {len(v)}{tag}")
        for i, msg in v[:limit]:
            r = byid.get(i)
            where = f" {r.ikn} {r.day}" if r else ""
            lines.append(f"    id {i}{where}: {msg}")
    return "\n".join(lines)


def check(db: Path) -> tuple[int, str, dict]:
    """(number of mismatches, printable summary, raw result) for the given ihale.db."""
    recs = load(db)
    if not recs:
        return 0, "no records", {"findings": {}, "stats": {}, "latest": None}
    res = audit(recs)
    return sum(len(v) for v in mismatches(res).values()), summary(res, recs), res
