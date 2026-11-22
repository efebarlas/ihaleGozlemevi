"""Static site generator (M3): export JSON (docs/data-contract.md §5) -> HTML in a dist dir.

Public API: `build(export_dir, out_dir)` and `deploy(dist_dir=None)`.
Output is deterministic: no build timestamps, sorted iteration everywhere.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path

from markupsafe import Markup

from ihale.indicators import usul_label

from . import d1
from .d1 import JV_LABEL
from .brands import is_series_brand_purchase
from .persons import PERSON_LABEL, is_joint_venture, is_natural_person
from jinja2 import Environment, FileSystemLoader, select_autoescape

PKG_DIR = Path(__file__).resolve().parent
SITE_DIR = PKG_DIR.parents[2] / "site"
EKAP_URL = "https://ekap.kik.gov.tr/EKAP/Ilan/BultenIndirme.aspx"
KURUL_URL = "https://ekap.kik.gov.tr/EKAP/Vatandas/KurulKararSorgu.aspx"   # plain search page; nothing is fetched

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
    "bedel_orani": "Bedel yaklaşık maliyete yakın veya üzerinde",
    "tekrarlayan_yuklenici": "Tekrarlayan yüklenici",
    "idare_orani": "İdarede tek teklif oranı yüksek",
    "tekrarlayan_eslesik": "Tekrarlayan yüklenici (başka bir işaretle birlikte)",
}
RATE_CODES = ["tek_teklif", "diger_teklifler_elendi", "bedel_orani", "tekrarlayan_eslesik", "idare_orani"]
DEFAULT_CUTOFF = 3.0     # Bugün cut-off when meta.json has no bugun_cutoff (contract §4.1)
INNOCENT = {  # one neutral "also common when…" line per flag type (detail pages and Yöntem)
    "tek_teklif": "Tek teklif, pazarın dar olduğu veya ürünün tek üreticisi bulunduğu alımlarda olağandır.",
    "diger_teklifler_elendi": "Teklifler belge eksikliği gibi biçimsel nedenlerle de elenebilir.",
    "bedel_orani": "Yaklaşık maliyet güncel piyasa fiyatlarıyla hazırlanmışsa bedel ona yakın çıkabilir.",
    "tekrarlayan_yuklenici": "Bölgedeki tek veya az sayıdaki tedarikçi aynı idareden sık sık iş alabilir.",
    "tekrarlayan_eslesik": "Bölgedeki tek veya az sayıdaki tedarikçi aynı idareden sık sık iş alabilir.",
    "idare_orani": "Merkezî alım kurumları (ör. DMO 4734/3-g) ve acil durum alımları (21/b) yapıları gereği tek teklifle sonuçlanabilir.",
}
INNOCENT_BEDEL_OVER = "Yaklaşık maliyet ihale tarihinden önce hazırlanmışsa ve fiyatlar arttıysa bedel onu aşabilir."
INNOCENT_BRAND = "Marka ve modeli belirtilmiş alımlarda tek teklif, yetkili satıcı yapısından kaynaklanabilir."
PAGE_MAX_RECORDS = 50    # day pages: records per page (also bounded by bytes)
PAGE_MAX_BYTES = 110_000  # keep every HTML page well under ~150 KB
EFFECT_LABELS = {
    "no_single_bid_points": "Tek teklif işaretleri gösterilir ama puan eklemez",
    "own_peer_group": "İdare yalnızca kendi geçmişiyle karşılaştırılır",
    "no_competition_points": "Tek teklif, bedel/maliyet oranı ve tekrar işaretleri gösterilir ama puan eklemez",
    "no_repeat_single_points": "Tek teklif ve tekrarlayan yüklenici işaretleri gösterilir ama puan eklemez",
}
MAX_CARDS_PER_IDARE = 2  # Bugün: more from the same idare are folded into one line
# detail pages only for records with score > 0 (keeps the file count bounded)
MAX_FILES = 19000        # Cloudflare free Workers static assets: 20,000 files per deploy
MIN_IDARE_RECORDS = 5    # no idare-level rate is shown below this sample (contract §4.1)
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
    return (-float(t.get("score", 0)), -_bedel_sort_value(t), t["id"])


def _flag_codes(t: dict) -> list[str]:
    codes = {f["code"] for f in t["flags"]} | {pt["code"] for pt in _parts(t)}
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


def _pct1(x) -> str:
    """Bedel ratio, floored to one decimal (same floor rule as the flag text: 0.9996 is %99,9, never %100)."""
    return f"%{math.floor(round(float(x) * 1000, 6)) / 10:.1f}".replace(".", ",")


def _pct_floor(x) -> str:
    return f"%{math.floor(round(float(x) * 100, 6))}"


def bedel_line(t: dict) -> str | None:
    """Actual bedel/yaklaşık maliyet ratio with its peer context (no cut-off is shown)."""
    ind = t.get("indicators") or {}
    if ind.get("bedel_orani") is None:
        return None
    out = f"{_pct1(ind['bedel_orani'])}"
    k = (t.get("kisim") or {}).get("records_in_ikn", 1)
    if k > 1:
        out += f" (İKN'deki {k} kısmın toplam bedeline göre)"
    if ind.get("bedel_orani_peer_median") is not None and ind.get("bedel_orani_peer_n"):
        out += f" · benzer idarelerde ortanca {_pct_floor(ind['bedel_orani_peer_median'])} (n={ind['bedel_orani_peer_n']})"
    return out


def bedel_peer_line(t: dict) -> str | None:
    ind = t.get("indicators") or {}
    if ind.get("bedel_orani_peer_median") is None or not ind.get("bedel_orani_peer_n"):
        return None
    return (f"Bedel / yaklaşık maliyet: bu kayıtta {_pct1(ind['bedel_orani'])} · "
            f"benzer idarelerde ortanca {_pct_floor(ind['bedel_orani_peer_median'])} (n={ind['bedel_orani_peer_n']})")


def _usul_group_label(g: str) -> str:
    """part_rates group key: '<type>/<usul>' (current) or a bare usul code (older exports)."""
    if g.split("/", 1)[0] in TYPE_LABELS and "/" in g:
        typ, u = g.split("/", 1)
        what = "Tüm usuller" if u == "hepsi" else (usul_label(u) or u)
        return f"{TYPE_LABELS.get(typ, typ)} · {what}"
    return "Tüm usuller" if g == "hepsi" else _usul_turu_label(g)


def indicators(t: dict) -> list[tuple[str, str]]:
    """(label, text) pairs for the neutral 'Göstergeler' block; null indicators are skipped."""
    ind = t.get("indicators") or {}
    out: list[tuple[str, str]] = []
    bl = bedel_line(t)
    if bl:
        out.append(("Bedel / yaklaşık maliyet", bl))
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


def _parts(t: dict) -> list[dict]:
    """score_parts as dicts (accepts the old list-of-strings shape too)."""
    return [pt if isinstance(pt, dict) else {"code": pt} for pt in t.get("score_parts") or []]


def tr_score(x) -> str:
    return f"{float(x):.1f}".replace(".", ",")


def tr_pct(p) -> str:
    if p is None:
        return "—"
    v = float(p) * 100
    if v == 0:
        return "%0"
    return "%" + (f"{v:.0f}" if v >= 10 else f"{v:.1f}".replace(".", ","))


def part_lines(t: dict) -> list[str]:
    out = []
    for pt in _parts(t):
        if pt.get("points") is None:
            continue
        s = f"{FLAG_TITLES.get(pt['code'], 'Diğer işaret')}: {tr_score(pt['points'])} puan"
        if pt.get("p") is not None:
            where = "tüm kayıtlarda" if pt.get("p_group") in (None, "hepsi") else "bu usulde"
            s += f" ({where} görülme oranı {tr_pct(pt['p'])})"
        out.append(s)
    return out


def formula_line(t: dict) -> str | None:
    """'Puan = (1,7 + 2,2) × 1,5 = 5,8' from the exported parts, weight and score."""
    pts = [pt["points"] for pt in _parts(t) if pt.get("points") is not None]
    if not pts or t.get("score") is None:
        return None
    inner = " + ".join(tr_score(p) for p in pts)
    w = t.get("value_weight")
    if w is not None and abs(float(w) - 1) > 1e-9:
        return f"Puan = ({inner}) × {tr_score(w)} = {tr_score(t['score'])}"
    return f"Puan = {inner} = {tr_score(t['score'])}"


def weight_line(t: dict, part_rates: dict) -> str | None:
    """Neutral 'Tutar katsayısı' line for the score breakdown (contract §4.1 Materiality)."""
    w = t.get("value_weight")
    if w is None:
        return None
    s = f"Tutar katsayısı: {tr_score(w)}"
    groups = [pt.get("p_group") for pt in _parts(t) if pt.get("p_group")]
    group = next((g for g in groups if g != "hepsi"), "hepsi")
    med = ((part_rates or {}).get(group) or {}).get("bedel_median_try")
    m = t.get("sozlesme_bedeli")
    if m and m.get("currency") == "TRY" and med:
        ratio = float(m["amount"]) / float(med)
        r = f"{ratio:.0f}" if ratio >= 2 else f"{ratio:.1f}".replace(".", ",")
        where = "tüm kayıtlardaki" if group == "hepsi" else "bu usuldeki"
        s += f" (sözleşme bedeli, {where} ortanca bedelin yaklaşık {r} katı)"
    elif not (m and m.get("currency") == "TRY"):
        s += " (TRY dışındaki veya okunamayan bedellere katsayı uygulanmaz)"
    return s


def idare_orani_text(t: dict) -> str:
    """The idare_orani note with the actual values: 'Bu idarede tek geçerli teklif payı %100 (n=114), karşılaştırma
    grubunda %23 (n=2.005)', with the procedure label when the export has one."""
    st = t.get("idare_stats") or {}
    who = f"Bu idarenin {st['usul_label']} alımlarında" if st.get("usul_label") else "Bu idarede"
    if st.get("tek_gecerli_teklif") is None or not st.get("records"):
        return f"{who} tek geçerli teklif payı karşılaştırma grubunun payından yüksektir"
    out = f"{who} tek geçerli teklif payı {_pct(st['tek_gecerli_teklif'])} (n={tr_int(st['records'])})"
    peer = st.get("peer") or {}
    if peer.get("tek_gecerli_teklif") is not None and peer.get("records"):
        out += f", karşılaştırma grubunda {_pct(peer['tek_gecerli_teklif'])} (n={tr_int(peer['records'])})"
    return out


