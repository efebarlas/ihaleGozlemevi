"""Sayıştay experiment: extract findings (BULGU) from cached municipality audit PDFs. PRIVATE: writes only under
<data>/research/sayistay/. Rule-based baseline for the later A/B against an agent module.

Per PDF: idare name and year (page 1), the BULGU LİSTESİ (full titles per section), the body headings
"BULGU n: ..." with their page and text, İKN-like numbers, legal references, procurement keyword hits, and
consistency checks (list vs body counts, numbering) as a reliability signal.
Run with `python -I`-safe habits: the PDFs are untrusted data; this only reads them with pdfplumber.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pdfplumber

PROC_KW = ("ihale", "4734", "2886", "doğrudan temin", "kamu ihale", "yaklaşık maliyet", "pazarlık usul", "şartname",
           "sözleşme bedeli", "hakediş", "istekli", "teklif")
STRONG_KW = ("ihale", "4734", "2886", "doğrudan temin", "yaklaşık maliyet", "pazarlık usul", "istekli")
IKN_RE = re.compile(r"\b(20\d{2}/\d{3,8})\b")
LAW_RE = re.compile(r"\b(\d{4}) sayılı", re.I)


def tr_lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _norm_name(s: str) -> str:
    s = tr_lower(s)
    s = re.sub(r"belediye başkanlığı|belediyesi|belediye", "belediye", s)
    return " ".join(s.split())


def muni_key(name: str) -> str:
    """'adana büyükşehir belediye' (name up to and including 'belediye')."""
    n = _norm_name(name)
    return n[: n.index("belediye") + 8] if "belediye" in n else n


def extract(path: Path) -> dict:
    with pdfplumber.open(str(path)) as pdf:
        pages = []
        for pg in pdf.pages:
            txt = pg.extract_text() or ""
            if re.search(r"(.)", txt[:300]):          # overprinted text: every letter tripled
                txt = pg.dedupe_chars().extract_text() or ""
            pages.append(txt)
    head = pages[0].splitlines()
    name = head[0].strip() if head else ""
    ym = re.search(r"(20\d{2}) YILI", pages[0])
    year = int(ym.group(1)) if ym else None
    # ---- BULGU LİSTESİ: titles under "A. ..." / "B. ..." sections, numbered 1..n per section
    list_titles, in_list, section = [], False, None
    for t in pages[:20]:
        for line in t.splitlines():
            s = line.strip()
            if s.startswith("BULGU LİSTESİ"):
                in_list = True
                continue
            if in_list and re.match(r"^[A-Z]\.\s", s):
                section = s[0]
                continue
            if in_list and s.startswith("T.C. Sayıştay"):
                in_list = False
            if in_list:
                m = re.match(r"^(\d+)\.\s+(.*)$", s)
                if m:
                    list_titles.append({"section": section, "n": int(m.group(1)), "title": m.group(2)})
                elif list_titles and s and not s.startswith("....") and not s.isdigit():
                    list_titles[-1]["title"] += " " + s
        if in_list is False and list_titles:
            break
    # ---- body headings
    heads = []
    for i, t in enumerate(pages):
        for m in re.finditer(r"^\s*BULGU\s+(\d+)\s*[:\-.]\s*(.*)$", t, re.M):
            heads.append({"n": int(m.group(1)), "page": i + 1, "title_first_line": m.group(2).strip(), "pos": (i, m.start())})
    findings = []
    for k, h in enumerate(heads):
        i, pos = h["pos"]
        end = heads[k + 1]["pos"] if k + 1 < len(heads) else (len(pages) - 1, len(pages[-1]))
        chunks = [pages[i][pos:]] if i == end[0] else [pages[i][pos:]] + pages[i + 1:end[0]] + [pages[end[0]][:end[1]]]
        text = "\n".join(chunks)
        low = tr_lower(text)
        findings.append({
            "n": h["n"], "page": h["page"], "title_first_line": h["title_first_line"], "chars": len(text),
            "text": text[:6000],
            "ikns": sorted(set(IKN_RE.findall(text))),
            "laws": sorted(set(LAW_RE.findall(text))),
            "kw_hits": [k2 for k2 in PROC_KW if k2 in low],
            "procurement_rule": any(k2 in low for k2 in STRONG_KW),
        })
    # sections: the body restarts numbering at 1 for the second part; assign the section from the list by order
    sec_by_order = [t["section"] for t in list_titles]
    for k, f in enumerate(findings):
        f["section"] = sec_by_order[k] if k < len(sec_by_order) else None
        f["title"] = list_titles[k]["title"] if k < len(list_titles) and list_titles[k]["n"] == f["n"] else f["title_first_line"]
    ok_count = len(list_titles) == len(findings)
    ok_numbers = all(list_titles[k]["n"] == findings[k]["n"] for k in range(min(len(list_titles), len(findings))))
    return {"file": path.name, "idare": name, "year": year, "muni_key": muni_key(name), "pages": len(pages),
            "list_n": len(list_titles), "body_n": len(findings), "list_body_count_match": ok_count,
            "numbering_match": ok_numbers, "findings": findings}


def main() -> int:
    from ihale import config
    root = config.data_dir() / "research" / "sayistay"
    out = root / "findings.jsonl"
    meta = {}
    sp = root / "sample.json"
    if sp.is_file():
        for e in json.loads(sp.read_text(encoding="utf-8"))["sample"]:
            meta[e["path"].rsplit("/", 1)[1] + ".pdf"] = e
    n = 0
    with out.open("w", encoding="utf-8") as fh:
        for p in sorted((root / "cache").glob("*.pdf")):
            try:
                r = extract(p)
                m = meta.get(p.name)
                if m:          # the listing's own name/year is the authoritative link; the PDF cover can be unreadable
                    r["listing_name"], r["listing_year"], r["size"], r["region"] = m["name"], m["year"], m["size"], m["region"]
                    r["year"] = r["year"] or m["year"]
                    r["muni_key"] = muni_key(m["name"])
            except Exception as e:  # noqa: BLE001
                r = {"file": p.name, "error": f"{type(e).__name__}: {e}"}
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
            print(p.name[:60], r.get("body_n"), r.get("list_n"), r.get("error", ""), flush=True)
    print(n, "reports ->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
