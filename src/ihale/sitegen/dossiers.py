"""Idare and yüklenici dosya pages (M4): /idare/, /idare/<slug>/, /yuklenici/, /yuklenici/<slug>/.

Reads export/idare/<slug>.json and export/yuklenici/<slug>.json (contract §5.2). Facts only: no firm-level
score, rank or rate (SPEC §6.1). Natural persons are masked everywhere and get no page.
"""
from __future__ import annotations

import json
from pathlib import Path

from markupsafe import Markup

from .persons import PERSON_LABEL, is_natural_person

ROW_BYTES_FIRST = 80_000     # timeline rows that share the first page with the dossier head
ROW_BYTES_NEXT = 100_000
ROW_MAX = 50
LIST_BYTES = 100_000
MIX_GRAYS = [1.0, 0.75, 0.55, 0.4, 0.28, 0.18, 0.1]   # neutral shading only (no hues)
IDARE_NOTE = "Bir idarenin tablosu tek başına bir sonuç değildir; usul ve alım türü farklılıkları rakamları etkiler."
YUK_NOTE = "Bir firmanın sözleşme listesi tek başına bir sonuç değildir; firmanın faaliyet alanı ve idarelerin alım hacmi listeyi etkiler."


def _mask(name: str | None) -> tuple[str, bool]:
    """(display name, is_masked)."""
    if not name:
        return "okunamadı", False
    if name == PERSON_LABEL or is_natural_person(name):
        return PERSON_LABEL, True
    return name, False


def _chunk(sizes: list[int], first_budget: int, next_budget: int) -> list[list[int]]:
    pages: list[list[int]] = []
    cur: list[int] = []
    used = 0
    budget = first_budget
    for i, n in enumerate(sizes):
        if cur and (len(cur) >= ROW_MAX or used + n > budget):
            pages.append(cur)
            cur, used, budget = [], 0, next_budget
        cur.append(i)
        used += n
    if cur or not pages:
        pages.append(cur)
    return pages


def _load_dir(export_dir: Path, kind: str, index: list[dict]) -> dict[str, dict]:
    out = {}
    for e in index:
        f = export_dir / kind / f"{e['slug']}.json"
        if f.is_file():
            out[e["slug"]] = json.loads(f.read_text(encoding="utf-8"))
    return out


def mix_rows(d: dict) -> tuple[list[dict], list[dict], int]:
    cats = d.get("procedure_categories") or []
    weeks = d.get("procedure_mix") or []
    peak = max((sum((w.get("counts") or {}).values()) for w in weeks), default=0) or 1
    rows = []
    for w in weeks:
        counts = w.get("counts") or {}
        total = sum(counts.values())
        x = 0.0
        segs = []
        for i, c in enumerate(cats):
            n = counts.get(c["code"], 0)
            if n:
                wd = 100.0 * n / peak
                segs.append(dict(x=round(x, 2), w=round(wd, 2), op=MIX_GRAYS[min(i, len(MIX_GRAYS) - 1)],
                                 label=c["label"], n=n))
                x += wd
        rows.append(dict(week=w["week"], start=w.get("start"), total=total,
                         cells=[counts.get(c["code"], 0) for c in cats], segs=segs))
    legend = [dict(label=c["label"], op=MIX_GRAYS[min(i, len(MIX_GRAYS) - 1)]) for i, c in enumerate(cats)]
    return rows, legend, peak