_DANGLING = re.compile(r"(?:[,;:\-–/(]|\b(?:ve|ile|için|ait|olan|ilgili|kapsamında)|\b\d+\.)$", re.I)


def display_subject(s: str | None) -> str:
    """The subject as printed; add an ellipsis when it ends mid-phrase (a dangling conjunction, comma, hyphen or an
    unclosed parenthesis), which is how a cut-off bulletin line looks."""
    s = (s or "").strip()
    if not s:
        return "(adsız ilan)"
    if _DANGLING.search(s) or s.count("(") > s.count(")"):
        return s + "…"
    return s


def _pct(x) -> str:
    return f"%{round(float(x) * 100)}"


def peer_line(t: dict) -> str | None:
    """'Bu idare (n=12): %80 tek geçerli teklif · <peer label, n=140>: %43'; None when the idare sample is too small."""
    st = t.get("idare_stats") or {}
    n = st.get("records") or 0
    if n < MIN_IDARE_RECORDS or st.get("tek_gecerli_teklif") is None:
        return None
    who = f"Bu idarenin {st['usul_label']} alımları" if st.get("usul_label") else "Bu idare"
    out = f"{who} (n={n}): {_pct(st['tek_gecerli_teklif'])} tek geçerli teklif"
    peer = st.get("peer") or {}
    if peer.get("label") and peer.get("records") and peer.get("tek_gecerli_teklif") is not None:
        label, pn = peer["label"], peer["records"]
        label = f"{label[:-1]}, n={pn})" if label.endswith(")") else f"{label} (n={pn})"
        out += f" · {label}: {_pct(peer['tek_gecerli_teklif'])}"
    elif st.get("peer_note"):
        out += f" · {st['peer_note']}"
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


