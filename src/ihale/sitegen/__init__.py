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

FLAG_ORDER = ["tek_teklif", "diger_teklifler_elendi", "bedel_orani", "tekrarlayan_yuklenici", "idare_orani"]
FLAG_TITLES = {
    "tek_teklif": "Tek teklif",
    "diger_teklifler_elendi": "Diğer teklifler elendi",
    "bedel_orani": "Bedel ≥ %97 yaklaşık maliyet",
    "tekrarlayan_yuklenici": "Tekrarlayan yüklenici",
    "idare_orani": "İdarede tek teklif oranı yüksek",
}
MIN_SHOWN_SCORE = 2      # Bugün shows records with score >= this (contract §4.1)
MIN_DETAIL_SCORE = 1     # detail pages only for score >= this (keeps the file count bounded)
MAX_FILES = 19000        # Cloudflare free Workers static assets: 20,000 files per deploy
MIN_IDARE_RECORDS = 5    # no idare-level rate is shown below this sample (contract §4.1)
IDARE_ORANI_TEXT = "İdarenin tek geçerli teklif payı, karşılaştırma grubunun 2 katı veya daha fazla"
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


class SiteTooLargeError(RuntimeError):
    pass


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
    return float(m["amount"]) if m and m.get("currency") == "TRY" else -1.0


def _sort_key(t: dict):
    # highest score first, then TRY bedel (other currencies last), then id for a stable order
    return (-int(t.get("score", 0)), -_bedel_sort_value(t), t["id"])


def _flag_codes(t: dict) -> list[str]:
    codes = {f["code"] for f in t["flags"]} | set(t.get("score_parts", []))
    return [c for c in FLAG_ORDER if c in codes] + sorted(codes - set(FLAG_ORDER))


USUL_TURU_LABELS = {
    "acik": "Açık ihale usulü", "belli_istekliler": "Belli istekliler arasında ihale usulü",
    "diger": "Diğer",
}


def _usul_turu_label(code: str) -> str:
    if code in USUL_TURU_LABELS:
        return USUL_TURU_LABELS[code]
    m = re.fullmatch(r"pazarlik_21([a-z])", code)
    if m:
        return f"Pazarlık usulü (md. 21/{m.group(1)})"
    m = re.fullmatch(r"istisna_3([a-z])", code)
    if m:
        return f"İstisna (4734 / 3-{m.group(1)})"
    m = re.fullmatch(r"dogrudan_temin_22([a-z])", code)
    if m:
        return f"Doğrudan temin (md. 22/{m.group(1)})"
    return code


def indicators(t: dict) -> list[tuple[str, str]]:
    """(label, text) pairs for the neutral 'Göstergeler' block; null indicators are skipped."""
    ind = t.get("indicators") or {}
    out: list[tuple[str, str]] = []
    if ind.get("elenen_orani") is not None:
        s = f"{_pct(ind['elenen_orani'])} (teklif verenlerin elenen payı)"
        if ind.get("elenen_orani_peer") is not None:
            s += f" · benzer idarelerin ortalaması: {_pct(ind['elenen_orani_peer'])}"
        out.append(("Elenen teklif oranı", s))
    if ind.get("karar_suresi_gun") is not None:
        out.append(("Karar süresi", f"{ind['karar_suresi_gun']} gün (ihale tarihinden sözleşme tarihine)"))
    if ind.get("usul_turu"):
        s = _usul_turu_label(ind["usul_turu"])
        if ind.get("acik_olmayan"):
            s += " · açık olmayan usul"
        out.append(("Usul türü", s))
    if ind.get("yuklenici_payi") is not None:
        s = f"{_pct(ind['yuklenici_payi'])} (idarenin son 365 gündeki TRY sözleşme bedelleri toplamı içinde"
        s += f", n={ind['yuklenici_payi_n']})" if ind.get("yuklenici_payi_n") else ")"
        out.append(("Yüklenicinin payı", s))
    return out


def _pct(x) -> str:
    return f"%{round(float(x) * 100)}"


def peer_line(t: dict) -> str | None:
    """'Bu idare (n=12): %80 tek geçerli teklif · <peer label, n=140>: %43'; None when the idare sample is too small."""
    st = t.get("idare_stats") or {}
    n = st.get("records") or 0
    if n < MIN_IDARE_RECORDS or st.get("tek_gecerli_teklif") is None:
        return None
    out = f"Bu idare (n={n}): {_pct(st['tek_gecerli_teklif'])} tek geçerli teklif"
    peer = st.get("peer") or {}
    if peer.get("label") and peer.get("records") and peer.get("tek_gecerli_teklif") is not None:
        label, pn = peer["label"], peer["records"]
        label = f"{label[:-1]}, n={pn})" if label.endswith(")") else f"{label} (n={pn})"
        out += f" · {label}: {_pct(peer['tek_gecerli_teklif'])}"
    return out


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


_WS = re.compile(r"\s+")


def _squeeze(html: str) -> str:
    """Collapse whitespace runs (no <pre>/<textarea> in our templates) to keep big day pages small."""
    return _WS.sub(" ", html)


