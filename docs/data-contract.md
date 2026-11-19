# Data contract: parse → store/flag → export → site

Owner: the orchestrator. Updated 2026-11-19 for SPEC §4.1 (build on ihalent) and §1 (base rates, ranking). Builders implement against this. If it's wrong, report it rather than silently diverging. Python types are in `src/ihale/model.py`.

## 1. Parser output (M1)
`ihale.parse.parse_bulletin(pdf_path: Path, bulletin_date: date, bulletin_type: str) -> list[Record]`

- **Built on ihalent** (SPEC §4.1). `ihalent==0.5.1` is pinned, MIT. `ihale.parse` is a thin adapter: `ihalent.bulletin.read_bulletin_saved()` → `BulletinNotice`s → our `Record`s.
  - Fix shortfalls in the adapter, using the notice's raw `(part, label, value)` fields. Fork ihalent only if a wrapper can't fix them.
  - A notice ihalent rejects still becomes a `Record`, with whatever is recoverable, low confidence and a warning, so the day's count stays honest.
  - Map ihalent's `section` ("4734" → `A`; "istisna"/"kapsam-disi" → `B`) and derive `seq` from document order within the section. Document the mapping in `parse.py`.
- One `Record` per `SONUÇ İLANI`, in document order.
- `raw_fields` keeps every printed `(part, label, value)` triple verbatim. M5/M6 need fields we don't model yet, such as `niteliği, türü ve miktarı` and the pazarlık gerekçesi, and re-parsing years of bulletins later would be wasteful. `ihale_usulu` stays verbatim (e.g. `Pazarlık (MD 21 B)`), so 21/b can be counted later. Field semantics are in `model.py`; the layout facts are in `docs/bulletin-layout.md`.
- **Confidence** is per field, in [0, 1]:
  - Use ≥ `CONFIDENT` (0.9) only when the label was found in the right group and the value matched its expected shape. Shapes: `YYYY/NNNNNNN[-n]` for ikn; `1.234,56 CUR` for money; an integer for counts; `DD.MM.YYYY` for dates; non-empty text for names.
  - An empty value after the colon means the field is `None` with confidence 1.0 for "known empty". Downstream treats `None` as unusable either way.
- The parser never raises on a bad record. It records `warnings` and lowers the confidence.

## 1.1 İlan bulletins (kept for M6)
Each day's zip also holds the *ilan* (tender notice) PDF, `BULTEN_<ddmmyyyy>_<TYPE>.pdf`. It prints `Niteliği, türü ve miktarı` (e.g. `2.500.000 Litre Motorin`), which M6 joins to sonuç records by ikn for unit prices.
- Never delete the zips or the extracted ilan PDFs from the data dir. Backfill keeps them too.
- Parsing ilan notices into raw fields keyed by ikn is M6 work: ihalent reads only `*_SONUC.pdf`.

## 2. Store (M2)
- SQLite at `ihale.config.db_path()`. One table of records, holding every `Record` field plus the confidence as JSON. Money is stored as an integer kuruş amount and a currency.
- Re-running the same bulletin is idempotent: the natural key is `(bulletin_date, bulletin_type, section, seq)`.
- `raw_fields` is stored as JSON alongside each record.
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
| `bedel_orani` | ratio ≥ 0.97 (see below), i.e. ihalent's `low_discount` (kırım < 3%) | `Sözleşme bedeli yaklaşık maliyetin %97'si`; if > 1: `Sözleşme bedeli yaklaşık maliyetin üzerinde (%104)` |
| `tekrarlayan_yuklenici` | the same (idare key, yüklenici key) has ≥ 3 distinct ikns with a bulletin date within the 365 days up to and including this record's | `Bu yüklenici son 12 ayda bu idareden 3 sözleşme aldı (bu dahil)` |

**Ratio for `bedel_orani`:**
- **Estimate:** `esas_kisim_yaklasik_maliyet` if confident, else `yaklasik_maliyet`.
- **Single-record ikn:** ratio = `sozlesme_bedeli` / estimate.
- **ikn with several records (kısmi):** ratio = sum of `sozlesme_bedeli` over all stored records of that ikn, deduped by (ikn, yüklenici key, bedel) / estimate. The text then says `Bu ihalenin N kısmının toplam bedeli yaklaşık maliyetin %97'si`.
- **Currency:** compute only when every bedel's currency equals the estimate's primary currency. Never convert. A mismatch puts `sozlesme_bedeli` under `unreadable` with the reason `para birimi farklı`.
- Store the ratio as a float and round only for display: floor to a whole percent, so 0.999 shows as %99, not %100.