def _group_key(t: dict) -> str:
    """Cap/cluster grouping: the parent key when the idare has one, else the idare key."""
    idare = t.get("idare") or {}
    return (idare.get("parent") or {}).get("key") or idare.get("key") or t["_idare"]


def _words(text: str) -> list[str]:
    return text.split()


def _norm_word(w: str) -> str:
    return re.sub(r"[^\w]", "", w.translate(str.maketrans({"İ": "i", "I": "ı"})).lower())


def common_phrase(names: list[str]) -> str | None:
    """Longest run of >= 2 words shared (case-insensitively) by every name; None when there is none."""
    if len(names) < 2:
        return None
    first = _words(names[0])
    others = [[_norm_word(w) for w in _words(n)] for n in names[1:]]
    nf = [_norm_word(w) for w in first]
    for size in range(len(first), 1, -1):
        for i in range(0, len(first) - size + 1):
            seq = nf[i:i + size]
            if all(any(o[j:j + size] == seq for j in range(len(o) - size + 1)) for o in others):
                return " ".join(first[i:i + size])
    return None


def _score_codes(t: dict) -> frozenset:
    return frozenset(pt["code"] for pt in _parts(t))


def fold_cards(flagged: list[dict]) -> list[dict]:
    """Bugün entries from the ranked records (highest score first).

    1. Records of the same parent idare with the same set of score-part codes (same day) form one cluster;
       records without a parent never cluster.
    2. A cluster counts once under the cap of MAX_CARDS_PER_IDARE units per group (parent key, else idare key);
       its rank is its highest score. Units over the cap are folded into one entry after the group's last kept
       unit. Nothing is dropped.
    Entries: {'card': t} | {'cluster': [t...], ...} | {'fold': [t...], 'codes': [...], 'idare': name}.
    """
    groups: dict[tuple, list[dict]] = {}
    for t in flagged:
        par = (t.get("idare") or {}).get("parent") or {}
        if par.get("key"):
            groups.setdefault((par["key"], _score_codes(t)), []).append(t)
    units: list[dict] = []
    emitted: set = set()
    for t in flagged:
        par = (t.get("idare") or {}).get("parent") or {}
        k = (par.get("key"), _score_codes(t))
        if par.get("key") and len(groups[k]) >= 2:
            if k in emitted:
                continue
            emitted.add(k)
            ms = groups[k]
            codes = sorted(_score_codes(ms[0]), key=lambda c: FLAG_ORDER.index(c) if c in FLAG_ORDER else 99)
            units.append({"cluster": ms, "parent": par.get("name") or par["key"], "gkey": par["key"],
                          "phrase": common_phrase([m["_name"] for m in ms]),
                          "all_codes": codes, "score": max(m["score"] for m in ms),
                          "codes": sorted({c for m in ms for c in m["_codes"]},
                                          key=lambda c: FLAG_ORDER.index(c) if c in FLAG_ORDER else 99)})
        else:
            units.append({"card": t, "gkey": _group_key(t)})
    kept: dict[str, int] = {}
    hidden: dict[str, list[dict]] = {}
    last_idx: dict[str, int] = {}
    items: list[dict] = []
    for u in units:
        key = u["gkey"]
        if kept.get(key, 0) < MAX_CARDS_PER_IDARE:
            kept[key] = kept.get(key, 0) + 1
            items.append(u)
            last_idx[key] = len(items) - 1
        else:
            hidden.setdefault(key, []).extend(u["cluster"] if "cluster" in u else [u["card"]])
    for key, hs in sorted(hidden.items(), key=lambda kv: -last_idx[kv[0]]):
        codes = sorted({c for h in hs for c in h["_codes"]}, key=lambda c: FLAG_ORDER.index(c) if c in FLAG_ORDER else 99)
        items.insert(last_idx[key] + 1, {"fold": hs, "codes": codes, "idare": hs[0]["_idare"]})
    return items