def _wipe(out_dir: Path) -> None:
    """Empty out_dir but keep the directory itself (it may be some process's cwd, e.g. a dev server)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for child in out_dir.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()


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
    _wipe(out_dir)
    env = _env()

    dates = sorted(days, reverse=True)
    latest = meta.get("latest_date") or (dates[0] if dates else None)
    types = sorted({t for d in days.values() for t in d.get("types", [])})
    type_text = ", ".join(TYPE_LABELS_LOWER.get(t, t) for t in types) or "—"
    ctx_base = dict(idare_orani_text=IDARE_ORANI_TEXT, repo_url=REPO_URL, ekap_url=EKAP_URL, flag_titles=FLAG_TITLES)

    def write(rel: str, template: str, **ctx):
        html = _squeeze(env.get_template(template).render(**ctx_base, **ctx))
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8", newline="\n")

    def prep(t: dict) -> dict:
        t = dict(t)
        t["_codes"] = _flag_codes(t)
        t["_name"] = t.get("konu") or t.get("title") or "(adsız ilan)"
        t["_idare"] = (t.get("idare") or {}).get("name") or "okunamadı"
        t["_yuklenici"] = (t.get("yuklenici") or {}).get("name") or "okunamadı"
        t["_peer"] = peer_line(t)
        t["_ind"] = indicators(t)
        t["_idare_orani"] = "idare_orani" in t.get("score_parts", [])
        t["score"] = int(t.get("score", 0))
        return t

    day_ctx = {}
    for ds in dates:
        tenders = sorted((prep(t) for t in days[ds]["tenders"]), key=_sort_key)
        for t in tenders:
            _safe(t["id"])
        c = (meta.get("counts") or {}).get(ds, {})
        shown = [t for t in tenders if t["score"] >= MIN_SHOWN_SCORE]
        day_ctx[ds] = dict(date=ds, tenders=tenders, flagged=shown,
                           records=c.get("records", len(tenders)),
                           flagged_n=c.get("flagged", sum(1 for t in tenders if t["flags"])))

    # Bugün
    d = day_ctx.get(latest)
    chips = []
    if d:
        for code in FLAG_ORDER:
            n = sum(1 for t in d["flagged"] if code in t["_codes"])
            if n:
                chips.append(dict(code=code, title=FLAG_TITLES[code], n=n))
    write("index.html", "index.html", page="bugun", title="Bugün", day=d, chips=chips)

    # archive
    write("arsiv/index.html", "arsiv.html", page="arsiv", title="Arşiv", rows=[day_ctx[ds] for ds in dates])

    # per-record context, then detail pages (only for score >= 1: bounded file count)
    for ds in dates:
        by_ikn: dict[str, list[dict]] = {}
        for t in day_ctx[ds]["tenders"]:
            t["_page"] = t["score"] >= MIN_DETAIL_SCORE
            t["_href"] = f"/ihale/{t['id']}/" if t["_page"] else f"/gun/{ds}/#{t['id']}"
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
            src = t.get("source") or {}
            type_label = TYPE_LABELS.get(src.get("type"), src.get("type") or "")
            src_text = ""
            if src.get("date"):
                src_text = f"Kamu İhale Bülteni, {tr_date_short(src['date'])}, {type_label} – Sonuç İlanları"
                if src.get("page"):
                    src_text += f", s. {src['page']}"
            t["_c"] = dict(rows=rows, n_ikn=(t.get("kisim") or {}).get("records_in_ikn", 1),
                           siblings=[x for x in by_ikn.get(t.get("ikn") or "", []) if x["id"] != t["id"]],
                           src=src, src_text=src_text, section_label=SECTION_LABELS.get(t.get("section"), ""),
                           src_date_short=tr_date_short(src["date"]) if src.get("date") else "",
                           type_label=type_label)
    for ds in dates:
        write(f"gun/{ds}/index.html", "day.html", page="arsiv", title=tr_date_long(ds), day=day_ctx[ds],
              date_fields=DATE_FIELDS, money_fields=MONEY_FIELDS)
        for t in day_ctx[ds]["tenders"]:
            if t["_page"]:
                write(f"ihale/{t['id']}/index.html", "tender.html", page="ihale", title=t["_name"], t=t,
                      date_fields=DATE_FIELDS, money_fields=MONEY_FIELDS)

    write("yontem/index.html", "yontem.html", page="yontem", title="Yöntem", type_text=type_text,
          earliest=min(dates) if dates else None, latest=latest)
    write("404.html", "404.html", page="404", title="Sayfa bulunamadı")

    shutil.copyfile(PKG_DIR / "static" / "style.css", out_dir / "style.css")
    (out_dir / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8", newline="\n")
    (out_dir / "_headers").write_text("/*\n  X-Robots-Tag: noindex, nofollow\n", encoding="utf-8", newline="\n")

    n_files = sum(1 for p in out_dir.rglob("*") if p.is_file())
    if n_files > MAX_FILES:
        _wipe(out_dir)  # never leave a dist that deploy could pick up
        raise SiteTooLargeError(
            f"site has {n_files} files, over the limit of {MAX_FILES} (Cloudflare free tier allows 20,000 "
            f"per deploy). Reduce the number of pages (MIN_DETAIL_SCORE) or move to JSON-backed pages.")


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