def build_dossiers(*, export_dir: Path, meta: dict, env, write, render_fragment, ctx_base: dict, href_by_id: dict,
                   idare_href: dict, yuk_href: dict, idare_parent: dict, fmt: dict, paginate_list) -> None:
    """Write all dossier pages. `idare_href` / `yuk_href`: display name -> page path (for linking)."""
    flag_titles = ctx_base["flag_titles"]
    idx_i = meta.get("idare_index") or []
    idx_y = [e for e in (meta.get("yuklenici_index") or []) if not is_natural_person(e.get("name"))]
    idares = _load_dir(export_dir, "idare", idx_i)
    yuks = _load_dir(export_dir, "yuklenici", idx_y)
    tr_money, tr_int, tr_date_short = fmt["tr_money"], fmt["tr_int"], fmt["tr_date_short"]
    row_tpl = env.get_template("dosya_row.html")

    def render_rows(rows: list[dict]) -> list[str]:
        return [render_fragment(row_tpl, r=r) for r in rows]

    def link_for(rid: str) -> str | None:
        return href_by_id.get(rid)

    # -------------------------------------------------------------- idare pages
    for slug, d in idares.items():
        rows = []
        for a in d.get("timeline") or []:
            who, masked = _mask(a.get("yuklenici"))
            ys = None if masked else a.get("yuklenici_slug")
            rows.append(dict(
                href=link_for(a["id"]), title=a.get("konu") or "(adsız ilan)", date=tr_date_short(a["date"]),
                who=who, who_yk=True, who_href=(f"/yuklenici/{ys}/" if ys and ys in yuks else None),
                bedel=tr_money(a["bedel"]) if a.get("bedel") else "okunamadı",
                flags=[flag_titles.get(f, "Diğer işaret") for f in a.get("flags") or []], second=None))
        rendered = render_rows(rows)
        pages = _chunk([len(x.encode("utf-8")) for x in rendered], ROW_BYTES_FIRST, ROW_BYTES_NEXT)
        mix, legend, peak = mix_rows(d)
        groups = []
        for g in d.get("tek_gecerli_by_group") or []:
            peer = g.get("peer") or {}
            groups.append(dict(
                label=g.get("label") or g.get("usul_turu") or "—", records=g.get("records") or 0,
                rate=g.get("tek_gecerli_teklif"), enough=(g.get("records") or 0) >= 5,
                peer_label=peer.get("label"), peer_n=peer.get("records"), peer_rate=peer.get("tek_gecerli_teklif"),
                peer_note=g.get("peer_note")))

        def top(lst):
            out = []
            for y in lst or []:
                name, masked = _mask(y.get("name"))
                out.append(dict(name=name, href=(None if masked or y.get("slug") not in yuks else f"/yuklenici/{y['slug']}/"),
                                count=y.get("count"), try_total=y.get("try_total")))
            return out

        n = len(pages)
        base = dict(d=d, mix=mix, legend=legend, groups=groups, note=IDARE_NOTE, npages=n,
                    top_count=top(d.get("top_yuklenici_by_count")), top_try=top(d.get("top_yuklenici_by_try")),
                    parent=idare_parent.get(d["name"]), kind="idare", slug=slug, total_rows=len(rows))
        write(f"idare/{slug}/index.html", "idare.html", page="idare", title=d["name"], pn=1,
              rows_html=Markup("\n".join(rendered[i] for i in pages[0])), **base)
        for pn in range(2, n + 1):
            write(f"idare/{slug}/{pn}/index.html", "dosya_more.html", page="idare", title=f"{d['name']} · sayfa {pn}",
                  pn=pn, name=d["name"], kind="idare", slug=slug, npages=n,
                  rows_html=Markup("\n".join(rendered[i] for i in pages[pn - 1])))

    # -------------------------------------------------------------- yüklenici pages
    for slug, d in yuks.items():
        rows = []
        for a in d.get("awards") or []:
            ih = a.get("idare") or {}
            rows.append(dict(
                href=link_for(a["id"]), title=a.get("konu") or "(adsız ilan)", date=tr_date_short(a["date"]),
                who=ih.get("name") or "okunamadı", who_href=(idare_href.get(ih.get("name"))),
                bedel=tr_money(a["bedel"]) if a.get("bedel") else "okunamadı", flags=[],
                second=a.get("usul")))
        rendered = render_rows(rows)
        pages = _chunk([len(x.encode("utf-8")) for x in rendered], ROW_BYTES_FIRST, ROW_BYTES_NEXT)
        tot = [dict(name=t.get("idare"), href=idare_href.get(t.get("idare")), count=t.get("count"),
                    try_total=t.get("try_total")) for t in d.get("totals_per_idare") or []]
        n = len(pages)
        write(f"yuklenici/{slug}/index.html", "yuklenici.html", page="yuklenici", title=d["name"], d=d, pn=1,
              npages=n, totals=tot, note=YUK_NOTE, kind="yuklenici", slug=slug, total_rows=len(rows),
              rows_html=Markup("\n".join(rendered[i] for i in pages[0])))
        for pn in range(2, n + 1):
            write(f"yuklenici/{slug}/{pn}/index.html", "dosya_more.html", page="yuklenici",
                  title=f"{d['name']} · sayfa {pn}", pn=pn, name=d["name"], kind="yuklenici", slug=slug, npages=n,
                  rows_html=Markup("\n".join(rendered[i] for i in pages[pn - 1])))

    # -------------------------------------------------------------- index pages (A–Z, paginated)
    for kind, index, built, title, other in (
            ("idare", idx_i, idares, "İdareler", ("/yuklenici/", "Yükleniciler (şirketler)")),
            ("yuklenici", idx_y, yuks, "Yükleniciler", ("/idare/", "İdareler"))):
        items = [e for e in index if e["slug"] in built]
        nm = (lambda n: f'<span class="yk" data-yk>{_esc(n)}</span>') if kind == "yuklenici" else _esc
        frags = [f'<li><a href="/{kind}/{e["slug"]}/">{nm(e["name"])}</a> <span class="muted">{tr_int(e.get("records", 0))} kayıt</span></li>'
                 for e in items]
        pages = paginate_list([len(f.encode("utf-8")) for f in frags], LIST_BYTES)
        n = len(pages)
        for pn, idxs in enumerate(pages, 1):
            first = items[idxs[0]]["name"][:1] if idxs else ""
            last = items[idxs[-1]]["name"][:1] if idxs else ""
            rel = f"{kind}/index.html" if pn == 1 else f"{kind}/liste/{pn}/index.html"
            write(rel, "dosya_list.html", page=kind, title=title + ("" if pn == 1 else f" · sayfa {pn}"),
                  kind=kind, heading=title, pn=pn, npages=n, span=f"{first}–{last}", other=other, total=len(items),
                  items_html=Markup("\n".join(frags[i] for i in idxs)),
                  page_spans=[(k + 1, (items[ix[0]]["name"][:1], items[ix[-1]]["name"][:1])) for k, ix in enumerate(pages)])


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
