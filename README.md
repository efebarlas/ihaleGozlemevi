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

Veri klasörü / data directory: `%LOCALAPPDATA%\ihaleGozlemevi` (override with the `IHALE_DATA_DIR` environment variable). Bulletins land in `<data>/bulletins/<yyyy-mm-dd>/<TYPE>.zip` plus the extracted PDFs. Data is deliberately kept out of the repo and out of OneDrive.

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
