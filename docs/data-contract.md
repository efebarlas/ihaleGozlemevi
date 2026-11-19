# Data contract: parse → store/flag → export → site

Owner: the orchestrator. Builders implement against this. If it's wrong, report it rather than silently diverging. Python types are in `src/ihale/model.py`.

## 1. Parser output (M1)
`ihale.parse.parse_bulletin(pdf_path: Path, bulletin_date: date, bulletin_type: str) -> list[Record]`

- One `Record` per `SONUÇ İLANI`, in document order. Field semantics are in `model.py`; the layout facts are in `docs/bulletin-layout.md`.
- **Confidence** is per field, in [0, 1]:
  - Use ≥ `CONFIDENT` (0.9) only when the label was found in the right group and the value matched its expected shape. Shapes: `YYYY/NNNNNNN[-n]` for ikn; `1.234,56 CUR` for money; an integer for counts; `DD.MM.YYYY` for dates; non-empty text for names.
  - An empty value after the colon means the field is `None` with confidence 1.0 for "known empty". Downstream treats `None` as unusable either way.
- The parser never raises on a bad record. It records `warnings` and lowers the confidence.

## 2. Store (M2)
- SQLite at `ihale.config.db_path()`. One table of records, holding every `Record` field plus the confidence as JSON. Money is stored as an integer kuruş amount and a currency.
- Re-running the same bulletin is idempotent: the natural key is `(bulletin_date, bulletin_type, section, seq)`.
- Keep a `runs` table: date, type, record count, warning count, and parse accuracy where known.

## 3. Normalized keys
Each idare and yüklenici has a `key` used for grouping, built as follows:
- Turkish-aware lowercasing (`İ→i`, `I→ı`).
- Unicode NFC.
- Collapse whitespace, and strip punctuation except `&`.
- Normalize the common company suffixes (`limited şirketi`/`ltd. şti.` → `ltd`, `anonim şirketi`/`a.ş.` → `as`, `sanayi ve ticaret`/`san. ve tic.` → `san tic`).

Be conservative: a false merge is worse than a missed one. No fuzzy matching in v1. Persons' names are keyed the same way and are never enriched (SPEC §6).

## 4. Flags (v1)
A flag is computed only when **every input field is confident**. Otherwise the record lists those fields under `unreadable`, and that flag is not computed. Wording is neutral (SPEC §6), and every flag carries its numbers.

| code | condition | text (Turkish, shown on the site) |
|---|---|---|
| `tek_gecerli_teklif` | `gecerli_teklif == 1` | `Tek geçerli teklif` (also show `toplam_teklif` when > 1: `2 teklif, 1 geçerli`) |
| `bedel_orani` | ratio ≥ 0.95 (see below) | `Sözleşme bedeli yaklaşık maliyetin %97'si`; if > 1: `Sözleşme bedeli yaklaşık maliyetin üzerinde (%104)` |
| `tekrarlayan_yuklenici` | the same (idare key, yüklenici key) has ≥ 3 distinct ikns with a bulletin date within the 365 days up to and including this record's | `Bu yüklenici son 12 ayda bu idareden 3 sözleşme aldı (bu dahil)` |

**Ratio for `bedel_orani`:**
- **Estimate:** `esas_kisim_yaklasik_maliyet` if confident, else `yaklasik_maliyet`.
- **Single-record ikn:** ratio = `sozlesme_bedeli` / estimate.
- **ikn with several records (kısmi):** ratio = sum of `sozlesme_bedeli` over all stored records of that ikn, deduped by (ikn, yüklenici key, bedel) / estimate. The text then says `Bu ihalenin N kısmının toplam bedeli yaklaşık maliyetin %97'si`.
- **Currency:** compute only when every bedel's currency equals the estimate's primary currency. Never convert. A mismatch puts `sozlesme_bedeli` under `unreadable` with the reason `para birimi farklı`.
- Store the ratio as a float and round only for display: floor to a whole percent, so 0.999 shows as %99, not %100.

`tekrarlayan_yuklenici` needs history, so it becomes meaningful once ~30 days of bulletins are loaded (a small backfill in M2/M3, full backfill in M5).