def merge_tiny_tail(pages: list[list[int]], sizes: list[int], max_bytes: int) -> list[list[int]]:
    """Fold a tiny last page (under 15% of a full page) into the previous one when the result stays under 130%."""
    if len(pages) >= 2:
        last = sum(sizes[i] for i in pages[-1])
        prev = sum(sizes[i] for i in pages[-2])
        if last < 0.15 * max_bytes and prev + last <= 1.3 * max_bytes:
            return pages[:-2] + [pages[-2] + pages[-1]]
    return pages


def paginate(sizes: list[int], max_bytes: int | None = None, max_records: int | None = None) -> list[list[int]]:
    """Greedy split of row indexes into pages by record count and byte size."""
    max_bytes = max_bytes or PAGE_MAX_BYTES
    max_records = max_records or PAGE_MAX_RECORDS
    pages: list[list[int]] = []
    cur: list[int] = []
    size = 0
    for i, n in enumerate(sizes):
        if cur and (len(cur) >= max_records or size + n > max_bytes):
            pages.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += n
    if cur:
        pages.append(cur)
    return pages


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
                       tr_money=tr_money, tr_int=tr_int, tr_score=tr_score, tr_pct=tr_pct,
                       tr_money_plain=lambda x: tr_money({"amount": x, "currency": "TRY"}) if x is not None else "—")
    env.globals["type_labels"] = TYPE_LABELS
    env.globals["innocent_brand"] = INNOCENT_BRAND
    return env


