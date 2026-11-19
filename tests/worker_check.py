"""Manual check of site/worker/index.js against a local D1 (`wrangler dev --local`). Not collected by pytest
(needs npx and the real build): python tests/worker_check.py  (run `ihale build` first).

Loads a subset of the real staged bulk pages into the LOCAL D1 with the same sync code as deploy(), starts the
Worker locally, and checks routing, bodies (byte for byte), status codes and headers.
"""
from __future__ import annotations

import http.client
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ihale import sitegen  # noqa: E402
from ihale.sitegen import d1  # noqa: E402

SITE = ROOT / "site"
PORT = 8787


def pick(db: sqlite3.Connection) -> list[str]:
    out = []
    for prefix, n in (("/ihale/", 3), ("/gun/", 2)):
        out += [r[0] for r in db.execute("SELECT path FROM staged WHERE path LIKE ? ORDER BY path LIMIT ?", (prefix + "%", n))]
    for prefix in ("/idare/", "/yuklenici/"):
        rows = db.execute("SELECT path, length(html) FROM staged WHERE path LIKE ? ORDER BY length(html) DESC LIMIT 1", (prefix + "%",)).fetchall()
        out += [r[0] for r in rows]
        out += [r[0] for r in db.execute("SELECT path FROM staged WHERE path LIKE ? ORDER BY path LIMIT 1", (prefix + "%",))]
    # a second page of a long dossier (pagination path), if there is one
    out += [r[0] for r in db.execute("SELECT path FROM staged WHERE path GLOB '/idare/*/2/' ORDER BY path LIMIT 1")]
    return sorted(set(out))


def get(method: str, path: str):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    c.request(method, path)
    r = c.getresponse()
    body = r.read()
    h = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, h, body


