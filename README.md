# İhale Gözlemevi

**TR:** Türkiye kamu ihalelerini (EKAP sonuç ilanları) her gün okuyup, sözleşme bedeli, yaklaşık maliyet, geçerli teklif sayısı gibi alanlardan tarafsız işaretler üreten bir kamu yararı gözlem aracı. Kararları değil, olguları gösterir. Ayrıntılar: [`SPEC.md`](SPEC.md), durum: [`PLAN.md`](PLAN.md).

**EN:** A public-interest watchdog over Turkish public procurement. It reads EKAP's daily result bulletins (sonuç ilanları) and computes neutral flags (single valid bid, price vs. estimate, repeat winner). Facts, not verdicts. See [`SPEC.md`](SPEC.md) (source of truth) and [`PLAN.md`](PLAN.md).

## Çalıştırma / Run

Python 3.12+.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Windows; Linux/macOS: .venv/bin/python
.venv/Scripts/python -m ihale fetch --date 18.11.2026 --type mal
```

`--type`: `mal`, `yapim`, `hizmet`, `danismanlik`. Already downloaded bulletins are not downloaded again (`--force` re-downloads).

Veri klasörü / data directory: `%USERPROFILE%\ihaleGozlemevi-data` (override with the `IHALE_DATA_DIR` environment variable). Bulletins land in `<data>/bulletins/<yyyy-mm-dd>/<TYPE>.zip` plus the extracted PDFs. Data is deliberately kept out of the repo and out of OneDrive.

EKAP'a nazik davranılır / polite to EKAP (enforced in `src/ihale/ekap.py`): at least 10 s between any two requests (shared across processes), at most 20 requests per run, sequential downloads, honest `User-Agent`. On HTTP 403/429, a CAPTCHA or a login wall the program stops (exit code 3) and never retries or works around it.

## Testler / Tests

```bash
.venv/Scripts/python -m pytest
```

Tests are fully offline (any network attempt fails the test) and use the small fixtures in `tests/fixtures/`. Bulk bulletins are never committed.

## Yapı / Layout

- `src/ihale/config.py`: data directory
- `src/ihale/ekap.py`: polite EKAP bulletin downloader
- `src/ihale/cli.py`: `python -m ihale <command>` (`fetch` for now; parse, flag, export, build, run come later)
- `docs/bulletin-layout.md`: how the result bulletin PDF is laid out (for the parser)
- `scripts/make_fixture.py`: cuts the fixture PDF from a full bulletin

Lisans / License: see [`LICENSE`](LICENSE).

## Yayın / Deploy (Cloudflare Worker + D1)

The site is one Cloudflare Worker (`site/wrangler.jsonc`, `site/worker/index.js`) with static assets and a D1 database, because the free plan allows only 20,000 asset files per deploy.

- **Core pages** (`/`, `/arsiv/`, `/yontem/`, `/gun/<date>/` summaries, the `/idare/` and `/yuklenici/` index pages, 404, `robots.txt`, `_headers`, CSS) are static assets in `site/dist` (about 45 files).
- **Bulk pages** (`/ihale/<id>/`, `/idare/<slug>/…`, `/yuklenici/<slug>/…`, `/gun/<date>/<n>/`) live in D1 (database `ihale-pages`, binding `PAGES`; tables `pages(path, part, html)` in chunks of 16,000 characters and `page_meta(path, sha, parts, updated)`). The Worker looks the page up, joins its chunks and adds `X-Robots-Tag: noindex, nofollow`; unknown paths get the 404 page with status 404. The path rules live in `src/ihale/sitegen/d1.py` and are mirrored in `worker/index.js` (a test compares them).
- `ihale build` writes the core pages to `site/dist` and stages the bulk pages, with a sha each, in `site/dist-pages.sqlite` (gitignored). The site has one visual direction (`static/sutun.css` tokens plus `static/style.css`); there is no switch or preview build.
- `sitegen.deploy()`:
  1. diffs the staged shas against the manifest of what is already in D1 (`<data>/d1-manifest-remote.json`, or `-local.json` for `--local`),
  2. writes only new or changed pages as SQL batch files (`<data>/d1-batches/`, every statement under 90 KB) and runs `wrangler d1 execute ihale-pages --remote --file=…` per batch,
  3. runs `wrangler deploy` (Worker and assets),
  4. then deletes pages that no longer exist, and updates the manifest after each successful batch, so a failed run can simply be repeated.
  It logs the row count and the stored bytes, and refuses a run that would write more than 90,000 rows (D1 free tier: 100,000 rows written per day; the first full upload is about 30,000 rows and 124 MB, and the free limit per database is 500 MB).
- **One-time setup:** `npx wrangler@4 d1 create ihale-pages`, then paste the printed `database_id` into `site/wrangler.jsonc`. `deploy()` refuses while the placeholder id (all zeros) is still there, and still refuses leftover preview markers (token files, `data-direction`) and the test sample.
- **Local test:** `deploy(local=True)` fills the local D1 only; `python tests/worker_check.py` loads a subset of the real staged pages into it, starts `wrangler dev --local` and checks routing, bodies, status codes and headers.
- **Masking guard:** every yüklenici name on a page sits in `<span class="yk" data-yk>`. Before any upload `deploy()` scans those elements (static pages and the staged bulk pages) and refuses if one shows a name that `is_natural_person()` masks; only a record's own detail page may show such a name, marked `data-yk="own"`. Raw text is deliberately not scanned.
- **Usage warnings:** after a remote deploy it logs the rows written today (tracked in `<data>/d1-usage.json`), the database size (`wrangler d1 info`) and rows read (`wrangler d1 insights`) where available, and at 80% of a free limit (100k rows written/day, 5M rows read/day, 5 GB storage, 500 MB per database) it logs `WARNING` lines and writes `<data>/logs/d1-usage-warning.txt` (removed again when usage is back under 80%).
- **Stop rule:** if any wrangler output asks for a card, a paid plan or a new account, `PaymentRequired` ("STOP: …") is raised and nothing further runs.
- **D1 down:** `/`, `/arsiv/`, `/yontem/` and the other core pages never touch D1; bulk pages answer 503 with a small page if D1 is unavailable.

- **All responses go through the Worker** (`run_worker_first: true`), so static HTML also gets `content-type: text/html; charset=utf-8` and `X-Robots-Tag`; core pages still never read D1.
- `arama-idare.json` (a static asset) feeds the name search on `/idare/`; the Bugün finder (`İl` select and idare-name box) and that search are the only scripts on the live site and stay hidden without JS.
