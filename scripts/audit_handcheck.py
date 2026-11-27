"""M5-audit hand check: what a detail page SHOWS vs the cached bulletin PDF text, field by field.

Source side is pdfplumber's raw page text cut to the notice block ("<seq>. <İKN>" heading to "Kamuoyuna saygıyla
duyurulur"), read with plain regexes, NOT the project's parser. Page side is the staged detail page HTML.
Names (idare, yüklenici) are compared but never printed (natural persons' names stay off reports).

    .venv/Scripts/python.exe -X utf8 scripts/audit_handcheck.py [--top 20] [--random 10] [--seed 20261127]
"""
from __future__ import annotations

import argparse
import html as H
import random
import re
import sqlite3
import sys
from pathlib import Path

import pdfplumber

DATA = Path.home() / "ihaleGozlemevi-data"
SRC_RE = {
    "ikn": r"İhale kayıt numarası\s*:\s*(\S+)",
    "usul": r"Usulü\s*:\s*(.+)",
    "ym": r"Yaklaşık Maliyeti\s*:\s*([\d.,]+\s*[A-Z]{3})",
    "esas": r"Esas Kısımlarının(?:\s*Yaklaşık Maliyeti)?\s*:\s*([\d.,]+\s*[A-Z]{3})",   # label may wrap
    "toplam": r"Toplam Teklif Sayısı\s*:\s*(\d+)",
    "gecerli": r"Toplam Geçerli Teklif Sayısı\s*:\s*(\d+)",
    "bedel": r"Bedeli\s*:\s*([\d.,]+\s*[A-Z]{3})",
}
PAGE_DT = {"ikn": "İhale kayıt no (İKN)", "usul": "İhale usulü", "ym": "Yaklaşık maliyet",
           "esas": "Esas kısım yaklaşık maliyeti", "toplam": "Toplam teklif sayısı", "gecerli": "Geçerli teklif sayısı",
           "bedel": "Sözleşme bedeli", "idare": "İdare", "yuklenici": "Yüklenici"}


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def norm_name(s: str) -> str:
    return re.sub(r"[^0-9a-zçğıöşü]", "", (s or "").replace("İ", "i").replace("I", "ı").lower())


def page_fields(html: str) -> dict:
    out = {}
    for k, dt in PAGE_DT.items():
        m = re.search(r"<dt>" + re.escape(dt) + r"</dt>\s*<dd>(.*?)</dd>", html, re.S)
        if m:
            out[k] = squash(H.unescape(re.sub(r"<[^>]+>", "", m.group(1))))
    return out


def notice_block(pdf_path: Path, p0: int, p1: int, seq: int, ikn: str) -> str | None:
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join((pdf.pages[i - 1].extract_text() or "") for i in range(max(1, p0), min(len(pdf.pages), p1 + 1) + 1))
    m = re.search(rf"(?m)^{seq}\. {re.escape(ikn)}\b", text)
    if not m:
        return None
    end = text.find("Kamuoyuna saygıyla duyurulur", m.end())
    return text[m.start(): end if end > 0 else None]


def check(row, html: str) -> list[tuple]:
    pdf = DATA / "bulletins" / row["bulletin_date"] / row["source_file"]
    block = notice_block(pdf, row["page_start"], (row["page_end"] or row["page_start"]) + 1, row["seq"], row["ikn"])
    if block is None:
        return [("notice block", "", "", "NOT FOUND")]
    pg = page_fields(html)
    rows = []
    for k, rx in SRC_RE.items():
        m = re.search(rx, block)
        src = squash(m.group(1)) if m else "—"
        shown = pg.get(k, "?")
        if k == "usul":
            ok = norm_name(shown) in norm_name(src) or norm_name(src) in norm_name(shown) or (shown == "Açık" and "açık" in src.lower())
        elif k in ("ym", "bedel", "esas"):
            ok = squash(shown).replace(" ", "") == src.replace(" ", "") or (shown == "—" and src == "—")
        else:
            ok = shown == src
        rows.append((k, shown, src, "yes" if ok else "NO"))
    flat = norm_name(block)
    for k in ("idare", "yuklenici"):
        shown = pg.get(k, "")
        if k == "yuklenici" and shown == "Gerçek kişi yüklenici":       # natural person: masked by design
            m = re.search(r"Yüklenici\s*:\s*(.+)", block)
            company = m and re.search(r"(?i)(şirket|ltd|a\.ş|kooperatif|ortaklığı|birliği|vakf|derne)", m.group(1))
            rows.append((k, "(masked person)", "(person)" if not company else "(company!)", "yes" if not company else "NO"))
            continue
        # names wrap around the label in the PDF layout: every word of the shown name must be in the notice
        words = [norm_name(w) for w in shown.split() if norm_name(w)]
        ok = bool(words) and (norm_name(shown) in flat or all(w in flat for w in words))
        rows.append((k, "(name)", "(in notice)", "yes" if ok else "NO"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--random", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20261127)
    a = ap.parse_args()
    db = sqlite3.connect(DATA / "ihale.db")
    db.row_factory = sqlite3.Row
    pages = sqlite3.connect(DATA / "site-build" / "dist-pages.sqlite")
    latest = db.execute("SELECT max(bulletin_date) FROM records").fetchone()[0]
    top = db.execute("SELECT * FROM records WHERE bulletin_date=? AND score>=3 ORDER BY score DESC LIMIT ?", (latest, a.top)).fetchall()
    pool = db.execute("SELECT * FROM records WHERE score>0 AND bulletin_date<>? ORDER BY id", (latest,)).fetchall()
    rnd = random.Random(a.seed).sample(pool, a.random)
    bad = 0
    for label, rows in (("Bugün top", top), ("random score>0", rnd)):
        for r in rows:
            path = f"/ihale/{r['bulletin_date']}-{r['bulletin_type']}-{r['section']}-{r['seq']}/"
            h = pages.execute("SELECT html FROM staged WHERE path=?", (path,)).fetchone()
            if h is None:
                print(f"{label} {path}: page not staged"); bad += 1
                continue
            res = check(r, h[0])
            miss = [x for x in res if x[3] != "yes"]
            bad += len(miss)
            print(f"\n{label} | {path} | score {r['score']} | {'all match' if not miss else f'{len(miss)} MISMATCH'}")
            print("  field | page | source | match")
            for f, p, s, ok in res:
                print(f"  {f} | {p} | {s} | {ok}")
    print(f"\nmismatches: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