def main() -> int:
    stage = d1.staging_path(SITE / "dist")
    assert stage.is_file(), "run `ihale build` first"
    src = sqlite3.connect(stage)
    paths = pick(src)
    tmp = Path(tempfile.mkdtemp(prefix="d1check-"))
    sub = d1.Stage(tmp / "subset.sqlite")
    for p in paths:
        sub.add(p, src.execute("SELECT html FROM staged WHERE path=?", (p,)).fetchone()[0])
    sub.close()
    print("subset:", len(paths), "pages;", "parts per page:", {p: len(d1.chunks(d1.staged_html(tmp / "subset.sqlite", p))) for p in paths})

    # load into the local D1 exactly like deploy(local=True)
    d1.sync_pages(stage_db=tmp / "subset.sqlite", manifest_path=tmp / "m.json", batch_dir=tmp / "b",
                  execute=lambda f: sitegen._run_wrangler(["d1", "execute", sitegen.D1_NAME, "--local", f"--file={f}"]),
                  updated="check", log=print)

    npx = sitegen._npx()
    env = dict(os.environ, npm_config_registry="https://registry.npmjs.org/")
    proc = subprocess.Popen([npx, "--yes", "wrangler@4", "dev", "--local", "--port", str(PORT), "--ip", "127.0.0.1"], cwd=SITE,
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    fails = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
        if not ok:
            fails.append(name)

    try:
        for _ in range(120):
            time.sleep(1)
            try:
                get("GET", "/robots.txt")
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError("wrangler dev exited early")
        for p in paths:
            st, h, body = get("GET", p)
            expect = d1.staged_html(tmp / "subset.sqlite", p).encode("utf-8")
            check(f"GET {p}", st == 200 and body == expect, f"{st}, {len(body)} bytes, parts={len(d1.chunks(expect.decode()))}")
            if p == paths[0]:
                check("content-type", h.get("content-type") == "text/html; charset=utf-8", h.get("content-type"))
                check("X-Robots-Tag", h.get("x-robots-tag") == "noindex, nofollow", h.get("x-robots-tag"))
                check("cache-control", "max-age" in (h.get("cache-control") or ""), h.get("cache-control"))
            # no trailing slash -> redirect to the slash form
            st2, h2, _ = get("GET", p.rstrip("/"))
            check(f"redirect {p.rstrip('/')}", st2 == 308 and h2.get("location", "").endswith(p), f"{st2} {h2.get('location')}")
        multi = max(paths, key=lambda p: len(d1.staged_html(tmp / "subset.sqlite", p)))
        check("multi-chunk page spans several parts", len(d1.chunks(d1.staged_html(tmp / "subset.sqlite", multi))) >= 3, multi)
        st, h, body = get("HEAD", paths[0])
        check("HEAD bulk page", st == 200 and body == b"" and h.get("x-robots-tag") == "noindex, nofollow", f"{st}, {len(body)} bytes")
        # static pass-through
        for p, needle in (("/", b"<h1>"), ("/yontem/", b"Y\xc3\xb6ntem"), ("/arsiv/", b"Ar\xc5\x9fiv"), ("/idare/", b"\xc4\xb0dareler")):
            st, h, body = get("GET", p)
            check(f"static {p}", st == 200 and needle in body and h.get("x-robots-tag") == "noindex, nofollow", f"{st}, {len(body)} bytes")
        day = next(p for p in sorted(Path(SITE / "dist" / "gun").iterdir()))
        st, h, body = get("GET", f"/gun/{day.name}/")
        check("static /gun/<date>/ summary", st == 200 and b"Sayfalar" in body, f"{st}")
        st, h, body = get("GET", "/robots.txt")
        check("robots.txt", st == 200 and b"Disallow: /" in body)
        # unknown paths
        for p in ("/ihale/yok-boyle-bir-kayit/", "/idare/yok/", "/yuklenici/yok/7/", "/gun/2000-01-01/3/", "/hic-yok/", "/idare/liste/9999/"):
            st, h, body = get("GET", p)
            check(f"404 {p}", st == 404 and b"Sayfa bulunamad" in body and h.get("x-robots-tag") == "noindex, nofollow"
                  and h.get("content-type", "").startswith("text/html"), f"{st}, {len(body)} bytes")
        st, h, body = get("POST", paths[0])
        check("POST -> 405", st == 405 and h.get("x-robots-tag") == "noindex, nofollow", str(st))
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    print("\n%d failure(s)" % len(fails))
    return 1 if fails else 0


def d1_down() -> int:
    """Core pages must load with D1 unavailable: run the Worker against an EMPTY local D1 (no tables, so every query
    throws) and check that static pages are 200 while bulk pages answer 503 (not a crash)."""
    tmp = Path(tempfile.mkdtemp(prefix="d1down-"))
    npx = sitegen._npx()
    env = dict(os.environ, npm_config_registry="https://registry.npmjs.org/")
    proc = subprocess.Popen([npx, "--yes", "wrangler@4", "dev", "--local", "--port", str(PORT), "--ip", "127.0.0.1",
                             "--persist-to", str(tmp / "state")], cwd=SITE, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    fails = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
        if not ok:
            fails.append(name)
    try:
        for _ in range(120):
            time.sleep(1)
            try:
                get("GET", "/robots.txt")
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError("wrangler dev exited early")
        for p, needle in (("/", b"<h1>"), ("/yontem/", b"Y\xc3\xb6ntem"), ("/arsiv/", b"Ar\xc5\x9fiv"), ("/idare/", b"\xc4\xb0dareler")):
            st, h, body = get("GET", p)
            check(f"D1 down: static {p}", st == 200 and needle in body, f"{st}, {len(body)} bytes")
        day = next(p for p in sorted(Path(SITE / "dist" / "gun").iterdir()))
        st, h, body = get("GET", f"/gun/{day.name}/")
        check("D1 down: /gun/<date>/ summary", st == 200, str(st))
        for p in ("/ihale/2026-10-21-mal-A-1/", "/idare/x/", "/yuklenici/x/", "/gun/2026-10-21/1/"):
            st, h, body = get("GET", p)
            check(f"D1 down: bulk {p} -> 503", st == 503 and h.get("x-robots-tag") == "noindex, nofollow"
                  and "Bugün".encode() in body, f"{st}, {len(body)} bytes")
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    print("\n%d failure(s) with D1 down" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    rc = main()
    rc |= d1_down()
    raise SystemExit(rc)