### 4.1 Ranking: compound unusualness (SPEC §1 "Base rates")
Flags alone fire on roughly half of all tenders, so Bugün ranks by a transparent `score`, an integer sum of these parts:
- +1 `tek_gecerli_teklif`
- +1 `bedel_orani`
- +2 `tekrarlayan_yuklenici` when this record also has at least one of the two flags above (a repeat pair inside flagged tenders). A bare repeat adds +0, but the flag is still shown.
- +1 `idare_orani`: the idare has ≥ 5 records in the window, and its share of `tek_gecerli_teklif` is ≥ 2× its peer group's share (see Peer comparison below).

Bugün shows records with `score ≥ 2`, sorted by score, then sözleşme bedeli (TRY). Thresholds are provisional. `scripts/base_rates.py` prints the measured base rates from the DB (share of tek teklif, bedel ≥ 0.97, repeat pairs, per usul and section). Revisit the thresholds once ~30 days are loaded.

**Peer comparison.** Every record carries `idare_stats` so the site can show the figure next to its peers, e.g. `Bu idare: 12 ihalenin %80'i tek geçerli teklif · Antalya'daki sağlık idareleri (mal, n=140): %43`.
- **Minimum sample:** no idare-level rate counts (for the score or for display) unless that idare has ≥ 5 awards in the window. Always show n next to every rate.
- **Peer group (cheap proxy).** The bulletin has no sector or province field, so:
  - `idare_turu` comes from keywords in the idare name, checked in order: `BELEDİYE` → belediye, `ÜNİVERSİTE` → üniversite, `HASTANE`/`SAĞLIK` → sağlık, `SU VE KANALİZASYON` → su-kanalizasyon, `JANDARMA`/`EMNİYET`/`POLİS` → güvenlik, `MİLLÎ EĞİTİM`/`MİLLİ EĞİTİM`/`OKUL` → eğitim, `KARAYOLLARI` → karayolları, `DSİ`/`DEVLET SU İŞLERİ` → dsi, else `diğer`.
  - `il` is one of Turkey's 81 province names when exactly one appears in the idare name. Otherwise it is unknown. The yüklenici address is the contractor's province, so never use it.
  - `sector` is the bulletin type (mal/hizmet/yapım).
  - Peers are tried in this order, taking the first group with ≥ 20 awards in the window (excluding the idare itself): same `idare_turu` + `il` + sector, then same `idare_turu` + sector nationwide, then all idares in that sector.
  - The group's Turkish label is exported, so the site never guesses it.
- The Yöntem page explains this proxy and its limits.

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
   "flags": [{"code": "bedel_orani", "value": 0.976, "text": "Sözleşme bedeli yaklaşık maliyetin %97'si"}],
   "score": 1, "score_parts": ["bedel_orani"],
   "idare_stats": {"records": 12, "tek_gecerli_teklif": 0.80, "window_days": 30, "idare_turu": "sağlık", "il": "Antalya",
                   "peer": {"label": "Antalya'daki sağlık idareleri (mal)", "records": 140, "tek_gecerli_teklif": 0.43}}}
 ]}
```
- `id` = `<date>-<type>-<section>-<seq>`. It is URL-safe and stable for that bulletin.
- Every record of the day is included, flagged or not. The site decides what to show.
- Money is a JSON number in major units plus a currency, with an optional `"alt"` for dual figures. Persons' names appear exactly as printed.
- `unreadable` lists the field names whose values were missing or below `CONFIDENT`, plus `{"field": ..., "reason": ...}` objects for reasons such as a currency mismatch.

## 6. Site (M3)
- **Generator:** `ihale.sitegen.build(export_dir: Path, out_dir: Path)`, plain Python with Jinja2. It writes static HTML to `site/dist/`, which is gitignored. Wrangler config is `site/wrangler.jsonc`: an assets-only Worker named `ihale-gozlemevi`.
- **Pages:**
  - `/`: **Bugün**. The latest date's records with `score ≥ 2`, ranked by score (§4.1), with a one-line summary of counts and the peer comparison on each card.
  - `/gun/<date>/`: every record of that day.
  - `/ihale/<id>/`: **İhale detayı**. All fields, the flags with their numbers, `okunamadı` for unreadable fields, and the source block: `Kamu İhale Bülteni, 18.11.2026, Mal – Sonuç İlanları, s. 18`, with a link to `https://ekap.kik.gov.tr/EKAP/Ilan/BultenIndirme.aspx` and how to download it.
  - `/yontem/`: **Yöntem**. How each flag and the score are computed, and their limits. It credits **ihalent** (MIT, link to github.com/gulmezeren2-byte/ihalent) as the bulletin reader.
  - M4 adds `/idare/<key-slug>/` and `/yuklenici/<key-slug>/`.
- **Unlisted (SPEC §6):**
  - `<meta name="robots" content="noindex, nofollow">` on every page.
  - `robots.txt` with `Disallow: /`.
  - A `_headers` file with `X-Robots-Tag: noindex, nofollow` for `/*`.
  - No analytics and no external links to the site.
