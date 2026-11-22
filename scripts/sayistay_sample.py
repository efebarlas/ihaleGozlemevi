"""Sayıştay experiment (M5e follow-up): fetch a fixed-rule sample of municipality audit reports, PRIVATE use only.

Rule (written to <data>/research/sayistay/NOTES.md BEFORE the first request, then followed mechanically):
  * seed 20261122; the listing is /reports/category/31-belediyeler---bagli-idareler (10 per page, ~324 pages)
  * draw listing pages uniformly at random (seeded, without replacement); fetch them one by one until the pool
    holds enough entries per size stratum or MAX_LISTING_PAGES pages were fetched
  * pool = entries whose name ends with "BELEDİYESİ"; size stratum = büyükşehir (name has BÜYÜKŞEHİR), il merkezi
    (name is exactly "<il> BELEDİYESİ"), ilçe/belde (everything else); region = coğrafi bölge of the il in the name
  * quotas 10 / 6 / 24 (a short stratum's gap goes to ilçe); inside a stratum a greedy pick: fewest picks so far for
    the region, then for the year, then the seeded shuffle order
  * never by name, never by anything seen in the tender data
GET only, one request every 30-60 s, plain non-personal UA, no parallel requests, stop at the first non-200 /
non-expected content, never run 14:00-20:30 Pacific (the EKAP backfill window), PDFs and pages cached, never re-fetched.
"""
from __future__ import annotations

import html
import json
import random
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

SEED = 20261122
BASE = "https://sayistay.gov.tr"
LISTING = BASE + "/reports/category/31-belediyeler---bagli-idareler"
LISTING_PAGES = 324
MAX_LISTING_PAGES = 24
QUOTA = {"buyuksehir": 10, "il": 6, "ilce": 24}
UA = "research-client/0.1 (polite, low-rate, non-commercial)"
MIN_GAP, MAX_GAP = 30.0, 60.0
WINDOW_PT = (14, 20.5)          # local PC time is US Pacific: no requests from 14:00 to 20:30

REGION = {}
for region, provs in {
    "Marmara": "Balıkesir Bilecik Bursa Çanakkale Edirne İstanbul Kırklareli Kocaeli Sakarya Tekirdağ Yalova",
    "Ege": "Afyonkarahisar Aydın Denizli İzmir Kütahya Manisa Muğla Uşak",
    "Akdeniz": "Adana Antalya Burdur Hatay Isparta Kahramanmaraş Mersin Osmaniye",
    "İç Anadolu": "Aksaray Ankara Çankırı Eskişehir Karaman Kırıkkale Kırşehir Konya Nevşehir Niğde Sivas Yozgat Kayseri",
    "Karadeniz": "Amasya Artvin Bartın Bayburt Bolu Çorum Düzce Giresun Gümüşhane Karabük Kastamonu Ordu Rize Samsun Sinop Tokat Trabzon Zonguldak",
    "Doğu Anadolu": "Ağrı Ardahan Bingöl Bitlis Elazığ Erzincan Erzurum Hakkari Iğdır Kars Malatya Muş Tunceli Van",
    "Güneydoğu Anadolu": "Adıyaman Batman Diyarbakır Gaziantep Kilis Mardin Siirt Şanlıurfa Şırnak",
}.items():
    for p in provs.split():
        REGION[p] = region


def tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


PROV_UP = {tr_upper(p): p for p in REGION}


def classify(name: str) -> tuple[str, str | None]:
    """(size stratum, region) from the printed idare name."""
    up = " ".join(name.upper().split())
    prov = next((PROV_UP[w] for w in sorted(PROV_UP, key=len, reverse=True) if up.startswith(w + " ") or up == w), None)
    if "BÜYÜKŞEHİR" in up:
        size = "buyuksehir"
    elif prov and up == f"{tr_upper(prov)} BELEDİYESİ":
        size = "il"
    else:
        size = "ilce"
    return size, REGION.get(prov) if prov else None


def parse_listing(page_html: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<a href="(/reports/[A-Za-z0-9]{10}-[^"]+)">\s*(.*?)\s*<strong>\s*(\d{4})\s*</strong>', page_html, re.S):
        out.append({"path": m.group(1), "name": html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip(),
                    "year": int(m.group(3))})
    return out


