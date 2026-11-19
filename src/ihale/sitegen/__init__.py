"""Static site generator (M3): export JSON (docs/data-contract.md §5) -> HTML in a dist dir.

Public API: `build(export_dir, out_dir)` and `deploy(dist_dir=None)`.
Output is deterministic: no build timestamps, sorted iteration everywhere.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

PKG_DIR = Path(__file__).resolve().parent
SITE_DIR = PKG_DIR.parents[2] / "site"
EKAP_URL = "https://ekap.kik.gov.tr/EKAP/Ilan/BultenIndirme.aspx"
REPO_URL = "https://github.com/efebarlas/ihaleGozlemevi"

MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
          "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
TYPE_LABELS = {"mal": "Mal", "hizmet": "Hizmet", "yapim": "Yapım", "danismanlik": "Danışmanlık"}
TYPE_LABELS_LOWER = {"mal": "mal alımı", "hizmet": "hizmet alımı", "yapim": "yapım işi",
                     "danismanlik": "danışmanlık"}
SECTION_LABELS = {"A": "4734 sayılı Kanun kapsamında", "B": "Kanun kapsamı dışı / diğer"}

FLAG_ORDER = ["tek_gecerli_teklif", "bedel_orani", "tekrarlayan_yuklenici"]
FLAG_TITLES = {
    "tek_gecerli_teklif": "Tek geçerli teklif",
    "bedel_orani": "Bedel ≥ %95 yaklaşık maliyet",
    "tekrarlayan_yuklenici": "Tekrarlayan yüklenici",
}
# (export key, Turkish label) in display order for the detail page
FIELD_LABELS = [
    ("ikn", "İhale kayıt no (İKN)"),
    ("title", "İşin adı"),
    ("konu", "İhale konusu"),
    ("idare", "İdare"),
    ("yuklenici", "Yüklenici"),
    ("tur", "İhale türü"),
    ("usul", "İhale usulü"),
    ("ihale_tarihi", "İhale tarihi"),
    ("yaklasik_maliyet", "Yaklaşık maliyet"),
    ("esas_kisim_yaklasik_maliyet", "Esas kısım yaklaşık maliyeti"),
    ("toplam_teklif", "Toplam teklif sayısı"),
    ("gecerli_teklif", "Geçerli teklif sayısı"),
    ("sozlesme_tarihi", "Sözleşme tarihi"),
    ("sozlesme_bedeli", "Sözleşme bedeli"),
    ("sozlesme_suresi", "Sözleşme süresi"),
]
DATE_FIELDS = {"ihale_tarihi", "sozlesme_tarihi"}
MONEY_FIELDS = {"yaklasik_maliyet", "esas_kisim_yaklasik_maliyet", "sozlesme_bedeli"}
# Absent by design for single-lot tenders; not "okunamadı" when empty.
OPTIONAL_FIELDS = {"esas_kisim_yaklasik_maliyet"}
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _safe(s: str) -> str:
    if not _SAFE.match(s or ""):
        raise ValueError(f"unsafe path component in export: {s!r}")
    return s


def tr_date_long(s) -> str:
    d = date.fromisoformat(s)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def tr_date_short(s) -> str:
    d = date.fromisoformat(s)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def tr_money(m) -> str:
    """{'amount': 2767200.0, 'currency': 'TRY'} -> '2.767.200,00 TRY' (+ ' (alt)' for dual figures)."""
    if not m:
        return ""
    cents = round(float(m["amount"]) * 100)
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    out = f"{sign}{whole:,}".replace(",", ".") + f",{frac:02d} {m.get('currency', '')}".rstrip()
    alt = m.get("alt")
    if isinstance(alt, dict):
        out += f" ({tr_money(alt)})"
    elif alt:
        out += f" ({alt})"
    return out


def tr_int(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def _bedel_sort_value(t: dict) -> float:
    m = t.get("sozlesme_bedeli")
    return float(m["amount"]) if m else -1.0


def _sort_key(t: dict):
    # most flags first, then largest bedel, then id for a stable order
    return (-len(t["flags"]), -_bedel_sort_value(t), t["id"])


def _flag_codes(t: dict) -> list[str]:
    codes = {f["code"] for f in t["flags"]}
    return [c for c in FLAG_ORDER if c in codes] + sorted(codes - set(FLAG_ORDER))


def _unreadable(t: dict) -> dict[str, str]:
    """field -> reason ('' when plainly unreadable)."""
    out: dict[str, str] = {}
    for u in t.get("unreadable", []):
        if isinstance(u, dict):
            out[u["field"]] = u.get("reason", "")
        else:
            out[u] = ""
    return out


def _field_value(t: dict, key: str):
    if key in ("idare", "yuklenici"):
        v = t.get(key)
        return v.get("name") if v else None
    return t.get(key)


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(PKG_DIR / "templates"),
                      autoescape=select_autoescape(["html", "xml"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update(tr_date_long=tr_date_long, tr_date_short=tr_date_short,
                       tr_money=tr_money, tr_int=tr_int)
    return env


def _load(export_dir: Path):
    meta = json.loads((export_dir / "meta.json").read_text(encoding="utf-8"))
    days: dict[str, dict] = {}
    for p in sorted((export_dir / "days").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        days[_safe(d["date"])] = d
    return meta, days


def build(export_dir: Path, out_dir: Path) -> None:
    export_dir, out_dir = Path(export_dir), Path(out_dir)
    meta, days = _load(export_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    env = _env()

    dates = sorted(days, reverse=True)
    latest = meta.get("latest_date") or (dates[0] if dates else None)
    types = sorted({t for d in days.values() for t in d.get("types", [])})
    type_text = ", ".join(TYPE_LABELS_LOWER.get(t, t) for t in types) or "—"
    ctx_base = dict(repo_url=REPO_URL, ekap_url=EKAP_URL, flag_titles=FLAG_TITLES)

    def write(rel: str, template: str, **ctx):
        html = env.get_template(template).render(**ctx_base, **ctx)
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8", newline="\n")

    def prep(t: dict) -> dict:
        t = dict(t)
        t["_codes"] = _flag_codes(t)
        t["_name"] = t.get("konu") or t.get("title") or "(adsız ilan)"
        return t

    day_ctx = {}
    for ds in dates:
        tenders = sorted((prep(t) for t in days[ds]["tenders"]), key=_sort_key)
        for t in tenders:
            _safe(t["id"])
        c = (meta.get("counts") or {}).get(ds, {})
        flagged = [t for t in tenders if t["flags"]]
        day_ctx[ds] = dict(date=ds, tenders=tenders, flagged=flagged,
                           records=c.get("records", len(tenders)),
                           flagged_n=c.get("flagged", len(flagged)))

    # Bugün
    d = day_ctx.get(latest)
    chips = []
    if d:
        for code in FLAG_ORDER:
            n = sum(1 for t in d["flagged"] if code in t["_codes"])
            if n:
                chips.append(dict(code=code, title=FLAG_TITLES[code], n=n))
    write("index.html", "index.html", page="bugun", title="Bugün", day=d, chips=chips)

    # day pages + archive
    for ds in dates:
        write(f"gun/{ds}/index.html", "day.html", page="arsiv", title=tr_date_long(ds), day=day_ctx[ds])
    write("arsiv/index.html", "arsiv.html", page="arsiv", title="Arşiv", rows=[day_ctx[ds] for ds in dates])

    # detail pages
    for ds in dates:
        by_ikn: dict[str, list[dict]] = {}
        for t in day_ctx[ds]["tenders"]:
            by_ikn.setdefault(t.get("ikn") or "", []).append(t)
        for t in day_ctx[ds]["tenders"]:
            unread = _unreadable(t)
            rows = []
            for key, label in FIELD_LABELS:
                v = _field_value(t, key)
                reason = unread.get(key)
                missing = v is None and key not in OPTIONAL_FIELDS
                rows.append(dict(key=key, label=label, value=v, note=reason or "",
                                 unreadable=missing or (key in unread and reason == "")))
            n_ikn = (t.get("kisim") or {}).get("records_in_ikn", 1)
            siblings = [s for s in by_ikn.get(t.get("ikn") or "", []) if s["id"] != t["id"]]
            src = t.get("source") or {}
            type_label = TYPE_LABELS.get(src.get("type"), src.get("type") or "")
            src_text = ""
            if src.get("date"):
                src_text = f"Kamu İhale Bülteni, {tr_date_short(src['date'])}, {type_label} – Sonuç İlanları"
                if src.get("page"):
                    src_text += f", s. {src['page']}"
            write(f"ihale/{t['id']}/index.html", "tender.html", page="ihale", title=t["_name"], t=t,
                  rows=rows, n_ikn=n_ikn, siblings=siblings, src=src, src_text=src_text,
                  section_label=SECTION_LABELS.get(t.get("section"), ""),
                  src_date_short=tr_date_short(src["date"]) if src.get("date") else "",
                  type_label=type_label, date_fields=DATE_FIELDS, money_fields=MONEY_FIELDS)

    write("yontem/index.html", "yontem.html", page="yontem", title="Yöntem", type_text=type_text,
          earliest=min(dates) if dates else None, latest=latest)
    write("404.html", "404.html", page="404", title="Sayfa bulunamadı")

    shutil.copyfile(PKG_DIR / "static" / "style.css", out_dir / "style.css")
    (out_dir / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8", newline="\n")
    (out_dir / "_headers").write_text("/*\n  X-Robots-Tag: noindex, nofollow\n", encoding="utf-8", newline="\n")


_URL_RE = re.compile(r"https://[A-Za-z0-9.-]+\.workers\.dev\S*")


def deploy(dist_dir: Path | None = None) -> str:
    """Deploy with wrangler (assets-only Worker). Returns the URL; raises RuntimeError with wrangler's output on failure."""
    dist = Path(dist_dir) if dist_dir else SITE_DIR / "dist"
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"nothing to deploy: {index} missing (run build first)")
    if "ÖRNEK İL MÜDÜRLÜĞÜ" in index.read_text(encoding="utf-8"):
        raise RuntimeError("refusing to deploy: dist was built from the test sample export")
    npx = shutil.which("npx.cmd") if os.name == "nt" else None
    npx = npx or shutil.which("npx")
    if not npx:
        raise RuntimeError("npx not found on PATH (install Node.js)")
    cmd = [npx, "--yes", "wrangler@4", "deploy"]
    if dist.resolve() != (SITE_DIR / "dist").resolve():
        cmd += ["--assets", str(dist.resolve())]
    env = dict(os.environ, npm_config_registry="https://registry.npmjs.org/")
    proc = subprocess.run(cmd, cwd=SITE_DIR, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(f"wrangler deploy failed ({proc.returncode}):\n{out}")
    m = _URL_RE.search(out)
    if not m:
        raise RuntimeError(f"wrangler deploy succeeded but no URL found in output:\n{out}")
    return m.group(0).rstrip(".,)")