def _load(export_dir: Path):
    meta = json.loads((export_dir / "meta.json").read_text(encoding="utf-8"))
    days: dict[str, dict] = {}
    for p in sorted((export_dir / "days").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        days[_safe(d["date"])] = d
    return meta, days


def build(export_dir: Path, out_dir: Path, split_bulk: bool = True) -> None:
    """Build the site. Live builds (default) keep core pages in `out_dir` and stage the bulk pages (see d1.is_bulk)
    in `<out_dir>-pages.sqlite` for D1; `split_bulk=False` writes every page to `out_dir`."""
    export_dir, out_dir = Path(export_dir), Path(out_dir)
    meta, days = _load(export_dir)
    _wipe(out_dir)
    split = split_bulk
    stage = d1.Stage(d1.staging_path(out_dir)) if split else None
    if not split:
        for suffix in ("", "-journal"):
            old = Path(str(d1.staging_path(out_dir)) + suffix)
            if old.exists():
                old.unlink()
    env = _env()

    cutoff = float(meta.get("bugun_cutoff", DEFAULT_CUTOFF))
    flag_share = None            # filled below from meta counts: share of loaded records with at least one flag
    dates = sorted(days, reverse=True)
    latest = meta.get("latest_date") or (dates[0] if dates else None)
    types = sorted({t for d in days.values() for t in d.get("types", [])})
    type_text = ", ".join(TYPE_LABELS_LOWER.get(t, t) for t in types) or "—"
    ctx_base = dict(innocent=INNOCENT, innocent_bedel_over=INNOCENT_BEDEL_OVER,
                    innocent_items=[(FLAG_TITLES[c], [INNOCENT[c]] + ([INNOCENT_BEDEL_OVER] if c == "bedel_orani" else []))
                                    for c in FLAG_ORDER], ekap_url=EKAP_URL, kurul_url=KURUL_URL, flag_titles=FLAG_TITLES)

    def write(rel: str, template: str, **ctx):
        html = _squeeze(env.get_template(template).render(**ctx_base, **ctx))
        if stage is not None and d1.is_bulk(d1.url_path(rel) or ""):
            stage.add(d1.url_path(rel), html)
            return
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8", newline="\n")

    def prep(t: dict) -> dict:
        t = dict(t)
        t["_codes"] = _flag_codes(t)
        t["_name"] = display_subject(t.get("konu") or t.get("title"))
        t["_idare"] = (t.get("idare") or {}).get("name") or "okunamadı"
        yname = (t.get("yuklenici") or {}).get("name")
        t["_person"] = is_natural_person(yname)
        # natural persons: the name appears only on the record's own detail page (SPEC §6.1)
        t["_yuklenici"] = ((JV_LABEL if is_joint_venture(yname) else PERSON_LABEL) if t["_person"] else (yname or "okunamadı"))
        t["_bedel_peer"] = bedel_peer_line(t)
        iname = (t.get("idare") or {}).get("name")
        t["_idare_href"] = idare_href.get(iname)
        t["_yuk_href"] = None if t["_person"] else yuk_href.get(yname)
        par = ((t.get("idare") or {}).get("parent") or {}).get("name")
        if par and iname:
            idare_parent.setdefault(iname, par)
        t["_peer"] = peer_line(t)
        t["_ind"] = indicators(t)
        t["_idare_orani"] = any(pt["code"] == "idare_orani" for pt in _parts(t))
        t["_idare_orani_text"] = idare_orani_text(t) if t["_idare_orani"] else None
        t["score"] = float(t.get("score", 0))
        t["_parts"] = part_lines(t)
        t["_brand"] = (any(f["code"] == "tek_teklif" for f in t["flags"])
                       and is_series_brand_purchase(t.get("konu") or t.get("title") or ""))
        has_check = any(f.get("source_check") for f in t["flags"])
        t["_typo_note"] = ((t.get("indicators") or {}).get("source_check") == "typo" and not has_check)
        wl = weight_line(t, meta.get("part_rates"))
        if wl:
            t["_parts"].append(wl)
        fl = formula_line(t)
        if fl:
            t["_parts"].append(fl)
        if t["_idare_orani"]:
            t["_peer"] = None           # the flag text already states the same numbers (no duplicate line)
        return t

    idare_href = {e["name"]: f"/idare/{_safe(e['slug'])}/" for e in meta.get("idare_index") or []}
    yuk_href = {e["name"]: f"/yuklenici/{_safe(e['slug'])}/" for e in meta.get("yuklenici_index") or []
                if not is_natural_person(e["name"])}
    idare_parent: dict[str, str] = {}

    day_ctx = {}
    for ds in dates:
        tenders = sorted((prep(t) for t in days[ds]["tenders"]), key=_sort_key)
        for t in tenders:
            _safe(t["id"])
        c = (meta.get("counts") or {}).get(ds, {})
        shown = [t for t in tenders if t["score"] >= cutoff]
        day_ctx[ds] = dict(date=ds, tenders=tenders, flagged=shown,
                           records=c.get("records", len(tenders)),
                           flagged_n=c.get("flagged", sum(1 for t in tenders if t["flags"])))

    # archive
    write("arsiv/index.html", "arsiv.html", page="arsiv", title="Arşiv", rows=[day_ctx[ds] for ds in dates])

    # per-record context, then detail pages (only for score >= 1: bounded file count)
    for ds in dates:
        by_ikn: dict[str, list[dict]] = {}
        for t in day_ctx[ds]["tenders"]:
            t["_page"] = t["score"] > 0
            t["_href"] = f"/ihale/{t['id']}/" if t["_page"] else f"/gun/{ds}/#{t['id']}"
            by_ikn.setdefault(t.get("ikn") or "", []).append(t)
        for t in day_ctx[ds]["tenders"]:
            unread = _unreadable(t)
            rows = []
            for key, label in FIELD_LABELS:
                v = _field_value(t, key)
                reason = unread.get(key)
                missing = v is None and key not in OPTIONAL_FIELDS
                if key == "yuklenici" and t["_person"] and not t["_page"]:
                    v = t["_yuklenici"]
                href = t["_idare_href"] if key == "idare" else (t["_yuk_href"] if key == "yuklenici" else None)
                rows.append(dict(key=key, label=label, value=v, note=reason or "", href=href,
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
    # day pages: summary + paginated lists (every HTML page stays small); records without a detail page
    # get their anchor on a list page
    row_tpl = env.get_template("day_row.html")
    day_rows: dict[str, list[str]] = {}
    day_pages: dict[str, list[list[int]]] = {}
    for ds in dates:
        tenders = day_ctx[ds]["tenders"]

        def render_rows() -> list[str]:
            return [_squeeze(row_tpl.render(**ctx_base, t=t, date_fields=DATE_FIELDS, money_fields=MONEY_FIELDS))
                    for t in tenders]

        rows = render_rows()                               # first pass: sizes (links are placeholders)
        pages = paginate([len(r.encode("utf-8")) for r in rows])
        for pn, idxs in enumerate(pages, 1):
            for i in idxs:
                t = tenders[i]
                t["_pageno"] = pn
                if not t["_page"]:
                    t["_href"] = f"/gun/{ds}/{pn}/#{t['id']}"
        day_rows[ds], day_pages[ds] = render_rows(), pages  # second pass: final links
    for ds in dates:
        tenders = day_ctx[ds]["tenders"]
        pages = day_pages[ds]
        counts: dict[str, list[int]] = {}
        for t in tenders:
            g = _usul_turu_label((t.get("indicators") or {}).get("usul_turu") or "") if (t.get("indicators") or {}).get("usul_turu") else "Belirtilmemiş"
            c = counts.setdefault(g, [0, 0])
            c[0] += 1
            c[1] += 1 if t["score"] > 0 else 0
        groups = sorted(((g, n, sc) for g, (n, sc) in counts.items()), key=lambda x: -x[1])
        write(f"gun/{ds}/index.html", "day_summary.html", page="arsiv", title=tr_date_long(ds), day=day_ctx[ds],
              groups=groups,
              pages=[(pn, len(ix), tenders[ix[0]]["score"], tenders[ix[-1]]["score"]) for pn, ix in enumerate(pages, 1)])
        for pn, idxs in enumerate(pages, 1):
            write(f"gun/{ds}/{pn}/index.html", "day.html", page="arsiv", title=f"{tr_date_long(ds)} · sayfa {pn}",
                  day=day_ctx[ds], pn=pn, npages=len(pages), rows_html=Markup("\n".join(day_rows[ds][i] for i in idxs)))
        for t in tenders:
            if t["_page"]:
                write(f"ihale/{t['id']}/index.html", "tender.html", page="ihale", title=t["_name"], t=t,
                      date_fields=DATE_FIELDS, money_fields=MONEY_FIELDS)

    # Bugün
    d = day_ctx.get(latest)
    chips = []
    if d:
        for code in FLAG_ORDER:
            n = sum(1 for t in d["flagged"] if code in t["_codes"])
            if n:
                chips.append(dict(code=code, title=FLAG_TITLES[code], n=n))
    from ihale.slugs import tr_sort_key
    provinces = sorted({(t.get("idare_stats") or {}).get("il") for t in (d["flagged"] if d else [])} - {None, ""},
                       key=tr_sort_key)
    write("index.html", "index.html", page="bugun", title="Bugün", day=d, chips=chips, provinces=provinces,
          items=fold_cards(d["flagged"]) if d else [])

    _cnt = (meta.get("counts") or {}).values()
    _rec = sum(c.get("records", 0) for c in _cnt)
    _fl = sum(c.get("flagged", 0) for c in _cnt)
    if _rec:
        flag_share = dict(records=_rec, flagged=_fl, pct=f"%{round(100 * _fl / _rec)}")
    from .dossiers import build_dossiers
    href_by_id = {t["id"]: t["_href"] for ds in dates for t in day_ctx[ds]["tenders"]}
    build_dossiers(export_dir=export_dir, meta=meta, env=env, write=write, ctx_base=ctx_base,
                   render_fragment=lambda tpl, **kw: _squeeze(tpl.render(**ctx_base, **kw)),
                   href_by_id=href_by_id,
                   src_by_id={t["id"]: t["_c"]["src_text"] for ds in dates for t in day_ctx[ds]["tenders"] if t["_c"]["src_text"]}, idare_href=idare_href, yuk_href=yuk_href, idare_parent=idare_parent,
                   fmt=dict(tr_money=tr_money, tr_int=tr_int, tr_date_short=tr_date_short, type_labels=TYPE_LABELS,
                    subject=display_subject),
                   yk_label_by_id={t["id"]: t["_yuklenici"] for ds in dates for t in day_ctx[ds]["tenders"] if t["_person"]},
                   paginate_list=lambda sizes, mb: merge_tiny_tail(paginate(sizes, max_bytes=mb, max_records=10**9), sizes, mb))

    (out_dir / "arama-idare.json").write_text(
        json.dumps([[e["name"], e["slug"]] for e in meta.get("idare_index") or []], ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8", newline="\n")

    write("yontem/index.html", "yontem.html", page="yontem", title="Yöntem", type_text=type_text,
          earliest=min(dates) if dates else None, latest=latest,
          cutoff=tr_score(cutoff), rate_codes=RATE_CODES, flag_share=flag_share,
          part_rates=[(_usul_group_label(g), r) for g, r in sorted((meta.get("part_rates") or {}).items(),
                                                              key=lambda kv: (kv[0].split("/")[0] if kv[0].split("/")[0] in TYPE_LABELS else "", kv[0].endswith("hepsi"), kv[0]))],
          rules=[dict(r, effects_tr=[EFFECT_LABELS.get(e, e) for e in (r.get("effects") or [])])
                 for r in meta.get("structural_rules") or []])
    write("404.html", "404.html", page="404", title="Sayfa bulunamadı")

    for css in ("sutun.css", "style.css"):          # the one visual direction: tokens, then the stylesheet that uses them
        shutil.copyfile(PKG_DIR / "static" / css, out_dir / css)
    (out_dir / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8", newline="\n")
    (out_dir / "_headers").write_text("/*\n  X-Robots-Tag: noindex, nofollow\n", encoding="utf-8", newline="\n")

    if stage is not None:
        stage.close()
    n_files = sum(1 for p in out_dir.rglob("*") if p.is_file())
    if n_files > MAX_FILES:
        _wipe(out_dir)  # never leave a dist that deploy could pick up
        if split:
            d1.staging_path(out_dir).unlink(missing_ok=True)
        raise SiteTooLargeError(
            f"site has {n_files} files, over the limit of {MAX_FILES} (Cloudflare free tier allows 20,000 "
            f"per deploy). Reduce the number of pages (MIN_DETAIL_SCORE) or move to JSON-backed pages.")


_URL_RE = re.compile(r"https://[A-Za-z0-9.-]+\.workers\.dev\S*")


BudgetExceeded = d1.BudgetExceeded
EmptySiteError = d1.EmptySiteError
PLACEHOLDER_D1_ID = "00000000-0000-0000-0000-000000000000"
D1_NAME = "ihale-pages"
log = print


def _npx() -> str:
    npx = shutil.which("npx.cmd") if os.name == "nt" else None
    npx = npx or shutil.which("npx")
    if not npx:
        raise RuntimeError("npx not found on PATH (install Node.js)")
    return npx


class PaymentRequired(RuntimeError):
    """wrangler asked for a card, a paid plan or a new account: stop and report (never proceed)."""


_PAYMENT_RE = re.compile(
    r"(credit card|debit card|payment (method|details|information|required)|add a (card|payment)|paid plan|workers paid|"
    r"upgrade (to|your) (the )?(workers )?(paid|plan)|billing (information|details|required|plan)|requires a (paid|payment)|"
    r"create (a|an) (new )?(cloudflare )?account|sign up for)", re.I)


def _run_wrangler(args: list[str]) -> str:
    """Run `npx --yes wrangler@4 <args>` in site/ with the public npm registry; return stdout+stderr."""
    env = dict(os.environ, npm_config_registry="https://registry.npmjs.org/")
    proc = subprocess.run([_npx(), "--yes", "wrangler@4", *args], cwd=SITE_DIR, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=900)
    out = (proc.stdout or "") + (proc.stderr or "")
    m = _PAYMENT_RE.search(out)
    if m:
        raise PaymentRequired(f"STOP: wrangler output mentions {m.group(0)!r} (a card, paid plan or new account). "
                              f"Do not proceed; report this to the owner.\n{out}")
    if proc.returncode != 0:
        raise RuntimeError(f"wrangler {' '.join(args[:2])} failed ({proc.returncode}):\n{out}")
    return out


def _d1_id() -> str | None:
    cfg = re.sub(r"^\s*//.*$", "", (SITE_DIR / "wrangler.jsonc").read_text(encoding="utf-8"), flags=re.M)
    dbs = json.loads(cfg).get("d1_databases") or []
    return dbs[0].get("database_id") if dbs else None


_TRANSIENT_RE = re.compile(r"File could not be uploaded|ServiceUnavailable|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|"
                           r"fetch failed|socket hang up|network error|timed out", re.I)
RETRY_PAUSES = (15, 45)       # seconds before retry 1 and 2


def run_with_retries(args: list[str], *, sleep=time.sleep) -> str:
    """`_run_wrangler` with at most two retries after a transient upload/network error. Safe for `d1 execute --file`
    batches because every page group starts with a DELETE of its own rows, so replaying a batch gives the same rows.
    A payment/account prompt (PaymentRequired) or any other failure is never retried."""
    for attempt in range(len(RETRY_PAUSES) + 1):
        try:
            return _run_wrangler(args)
        except PaymentRequired:
            raise
        except RuntimeError as e:
            if attempt >= len(RETRY_PAUSES) or not _TRANSIENT_RE.search(str(e)):
                raise
            log(f"transient wrangler error ({str(e).splitlines()[0][:100]}); retry {attempt + 1} in {RETRY_PAUSES[attempt]} s")
            sleep(RETRY_PAUSES[attempt])
    raise AssertionError("unreachable")


def _delete_override(log) -> dict:
    """One-time per-run override of the empty-site deletion limit: IHALE_MAX_DELETE_FRACTION (e.g. 0.08), 0 < x <= 0.2.
    Unset = the normal 5% guard. Never set it in a scheduled task or config; log every use."""
    raw = os.environ.get("IHALE_MAX_DELETE_FRACTION")
    if not raw:
        return {}
    x = float(raw)
    if not 0 < x <= 0.2:
        raise ValueError(f"IHALE_MAX_DELETE_FRACTION={raw} out of range (0 < x <= 0.2)")
    log(f"WARNING: one-time deletion limit override {x:.0%} (IHALE_MAX_DELETE_FRACTION), default is 5%")
    return {"max_delete_fraction": x}


def deploy(dist_dir: Path | None = None, *, local: bool = False, manifest_path: Path | None = None,
           batch_dir: Path | None = None, max_rows: int = d1.D1_MAX_ROWS_PER_RUN, dry_run: bool = False,
           export_dir: Path | None = None) -> str:
    """Deploy: changed bulk pages to D1, then the Worker + static assets, then D1 deletions.

    Returns the Worker URL (or "local" with local=True, which only fills the local D1 used by `wrangler dev --local`
    and skips `wrangler deploy`). Raises RuntimeError with wrangler's output on failure. The manifest of what is in
    D1 (separate for local and remote, versioned for the gzip table) is updated only after each batch succeeds.

    With dry_run=True every guard and the real plan run, the exact rows/bytes are logged, and nothing else happens:
    no wrangler call, no batch file, no manifest or usage change. Returns "dry-run"."""
    dist = Path(dist_dir) if dist_dir else SITE_DIR / "dist"
    index = dist / "index.html"
    if not index.is_file():
        log(f"empty-site guard (c): {index} is missing")
        raise EmptySiteError(f"nothing to deploy: {index} missing (run build first)")
    if (dist / "tokens").exists() or any(
            "data-direction" in f.read_text(encoding="utf-8", errors="replace") for f in (index, dist / "yontem" / "index.html")
            if f.is_file()):
        raise RuntimeError("refusing to deploy: dist contains design preview leftovers (token files / data-direction)")
    if "ÖRNEK İL MÜDÜRLÜĞÜ" in index.read_text(encoding="utf-8"):
        raise RuntimeError("refusing to deploy: dist was built from the test sample export")
    stage_db = d1.staging_path(dist)
    if not stage_db.is_file():
        raise RuntimeError(f"nothing to deploy: staged bulk pages {stage_db.name} missing (run build first)")
    d1.check_masking(dist, stage_db)
    d1.check_identity(dist, stage_db, SITE_DIR / "worker" / "index.js")
    if not local and _d1_id() in (None, PLACEHOLDER_D1_ID):
        raise RuntimeError("refusing to deploy: site/wrangler.jsonc still has the placeholder D1 database_id "
                           f"(create the database with `wrangler d1 create {D1_NAME}` and paste its id)")

    from ihale import config
    data = config.data_dir()
    d1.check_export_not_empty(export_dir or data / "export", log=lambda m: log(m))
    manifest_path = manifest_path or data / f"d1-manifest-{'local' if local else 'remote'}-{d1.MANIFEST_VERSION}.json"
    batch_dir = batch_dir or data / "d1-batches"
    where = ["--local"] if local else ["--remote"]
    url: list[str] = []

    from datetime import datetime, timezone
    usage_path = data / "d1-usage.json"

    def execute(f: Path) -> None:
        size = f.stat().st_size
        t0 = time.time()
        started = datetime.now(timezone.utc).strftime("%H:%M:%S")
        run_with_retries(["d1", "execute", D1_NAME, *where, f"--file={f}"])
        log(f"D1 execute {f.name}: {size:,} bytes, {time.time() - t0:.1f} s (started {started} UTC; "
            "bulk pages answer 503 while an import runs)")
        if not local:                                       # keep today's tally honest even if a later batch fails
            d1.add_rows_written(usage_path, f.read_text(encoding="utf-8").count("INSERT INTO pg"),
                                datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    def between() -> None:
        if local:
            url.append("local")
            return
        cmd = ["deploy"]
        if dist.resolve() != (SITE_DIR / "dist").resolve():
            cmd += ["--assets", str(dist.resolve())]
        out = _run_wrangler(cmd)
        m = _URL_RE.search(out)
        if not m:
            raise RuntimeError(f"wrangler deploy succeeded but no URL found in output:\n{out}")
        url.append(m.group(0).rstrip(".,)"))

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    plan = d1.sync_pages(stage_db=stage_db, manifest_path=manifest_path, batch_dir=batch_dir, execute=execute,
                         between=between, max_rows=max_rows, dry_run=dry_run, **_delete_override(log),
                         rows_today=0 if local else d1.rows_written_today(usage_path, today), log=lambda m: log(m))
    if dry_run:
        return "dry-run"
    if not local:
        report_d1_usage(data, plan, today)
    return url[0]


def report_d1_usage(data: Path, plan, today: str) -> list[str]:
    """Warn (log line + marker file in <data>/logs/) at 80% of any D1 free limit. Rows written are tracked here;
    storage and rows read come from `wrangler d1 info` / `insights` when they are available without extra auth."""
    written = d1.rows_written_today(data / "d1-usage.json", today)       # tracked per executed batch
    size = reads = None
    try:
        size = d1.parse_info_size(_run_wrangler(["d1", "info", D1_NAME, "--json"]))
    except PaymentRequired:
        raise
    except Exception as e:  # noqa: BLE001
        log(f"D1 usage: storage size unavailable ({type(e).__name__})")
    try:
        reads = d1.parse_rows_read(_run_wrangler(["d1", "insights", D1_NAME, "--timePeriod", "1d", "--json"]))
    except PaymentRequired:
        raise
    except Exception as e:  # noqa: BLE001
        log(f"D1 usage: rows read unavailable ({type(e).__name__})")
    log(f"D1 usage: {written:,} rows written today, {plan.total_bytes / 1e6:.0f} MB staged"
        + (f", database {size / 1e6:.0f} MB" if size else "") + (f", {reads:,} rows read (1d)" if reads is not None else ""))
    warnings = d1.usage_warnings(rows_written_today=written, rows_read_today=reads, db_bytes=size,
                                 stored_bytes=plan.total_bytes)
    marker = data / "logs" / "d1-usage-warning.txt"
    if warnings:
        for w in warnings:
            log("WARNING: " + w)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("\n".join([today] + warnings) + "\n", encoding="utf-8")
    elif marker.exists():
        marker.unlink()
    return warnings