## 5. Export (M2) → site input
Written under `<data>/export/`, UTF-8, `ensure_ascii=False`.

`meta.json`
```json
{"schema": 1, "generated_at": "2026-11-18T21:30:00+03:00", "latest_date": "2026-11-18",
 "dates": ["2026-11-18", "2026-11-17"],
 "counts": {"2026-11-18": {"records": 626, "flagged": 240, "tek_gecerli_teklif": 200, "bedel_orani": 60, "tekrarlayan_yuklenici": 5, "unreadable": 4}}}
```

`days/<YYYY-MM-DD>.json`
```json
{"schema": 1, "date": "2026-11-18", "types": ["mal"],
 "tenders": [
  {"id": "2026-11-18-mal-A-3",
   "ikn": "2026/1766844", "title": "17 KALEM TEMİZLİK MALZEMESİ ALIMI", "konu": "17 Kalem Temizlik Malzemesi Alımı",
   "type": "mal", "section": "A", "usul": "Açık", "tur": "Mal alımı",
   "idare": {"name": "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ ANTALYA MANAVGAT DEVLET HASTANESİ BAŞHEKİMLİĞİ", "key": "antalya il sağlık ..."},
   "yuklenici": {"name": "Emir Sosyal Hizmetler ... Limited Şirketi", "key": "emir sosyal hizmetler ... ltd"},
   "ihale_tarihi": "2026-10-21", "sozlesme_tarihi": "2026-11-16", "sozlesme_suresi": "16.11.2026 - 31.12.2026",
   "yaklasik_maliyet": {"amount": 2894258.50, "currency": "TRY"},
   "esas_kisim_yaklasik_maliyet": null,
   "sozlesme_bedeli": {"amount": 2767200.00, "currency": "TRY"},
   "toplam_teklif": 2, "gecerli_teklif": 2,
   "kisim": {"records_in_ikn": 1},
   "source": {"date": "2026-11-18", "type": "mal", "file": "BULTEN_18112026_MAL_SONUC.pdf", "page": 18},
   "unreadable": [],
   "flags": [{"code": "bedel_orani", "value": 0.956, "text": "Sözleşme bedeli yaklaşık maliyetin %95'i"}]}
 ]}
```
- `id` = `<date>-<type>-<section>-<seq>`. It is URL-safe and stable for that bulletin.
- Every record of the day is included, flagged or not. The site decides what to show.
- Money is a JSON number in major units plus a currency, with an optional `"alt"` for dual figures. Persons' names appear exactly as printed.
- `unreadable` lists the field names whose values were missing or below `CONFIDENT`, plus `{"field": ..., "reason": ...}` objects for reasons such as a currency mismatch.

## 6. Site (M3)
- **Generator:** `ihale.sitegen.build(export_dir: Path, out_dir: Path)`, plain Python with Jinja2. It writes static HTML to `site/dist/`, which is gitignored. Wrangler config is `site/wrangler.jsonc`: an assets-only Worker named `ihale-gozlemevi`.
- **Pages:**
  - `/`: **Bugün**. The latest date's flagged records, with a one-line summary of counts.
  - `/gun/<date>/`: every record of that day.
  - `/ihale/<id>/`: **İhale detayı**. All fields, the flags with their numbers, `okunamadı` for unreadable fields, and the source block: `Kamu İhale Bülteni, 18.11.2026, Mal – Sonuç İlanları, s. 18`, with a link to `https://ekap.kik.gov.tr/EKAP/Ilan/BultenIndirme.aspx` and how to download it.
  - `/yontem/`: **Yöntem**. How each flag is computed and its limits.
  - M4 adds `/idare/<key-slug>/` and `/yuklenici/<key-slug>/`.
- **Unlisted (SPEC §6):**
  - `<meta name="robots" content="noindex, nofollow">` on every page.
  - `robots.txt` with `Disallow: /`.
  - A `_headers` file with `X-Robots-Tag: noindex, nofollow` for `/*`.
  - No analytics and no external links to the site.
