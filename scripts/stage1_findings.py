"""M6-share-1: numbers, intervals, charts and checks for the Stage 1 findings note (SPEC "Staged sharing").

Code only: the prose lives outside the repo. Everything is recomputed from research/history.db (current rules) and
written to <data>/share/stage1/: numbers.json, fig*.svg/png, checks.txt. Reproducible: fixed bootstrap seed.

    .venv/Scripts/python.exe -X utf8 scripts/stage1_findings.py [--reps 1000]

Main analysis: the seeded random sample days (backfill plan), 2016-01-01 .. 2025-09-30 (before the publication
change). Finding 4 alone uses 2024-01 .. 2026-09 (all history.db days) as a method note. Uncertainty: 90% bootstrap
intervals resampling sample days (cluster bootstrap; per-year figures resample that year's days).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ihale import config, history  # noqa: E402
from ihale.keys import normalize_key  # noqa: E402

MAIN_END = date(2025, 9, 30)
M4_START, M4_END = date(2024, 1, 1), date(2026, 9, 30)
CHANGE = date(2025, 10, 1)
TYPES = ("mal", "hizmet", "yapim")
TYPE_TR = {"mal": "Mal alımı", "hizmet": "Hizmet alımı", "yapim": "Yapım işi"}
BID_GROUPS = (("1", 1, 1), ("2-3", 2, 3), ("4+", 4, 10 ** 9))
BID_TR = {"1": "1 teklif", "2-3": "2–3 teklif", "4+": "4 ve üzeri teklif"}
USUL_CATS = ("acik", "belli", "pazarlik_21b", "pazarlik_diger", "pazarlik_bent_yok", "istisna", "diger")
USUL_TR = {"acik": "Açık ihale", "belli": "Belli istekliler arası", "pazarlik_21b": "Pazarlık (21/b)",
           "pazarlik_diger": "Diğer pazarlık (21/a, c, d, e, f)",
           "pazarlik_bent_yok": "Pazarlık (bent yazılmamış)", "istisna": "İstisna (4734 md. 3)",
           "diger": "Diğer / okunamadı"}
CORE = ("ikn", "idare", "yuklenici", "yaklasik_maliyet", "sozlesme_bedeli", "toplam_teklif", "gecerli_teklif", "ihale_usulu")
OKABE_ITO = ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#999999")
MARKERS = ("o", "s", "^", "D", "v", "P")
LINESTYLES = ("-", "--", "-.", ":", (0, (5, 1)), (0, (3, 1, 1, 1)))
VERDICT_WORDS = ("şüpheli", "yolsuzluk", "usulsüz", "skandal", "hırsız", "rüşvet", "kayırma", "milyarlarca", "kayıp")


def usul_cat(code: str | None, text: str | None = None) -> str:
    if code in (None, "diger") and (text or "").strip().lower().startswith("pazarlık"):
        return "pazarlik_bent_yok"          # 2016-2017 notices often print "Pazarlık" without the article
    if code is None or code == "diger":
        return "diger"
    if code == "acik":
        return "acik"
    if code == "belli_istekliler":
        return "belli"
    if code == "pazarlik_21b":
        return "pazarlik_21b"
    if code.startswith("pazarlik_"):
        return "pazarlik_diger"
    if code.startswith("istisna_"):
        return "istisna"
    return "diger"


def load(db: Path) -> list[dict]:
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    out = []
    for r in c.execute("SELECT * FROM records"):
        conf = json.loads(r["confidence"] or "{}")
        ind = json.loads(r["indicators"] or "{}")
        ok = lambda f: conf.get(f, 0) >= 0.9          # noqa: E731
        out.append(dict(
            day=date.fromisoformat(r["bulletin_date"]), type=r["bulletin_type"], ikn=r["ikn"] if ok("ikn") else None,
            id=r["id"], conf=conf, kisim_n=r["kisim_n"] or 1, usul=ind.get("usul_turu"), usul_text=r["ihale_usulu"],
            toplam=r["toplam_teklif"] if ok("toplam_teklif") else None,
            gecerli=r["gecerli_teklif"] if ok("gecerli_teklif") else None,
            ym=(r["yaklasik_maliyet_kurus"], r["yaklasik_maliyet_cur"]) if ok("yaklasik_maliyet") and r["yaklasik_maliyet_kurus"] is not None else None,
            esas=(r["esas_kisim_yaklasik_maliyet_kurus"], r["esas_kisim_yaklasik_maliyet_cur"]) if r["esas_kisim_yaklasik_maliyet_kurus"] is not None else None,
            bedel=(r["sozlesme_bedeli_kurus"], r["sozlesme_bedeli_cur"]) if ok("sozlesme_bedeli") and r["sozlesme_bedeli_kurus"] is not None else None,
            yk=normalize_key(r["yuklenici"]) if ok("yuklenici") and r["yuklenici"] else None,
            ratio=ind.get("bedel_orani"), check=ind.get("source_check"), kalem=bool(ind.get("bedel_orani_not_comparable")),
            warnings=len(json.loads(r["warnings"] or "[]"))))
    return out


# ------------------------------------------------------------------ bootstrap over days
def by_day(rows):
    d = defaultdict(list)
    for r in rows:
        d[r["day"]].append(r)
    return d


def boot(rows, stat, reps, rng):
    """(point, lo, hi) with a 90% percentile interval, resampling days with replacement."""
    days = by_day(rows)
    keys = sorted(days)
    point = stat(rows)
    if point is None or len(keys) < 2:
        return point, None, None
    vals = []
    for _ in range(reps):
        pick = rng.integers(0, len(keys), len(keys))
        v = stat([r for i in pick for r in days[keys[i]]])
        if v is not None:
            vals.append(v)
    if len(vals) < reps * 0.5:
        return point, None, None
    lo, hi = np.percentile(vals, [5, 95])
    return point, float(lo), float(hi)


def rnd(t, k=3):
    return [None if x is None else round(x, k) for x in t]


def median_of(f):
    def s(rows):
        v = [f(r) for r in rows]
        v = [x for x in v if x is not None]
        return float(np.median(v)) if len(v) >= 10 else None
    return s


def share_of(pred, base):
    def s(rows):
        b = [r for r in rows if base(r)]
        return sum(1 for r in b if pred(r)) / len(b) if len(b) >= 10 else None
    return s


def awards(rows):
    """One row per (type, İKN); a record without a confident İKN is its own award (first notice kept)."""
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: (r["day"], r["id"])):
        k = (r["type"], r["ikn"]) if r["ikn"] else ("rec", r["id"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


# ------------------------------------------------------------------ findings
def f1_rows(rows):
    """Single-lot açık tenders, estimate and price in TRY, ratio computable and not a doubtful value."""
    out = []
    for r in rows:
        if (r["usul"] == "acik" and r["kisim_n"] == 1 and r["ikn"] and r["toplam"] and r["ym"] and r["bedel"]
                and r["ym"][1] == "TRY" and r["bedel"][1] == "TRY" and r["ratio"] is not None and r["check"] is None
                and (r["esas"] is None or r["esas"] == r["ym"])):
            out.append(r)
    return out


def bid_group(n):
    return next(g for g, lo, hi in BID_GROUPS if lo <= n <= hi)


def finding1(main, reps, rng):
    rows = f1_rows(main)
    res = {"n_records": len(rows), "pooled": {}, "by_year": {}}
    for t in TYPES + ("hepsi",):
        sub = [r for r in rows if t == "hepsi" or r["type"] == t]
        res["pooled"][t] = {}
        for g, lo, hi in BID_GROUPS:
            gr = [r for r in sub if lo <= r["toplam"] <= hi]
            res["pooled"][t][g] = {"median": rnd(boot(gr, median_of(lambda r: r["ratio"]), reps, rng)), "n": len(gr)}
        for y in sorted({r["day"].year for r in sub}):
            ys = [r for r in sub if r["day"].year == y]
            res["by_year"].setdefault(t, {})[y] = {
                g: {"median": rnd(boot([r for r in ys if lo <= r["toplam"] <= hi], median_of(lambda r: r["ratio"]), reps, rng)),
                    "n": sum(1 for r in ys if lo <= r["toplam"] <= hi)} for g, lo, hi in BID_GROUPS}
    return res


def finding2(main, reps, rng):
    aw = [r for r in awards(main) if r["usul"] == "acik" and r["toplam"] is not None and r["gecerli"] is not None]
    stat = share_of(lambda r: r["toplam"] == 1, lambda r: True)
    res = {"n_awards": len(aw), "pooled": {}, "by_year": {}}
    for t in TYPES + ("hepsi",):
        sub = [r for r in aw if t == "hepsi" or r["type"] == t]
        res["pooled"][t] = {"share": rnd(boot(sub, stat, reps, rng)), "n": len(sub)}
        res["by_year"][t] = {y: {"share": rnd(boot([r for r in sub if r["day"].year == y], stat, reps, rng)),
                                 "n": sum(1 for r in sub if r["day"].year == y)}
                             for y in sorted({r["day"].year for r in sub})}
    return res


def finding3(main, reps, rng):
    res = {"n_records": len(main), "by_year": {}, "per_day_istisna": []}
    for y in sorted({r["day"].year for r in main}):
        ys = [r for r in main if r["day"].year == y]
        res["by_year"][y] = {c: rnd(boot(ys, share_of(lambda r, c=c: usul_cat(r["usul"], r["usul_text"]) == c, lambda r: True), reps, rng))
                             for c in USUL_CATS}
        res["by_year"][y]["n"] = len(ys)
    for d, rs in sorted(by_day(main).items()):
        res["per_day_istisna"].append({"day": d.isoformat(), "n": len(rs),
                                       "istisna": round(sum(usul_cat(r["usul"], r["usul_text"]) == "istisna" for r in rs) / len(rs), 4),
                                       "pazarlik_21b": round(sum(usul_cat(r["usul"], r["usul_text"]) == "pazarlik_21b" for r in rs) / len(rs), 4)})
    for c in ("istisna", "pazarlik_21b"):
        v = [x[c] for x in res["per_day_istisna"]]
        res[f"day_spread_{c}"] = {"min": round(min(v), 3), "p10": round(float(np.percentile(v, 10)), 3),
                                  "median": round(float(np.median(v)), 3), "p90": round(float(np.percentile(v, 90)), 3),
                                  "max": round(max(v), 3)}
    return res


def quarter(d):
    return f"{d.year}Ç{(d.month - 1) // 3 + 1}"


def uniform_count_ikns(rows):
    """İKNs with 2+ notices and 2+ distinct winners: (İKN key, day, all notices print one identical count pair)."""
    g = defaultdict(list)
    for r in rows:
        if r["ikn"]:
            g[(r["type"], r["ikn"])].append(r)
    out = []
    for k, ms in g.items():
        if len(ms) < 2 or len({m["yk"] for m in ms if m["yk"]}) < 2:
            continue
        pairs = {(m["toplam"], m["gecerli"]) for m in ms}
        if any(m["toplam"] is None for m in ms):
            continue
        out.append({"day": min(m["day"] for m in ms), "uniform": len(pairs) == 1})
    return out


def finding4(all_rows, reps, rng):
    rows = [r for r in all_rows if M4_START <= r["day"] <= M4_END]
    res = {"quarters": {}, "pre": {}, "post": {}}
    for q in sorted({quarter(r["day"]) for r in rows}, key=lambda s: (int(s[:4]), s[-1])):
        qs = [r for r in rows if quarter(r["day"]) == q]
        mal = [r for r in qs if r["type"] == "mal"]
        u = uniform_count_ikns(qs)
        res["quarters"][q] = {
            "days": len({r["day"] for r in qs}), "mal_records": len(mal),
            "kalem_share_mal": round(sum(r["kalem"] for r in mal) / len(mal), 4) if mal else None,
            "multi_winner_ikns": len(u),
            "uniform_count_share": round(sum(x["uniform"] for x in u) / len(u), 4) if len(u) >= 10 else None}
    for label, lo, hi in (("pre", M4_START, date(2025, 9, 30)), ("post", CHANGE, M4_END)):
        part = [r for r in rows if lo <= r["day"] <= hi]
        mal = [r for r in part if r["type"] == "mal"]
        res[label]["kalem_share_mal"] = rnd(boot(mal, share_of(lambda r: r["kalem"], lambda r: True), reps, rng), 4)
        # naive per-notice price ratio (own bedel / printed YM, every notice with both in TRY) vs the rule-based one
        naive = lambda r: (r["bedel"][0] / r["ym"][0] if r["ym"] and r["bedel"] and r["ym"][1] == r["bedel"][1] == "TRY"   # noqa: E731
                           and r["ym"][0] > 0 else None)
        res[label]["naive_per_notice_median_mal"] = rnd(boot(mal, median_of(naive), reps, rng))
        res[label]["rule_based_median_mal"] = rnd(boot(
            [r for r in mal if r["check"] is None], median_of(lambda r: r["ratio"]), reps, rng))

        def ushare(rs):
            u = uniform_count_ikns(rs)
            return sum(x["uniform"] for x in u) / len(u) if len(u) >= 10 else None
        res[label]["uniform_count_share"] = rnd(boot(part, ushare, reps, rng), 4)
        res[label]["days"] = len({r["day"] for r in part})
    return res


# ------------------------------------------------------------------ parse quality
def parse_quality(main):
    tab = {}
    for y in sorted({r["day"].year for r in main}):
        ys = [r for r in main if r["day"].year == y]
        n = len(ys)
        row = {"records": n, "days": len({r["day"] for r in ys})}
        for f in CORE:
            row[f] = round(100 * sum(r["conf"].get(f, 0) >= 0.9 for r in ys) / n, 1)
        row["any_warning"] = round(100 * sum(r["warnings"] > 0 for r in ys) / n, 1)
        tab[y] = row
    return tab


# ------------------------------------------------------------------ charts
def setup_mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none",
                         "axes.facecolor": "white", "figure.facecolor": "white", "axes.edgecolor": "#333333",
                         "axes.grid": True, "grid.color": "#dddddd", "grid.linewidth": 0.6,
                         "axes.spines.top": False, "axes.spines.right": False})
    return plt


def save(fig, out: Path, name: str):
    for ext in ("svg", "png"):
        fig.savefig(out / f"{name}.{ext}", dpi=160 if ext == "png" else None, bbox_inches="tight")


def pct(x, _=None):
    return f"%{x * 100:.0f}"


def chart1(plt, f1, out):
    from matplotlib.ticker import FuncFormatter
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.9), sharey=True)
    for ax, t in zip(axes, TYPES):
        by = f1["by_year"].get(t, {})
        years = sorted(by)
        for i, (g, _, _) in enumerate(BID_GROUPS):
            xs = [y for y in years if by[y][g]["median"][0] is not None]
            ys = [by[y][g]["median"][0] for y in xs]
            lo = [by[y][g]["median"][1] for y in xs]
            hi = [by[y][g]["median"][2] for y in xs]
            ax.plot(xs, ys, color=OKABE_ITO[i], marker=MARKERS[i], linestyle=LINESTYLES[i], label=BID_TR[g])
            xb = [x for x, l_ in zip(xs, lo) if l_ is not None]
            ax.fill_between(xb, [l_ for l_ in lo if l_ is not None], [h for h in hi if h is not None],
                            color=OKABE_ITO[i], alpha=0.12, linewidth=0)
        ax.set_title(TYPE_TR[t])
        ax.yaxis.set_major_formatter(FuncFormatter(pct))
        ax.set_xticks(years)
        ax.set_xticklabels([f"{y}*" if y == 2025 else str(y) for y in years], rotation=60)
    axes[0].set_ylabel("Sözleşme bedeli / yaklaşık maliyet (ortanca)")
    h, l_ = axes[0].get_legend_handles_labels()
    fig.legend(h, l_, loc="lower center", bbox_to_anchor=(0.5, -0.16), ncol=3, frameon=False)
    fig.suptitle("Tek kısımlı açık ihalelerde fiyat ve teklif sayısı (2016 – 2025 Eylül)", y=1.02)
    fig.text(0, -0.22, "Gölgeli alanlar: örnek günler yeniden örneklenerek hesaplanan %90 aralığı. "
                       "* 2025: Ocak–Eylül. Kaynak: EKAP sonuç ilanları bültenleri, örnek günler.", fontsize=8)
    save(fig, out, "sekil1-fiyat-teklif")
    plt.close(fig)


def chart2(plt, f2, out):
    from matplotlib.ticker import FuncFormatter
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, t in enumerate(TYPES):
        by = f2["by_year"][t]
        xs = [y for y in sorted(by) if by[y]["share"][0] is not None]
        ax.plot(xs, [by[y]["share"][0] for y in xs], color=OKABE_ITO[i], marker=MARKERS[i], linestyle=LINESTYLES[i],
                label=TYPE_TR[t])
        ok = [y for y in xs if by[y]["share"][1] is not None]
        ax.fill_between(ok, [by[y]["share"][1] for y in ok], [by[y]["share"][2] for y in ok], color=OKABE_ITO[i],
                        alpha=0.12, linewidth=0)
    ax.yaxis.set_major_formatter(FuncFormatter(pct))
    years = sorted({y for t in TYPES for y in f2["by_year"][t]})
    ax.set_xticks(years)
    ax.set_xticklabels([f"{y}*" if y == 2025 else str(y) for y in years], rotation=60)
    ax.set_ylabel("Tek teklif verilen ihalelerin payı")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False)
    ax.set_title("Açık ihalelerde tek teklif payı (2016 – 2025 Eylül)")
    fig.text(0, -0.08, "Birim: ihale (İKN). Gölgeli alanlar: %90 aralığı. * 2025: Ocak–Eylül. "
                       "Kaynak: EKAP sonuç ilanları bültenleri, örnek günler.", fontsize=8)
    save(fig, out, "sekil2-tek-teklif")
    plt.close(fig)


def chart3(plt, f3, out):
    from matplotlib.ticker import FuncFormatter
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [1.1, 1]})
    years = sorted(f3["by_year"])
    bottom = np.zeros(len(years))
    hatches = ("", "//", "..", "xx", "++", "\\\\", "")
    for i, c in enumerate(USUL_CATS):
        v = np.array([f3["by_year"][y][c][0] or 0 for y in years])
        a1.bar([str(y) if y != 2025 else "2025*" for y in years], v, bottom=bottom, color=OKABE_ITO[i],
               hatch=hatches[i], edgecolor="white", linewidth=0.5, label=USUL_TR[c])
        bottom += v
    a1.yaxis.set_major_formatter(FuncFormatter(pct))
    a1.set_ylabel("Kayıtların payı")
    a1.tick_params(axis="x", rotation=60)
    a1.set_title("Usul dağılımı (yıllık)")
    a1.legend(fontsize=7.5, frameon=False, loc="upper left", bbox_to_anchor=(0, -0.22), ncol=2)
    pts = f3["per_day_istisna"]
    xs = [date.fromisoformat(p["day"]) for p in pts]
    a2.scatter(xs, [p["istisna"] for p in pts], s=14, color=OKABE_ITO[5], marker="o", label="İstisna")
    a2.scatter(xs, [p["pazarlik_21b"] for p in pts], s=14, color=OKABE_ITO[2], marker="^", label="Pazarlık (21/b)")
    a2.yaxis.set_major_formatter(FuncFormatter(pct))
    a2.set_ylabel("O günün kayıtları içindeki pay")
    a2.set_title("Günden güne değişim (her nokta bir örnek gün)")
    a2.legend(frameon=False)
    fig.text(0, -0.36, "* 2025: Ocak–Eylül. 2016–2017 ilanlarında pazarlık çoğu kez bent yazılmadan geçer.  Kaynak: EKAP sonuç ilanları bültenleri, örnek günler; mal, hizmet ve yapım birlikte.",
             fontsize=8)
    save(fig, out, "sekil3-usul")
    plt.close(fig)


def chart4(plt, f4, out):
    from matplotlib.ticker import FuncFormatter
    qs = list(f4["quarters"])
    fig, ax = plt.subplots(figsize=(9, 4))
    k = [f4["quarters"][q]["kalem_share_mal"] for q in qs]
    u = [f4["quarters"][q]["uniform_count_share"] for q in qs]
    ax.plot(qs, k, color=OKABE_ITO[0], marker="o", label="Mal kayıtları: yüklenici başına ayrı ilan (kalem bazlı) payı")
    ax.plot([q for q, x in zip(qs, u) if x is not None], [x for x in u if x is not None], color=OKABE_ITO[1], marker="s",
            linestyle="--", label="Çok yüklenicili ihaleler: her ilanda aynı teklif sayısı payı")
    ax.axvline(qs.index("2025Ç4") - 0.5, color="#555555", linewidth=0.8, linestyle=":")
    ax.text(qs.index("2025Ç4") - 0.4, 0.95, "2025 Ekim", fontsize=8, color="#555555", transform=ax.get_xaxis_transform())
    ax.yaxis.set_major_formatter(FuncFormatter(pct))
    ax.set_ylim(0, 1)
    ax.tick_params(axis="x", rotation=60)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title("2025 sonbaharındaki yayım değişikliği (çeyrek bazında)")
    fig.text(0, -0.12, "Kaynak: EKAP sonuç ilanları bültenleri; 2024–2025 Eylül örnek günler, sonrası tüm yüklenen günler.",
             fontsize=8)
    save(fig, out, "sekil4-yayim-degisikligi")
    plt.close(fig)


# ------------------------------------------------------------------ checks
def name_checks(out: Path, quality: dict) -> str:
    texts = {}
    for p in sorted(out.glob("*.md")) + sorted(out.glob("*.svg")) + [out / "numbers.json"]:
        if p.exists():
            t = p.read_text(encoding="utf-8")
            if p.suffix == ".svg":
                t = " ".join(re.findall(r">([^<>]+)<", t))     # only the text nodes of the chart
            texts[p.name] = t
    norm = lambda s: re.sub(r"\s+", " ", (s or "").replace("İ", "i").replace("I", "ı").lower()).strip()  # noqa: E731
    docs = {k: norm(v) for k, v in texts.items()}
    names = set()
    for db in (history.db_path(), config.db_path()):
        if db.exists():
            c = sqlite3.connect(db)
            for col in ("idare", "yuklenici"):
                names |= {norm(x) for (x,) in c.execute(f"SELECT DISTINCT {col} FROM records") if x}
    names = {n for n in names if len(n) >= 8}       # shorter strings are not identifying and match common words
    lines = [f"Name check: {len(names):,} distinct idare and yüklenici names (history.db + ihale.db, >= 8 chars) "
             f"searched in {', '.join(texts)}."]
    hits = [(f, n) for f, d in docs.items() for n in names if n in d]
    lines.append(f"  name hits: {len(hits)}" + "".join(f"\n    {f}: [name of {len(n)} chars]" for f, n in hits[:20]))
    extra = ("dmo", "devlet malzeme ofisi")
    for w in extra + VERDICT_WORDS:
        h = [f for f, d in docs.items() if re.search(rf"\b{re.escape(w)}", d)]
        lines.append(f"  '{w}': {'none' if not h else ', '.join(h)}")
    lines.append("\nParse quality on the main sample days (% of records with the field read confidently; "
                 "any_warning = % of records with any parser warning):")
    cols = ["records", "days", *CORE, "any_warning"]
    lines.append("  year  " + "  ".join(c[:9].rjust(9) for c in cols))
    for y, row in quality.items():
        lines.append(f"  {y}  " + "  ".join(str(row[c]).rjust(9) for c in cols))
    return "\n".join(lines) + "\n"


def _int_years(d):
    """numbers.json keys years as strings; the charts want ints."""
    for k in ("by_year",):
        if k in d:
            if all(isinstance(v, dict) and all(str(x).isdigit() for x in v) for v in d[k].values()) and                     not all(str(x).isdigit() for x in d[k]):
                d[k] = {t: {int(y): v for y, v in yv.items()} for t, yv in d[k].items()}
            elif all(str(x).isdigit() for x in d[k]):
                d[k] = {int(y): v for y, v in d[k].items()}


def draw(res, out):
    plt = setup_mpl()
    chart1(plt, res["finding1_price_by_bids"], out)
    chart2(plt, res["finding2_single_bid_share"], out)
    chart3(plt, res["finding3_procedure_mix"], out)
    chart4(plt, res["finding4_publication_change"], out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261127)
    ap.add_argument("--checks-only", action="store_true", help="only rewrite checks.txt (after editing the md)")
    ap.add_argument("--charts-only", action="store_true", help="redraw the charts from numbers.json, then checks")
    a = ap.parse_args()
    out = config.data_dir() / "share" / "stage1"
    out.mkdir(parents=True, exist_ok=True)
    rows = load(history.db_path())
    samp = history.sample_days()
    main_rows = [r for r in rows if r["day"] in samp and r["day"] <= MAIN_END]
    quality = parse_quality(main_rows)
    if a.checks_only:
        (out / "checks.txt").write_text(name_checks(out, quality), encoding="utf-8")
        print((out / "checks.txt").read_text(encoding="utf-8"))
        return 0
    if a.charts_only:
        res = json.loads((out / "numbers.json").read_text(encoding="utf-8"))
        for f in ("finding1_price_by_bids", "finding2_single_bid_share", "finding3_procedure_mix"):
            _int_years(res[f])
        draw(res, out)
        (out / "checks.txt").write_text(name_checks(out, quality), encoding="utf-8")
        return 0
    rng = np.random.default_rng(a.seed)
    f4_rows = [r for r in rows if (r["day"] in samp or r["day"] >= CHANGE)]
    res = {
        "meta": {"source": "research/history.db (current rules)", "seed": a.seed, "reps": a.reps,
                 "main_period": f"sample days <= {MAIN_END}", "main_days": len({r['day'] for r in main_rows}),
                 "main_records": len(main_rows), "interval": "90% cluster bootstrap over days (5th-95th pct)",
                 "triples": "[point, lo, hi]"},
        "parse_quality": quality,
        "finding1_price_by_bids": finding1(main_rows, a.reps, rng),
        "finding2_single_bid_share": finding2(main_rows, a.reps, rng),
        "finding3_procedure_mix": finding3(main_rows, a.reps, rng),
        "finding4_publication_change": finding4(f4_rows, a.reps, rng),
    }
    (out / "numbers.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    draw(res, out)
    (out / "checks.txt").write_text(name_checks(out, quality), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