class Fetcher:
    def __init__(self, root: Path):
        self.root, self.n, self.last = root, 0, 0.0
        (root / "cache").mkdir(parents=True, exist_ok=True)

    def _in_window(self) -> bool:
        now = datetime.now()
        h = now.hour + now.minute / 60
        return WINDOW_PT[0] <= h < WINDOW_PT[1]

    def get(self, url: str, cache: Path, expect: str) -> bytes:
        if cache.exists():
            return cache.read_bytes()
        if self._in_window():
            raise SystemExit("stop: inside the EKAP backfill window (14:00-20:30 PT); resume after 20:30")
        wait = self.last + random.Random(SEED + self.n).uniform(MIN_GAP, MAX_GAP) - time.time()
        if self.n and wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        self.last = time.time()
        self.n += 1
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body, ctype, status = r.read(), r.headers.get("content-type", ""), r.status
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"stop: request failed ({type(e).__name__}: {e}) for {url}")
        if status != 200 or expect not in ctype:
            raise SystemExit(f"stop: unexpected response {status} {ctype} for {url}")
        if expect == "pdf" and not body.startswith(b"%PDF"):
            raise SystemExit(f"stop: not a PDF for {url}")
        cache.write_bytes(body)
        print(f"{datetime.now():%H:%M:%S} GET {url} -> {len(body)} bytes", flush=True)
        return body


def choose(pool: list[dict]) -> list[dict]:
    rng = random.Random(SEED)
    for e in pool:
        e["size"], e["region"] = classify(e["name"])
    order = sorted(pool, key=lambda e: e["path"])
    rng.shuffle(order)
    picked: list[dict] = []
    quotas = dict(QUOTA)
    have = {s: sum(1 for e in order if e["size"] == s) for s in QUOTA}
    gap = sum(max(0, quotas[s] - have[s]) for s in ("buyuksehir", "il"))
    for s in ("buyuksehir", "il"):
        quotas[s] = min(quotas[s], have[s])
    quotas["ilce"] += gap
    for s in ("buyuksehir", "il", "ilce"):
        cand = [e for e in order if e["size"] == s]
        got: list[dict] = []
        while cand and len(got) < quotas[s]:
            reg = {}
            yr = {}
            for e in got + picked:
                reg[e["region"]] = reg.get(e["region"], 0) + 1
                yr[e["year"]] = yr.get(e["year"], 0) + 1
            best = min(cand, key=lambda e: (reg.get(e["region"], 0), yr.get(e["year"], 0), order.index(e)))
            got.append(best)
            cand.remove(best)
        picked += got
    return picked


def main() -> int:
    from ihale import config
    root = config.data_dir() / "research" / "sayistay"
    root.mkdir(parents=True, exist_ok=True)
    notes = root / "NOTES.md"
    if not notes.exists():
        notes.write_text("# Sayıştay experiment notes\n\n" + (__doc__ or "") + f"\nSeed: {SEED}\nStarted: {datetime.now():%Y-%m-%d %H:%M}\n", encoding="utf-8")
    f = Fetcher(root)
    pages = random.Random(SEED).sample(range(1, LISTING_PAGES + 1), MAX_LISTING_PAGES)
    pool, seen = [], set()
    for k, pg in enumerate(pages):
        body = f.get(LISTING + (f"?page={pg}" if pg > 1 else ""), root / "cache" / f"listing-{pg}.html", "html").decode("utf-8")
        for e in parse_listing(body):
            if e["path"] not in seen and e["name"].upper().endswith("BELEDİYESİ"):
                seen.add(e["path"])
                pool.append(e)
        have = {s: sum(1 for e in pool if classify(e["name"])[0] == s) for s in QUOTA}
        if k >= 5 and have["buyuksehir"] >= QUOTA["buyuksehir"] and have["il"] >= QUOTA["il"] and have["ilce"] >= QUOTA["ilce"]:
            break
    sample = choose(pool)
    (root / "sample.json").write_text(json.dumps({"seed": SEED, "listing_pages_fetched": [p for p in pages[:k + 1]],
                                                  "pool": len(pool), "sample": sample}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"pool {len(pool)}; sample {len(sample)}: " + ", ".join(f"{s}={sum(1 for e in sample if e['size'] == s)}" for s in QUOTA), flush=True)
    for e in sample:
        f.get(BASE + e["path"].replace("/reports/", "/reports/download/", 1), root / "cache" / (e["path"].rsplit("/", 1)[1] + ".pdf"), "pdf")
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
