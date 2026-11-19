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
The old single flag `tek_gecerli_teklif` is split per SPEC §1 "Borrowed from abroad": `tek_teklif` and `diger_teklifler_elendi`. Both depend on `toplam_teklif` and `gecerli_teklif` being confident. `tek_gecerli_teklif` (= either of the two) is still used as the rate for `idare_stats` and the peer comparison.

A flag is computed only when **every input field is confident**. Otherwise the record lists those fields under `unreadable`, and that flag is not computed. Wording is neutral (SPEC §6), and every flag carries its numbers.

| code | condition | text (Turkish, shown on the site) |
|---|---|---|
| `tek_teklif` (OCP R018) | `toplam_teklif == 1` | `Tek teklif verildi` |
| `diger_teklifler_elendi` (OCP R035) | `toplam_teklif > 1` and `gecerli_teklif == 1` | `4 teklif verildi, yalnızca kazananınki geçerli sayıldı` |
| `bedel_orani` | ratio ≥ 0.97 (see below), i.e. ihalent's `low_discount` (kırım < 3%) | `Sözleşme bedeli yaklaşık maliyetin %97'si`; if > 1: `Sözleşme bedeli yaklaşık maliyetin üzerinde (%104)` |
| `tekrarlayan_yuklenici` | the same (idare key, yüklenici key) has ≥ 3 distinct ikns with a bulletin date within the 365 days up to and including this record's | `Bu yüklenici son 12 ayda bu idareden 3 sözleşme aldı (bu dahil)` |

**Ratio for `bedel_orani`:**
- **Estimate:** `esas_kisim_yaklasik_maliyet` if confident, else `yaklasik_maliyet`.
- **Single-record ikn:** ratio = `sozlesme_bedeli` / estimate.
- **ikn with several records (kısmi):** ratio = sum of `sozlesme_bedeli` over all stored records of that ikn, deduped by (ikn, yüklenici key, bedel) / estimate. The text then says `Bu ihalenin N kısmının toplam bedeli yaklaşık maliyetin %97'si`.
- **Currency:** compute only when every bedel's currency equals the estimate's primary currency. Never convert. A mismatch puts `sozlesme_bedeli` under `unreadable` with the reason `para birimi farklı`.
- Store the ratio as a float and round only for display: floor to a whole percent, so 0.999 shows as %99, not %100.

### 4.1 Ranking: compound unusualness (SPEC §1 "Base rates")
Flags alone fire on roughly half of all tenders, and their base rates differ a lot by procedure. For example, tek teklif is 48% in 21/f but 11.6% in açık. So each score part is **weighted by its rarity within the record's procedure**. This is the interim rule until the M5 weight fit.

**Parts.** Each part is computed only if its condition holds and it isn't excluded by §4.1.1:
- `tek_teklif`
- `diger_teklifler_elendi`
- `bedel_orani`
- `tekrarlayan_eslesik`: `tekrarlayan_yuklenici` AND at least one other non-excluded part on the record. A bare repeat earns 0 points, but the flag is still shown.
- `idare_orani`: the idare's tek-geçerli share within its usul_turu is ≥ 2× the share of its per-procedure peers (min n as in Peer comparison).

**Points per part.** points = ln(1 / p), where p is that part's base rate among stored records with the same `usul_turu`.
- If that group has n < 100, use the all-records rate.
- Recompute p on every `flag` run from the whole stored history.
- Floor p at 0.001, so no part exceeds about 6.9 points.

**Score.** The sum of points, a float. Export `score` rounded to 2 decimals and `score_parts` as `[{"code", "points", "p", "p_group"}]`, where `p_group` is the usul_turu used, or `"hepsi"` for the fallback.

**Bugün** shows records with `score ≥ 3.0` (≈ ln 20: at least as rare as a 1-in-20 event), sorted by score, then TRY bedel, with at most 2 cards per idare. The cut-off is provisional. `scripts/base_rates.py` prints each part's p per usul_turu (also shown in Yöntem) and the share of records over the cut-off per usul_turu. The goal is that no single procedure crowds Bugün just by being that procedure.

**Peer comparison.** Every record carries `idare_stats` so the site can show the figure next to its peers, e.g. `Bu idare: 12 ihalenin %80'i tek geçerli teklif · Antalya'daki sağlık idareleri (mal, n=140): %43`.
- **Minimum sample:** no idare-level rate counts (for the score or for display) unless that idare has ≥ 5 awards in the window. Always show n next to every rate.
- **Peer group (cheap proxy).** The bulletin has no sector or province field, so:
  - `idare_turu` comes from keywords in the idare name, checked in order: `BELEDİYE` → belediye, `ÜNİVERSİTE` → üniversite, `HASTANE`/`SAĞLIK` → sağlık, `SU VE KANALİZASYON` → su-kanalizasyon, `JANDARMA`/`EMNİYET`/`POLİS` → güvenlik, `MİLLÎ EĞİTİM`/`MİLLİ EĞİTİM`/`OKUL` → eğitim, `KARAYOLLARI` → karayolları, `DSİ`/`DEVLET SU İŞLERİ` → dsi, else `diğer`.
  - `il` is one of Turkey's 81 province names when exactly one appears in the idare name. Otherwise it is unknown. The yüklenici address is the contractor's province, so never use it.
  - `sector` is the bulletin type (mal/hizmet/yapım).
  - Peers are tried in this order, taking the first group with ≥ 20 awards in the window (excluding the idare itself): same `idare_turu` + `il` + sector, then same `idare_turu` + sector nationwide, then all idares in that sector.
  - The group's Turkish label is exported, so the site never guesses it.
- The Yöntem page explains this proxy and its limits.

### 4.1.1 Structural single-bid table (SPEC §6.1)
Some single-bid patterns have a known structural cause. These are listed in a small table, `src/ihale/structural.py`. They are never hidden special cases. Each entry has:
- `id`
- a match rule: an idare name prefix, Turkish-casefolded, plus a `usul_turu`
- `effects`
- `reason_tr`: one Turkish sentence, shown on the record and in Yöntem
- `added`: a date

Add an entry only together with a stated reason.

The first entry:
- `id`: `dmo-3g`
- match: idare name starts with `DEVLET MALZEME OFİSİ`, with `usul_turu == istisna_3g`
- `reason_tr`: `Devlet Malzeme Ofisi merkezî alım kurumudur; 4734/3-g kapsamındaki seri, markaya özgü alımlarında tek teklif yapısı gereğidir.`
- `effects`:
  - `no_single_bid_points`: the `tek_teklif` and `diger_teklifler_elendi` flags are still shown as facts, but they add no score points. They stay out of `score_parts` and don't count as "another flag" for the tekrarlayan +2.
  - `own_peer_group`: the idare is compared only with its own history. In v1 that means `idare_stats.peer = null`, with `peer_note: "Kendi geçmişiyle karşılaştırılır"`, so `idare_orani` cannot fire. M5 adds drift against its own past.

A second entry, `istisna-3e`, was added 2026-11-19 from the law text, not the rate:
- match: any idare, `usul_turu == istisna_3e`
- effect: `no_single_bid_points`
- reason: `4734 sayılı Kanun md. 3/e: alım, Kanunda adı sayılan kamu kuruluşundan (ör. ceza infaz kurumu işyurtları, DMO, TCDD, Et ve Balık Kurumu) yapılır; tek tedarikçi Kanun gereğidir.`
- `own_peer_group` does not apply.

Every other component still counts: `bedel_orani`, the tekrarlayan pair when combined with a non-excluded flag, and later indicators.

Export:
- Per record: `"structural": {"id": "dmo-3g", "text": "<reason_tr>"}`, or null.
- In `meta.json`: `"structural_rules": [{"id", "match_tr", "effects", "reason_tr", "added"}]`, so Yöntem renders the table from data.

### 4.2 Indicators: stored as values, not yet in the score
From the sonuç fields (SPEC §1 "Borrowed from abroad", GTI and OCP). Computed and exported per record, shown on the detail page with peer medians where n ≥ 5. They are **not added to `score`** until `scripts/base_rates.py` has run on ~30 days of data and the thresholds are chosen.
- `elenen_orani` (OCP R038): `(toplam_teklif - gecerli_teklif) / toplam_teklif` when `toplam_teklif ≥ 2`. Export the peer group's mean too (same peer chain as §4.1, min n ≥ 5).
- `karar_suresi_gun` (GTI decision period): days from `ihale_tarihi` to `sozlesme_tarihi`, only when both are confident and the result is ≥ 0. Negative or absent → null plus a warning.
- `usul_turu`: from the verbatim `ihale_usulu`: `acik` (`Açık`), `belli_istekliler`, `pazarlik_21a` … `pazarlik_21f` (`Pazarlık (MD 21 X)`), `istisna_3x` (`4734 / 3-x`), `dogrudan_temin_22x` if seen, else `diger`. `acik_olmayan` is true for everything except `acik` and `belli_istekliler`.
- `yuklenici_payi` (GTI winner share): this yüklenici's share of the idare's TRY sözleşme bedeli total in the 365-day window up to and including this record. Only when the idare has ≥ 5 awards in the window. Export the share and n.
- `base_rates.py` also prints the distribution of each indicator, by usul_turu and section.

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
   "indicators": {"elenen_orani": 0.0, "elenen_orani_peer": 0.18, "karar_suresi_gun": 26, "usul_turu": "acik", "acik_olmayan": false,
                  "yuklenici_payi": 0.12, "yuklenici_payi_n": 12},
   "idare_stats": {"records": 12, "tek_gecerli_teklif": 0.80, "window_days": 30, "idare_turu": "sağlık", "il": "Antalya",
                   "peer": {"label": "Antalya'daki sağlık idareleri (mal)", "records": 140, "tek_gecerli_teklif": 0.43}}}
 ]}
```
- `id` = `<date>-<type>-<section>-<seq>`. It is URL-safe and stable for that bulletin.
- Every record of the day is included, flagged or not. The site decides what to show.
- Money is a JSON number in major units plus a currency, with an optional `"alt"` for dual figures. Persons' names appear exactly as printed.
- `unreadable` lists the field names whose values were missing or below `CONFIDENT`, plus `{"field": ..., "reason": ...}` objects for reasons such as a currency mismatch.

## 5.1 Oracle candidates (M3, SPEC §9.1 Günün sorusu)
Each `run` writes `<data>/oracle/candidates.json`. It is local only and never deployed or committed. The spec owner appends Efe's answers to `<data>/oracle/log.jsonl`, and the pipeline never writes that file.
```json
{"schema": 1, "date": "2026-11-18", "generated_at": "...",
 "pairs": [
  {"pair_id": "2026-11-18-1",
   "why": "aynı skor (2), farklı işaret karışımı: diger_teklifler_elendi / tek_teklif + bedel_orani",
   "would_change": "diger_teklifler_elendi ağırlığı ile tek_teklif + bedel_orani toplamı arasındaki sıra",
   "question": "Hangisi bir muhabirin zamanına daha çok değer?",
   "a": { ...the full day-export tender object, incl. score, score_parts, indicators, source... },
   "b": { ... }}
 ]}
```
**Selection (deterministic):**
- Candidates are today's records with `1 ≤ score ≤ 3`, which is the band around the Bugün cut-off.
- Form pairs whose scores differ by at most 1 and whose `score_parts` sets differ.
- Prefer pairs whose part sets differ by a single swap, since those isolate one weight. Next, prefer equal scores. Then prefer higher TRY bedel.
- Use each record at most once, and pick 3–5 pairs.
- If fewer than 3 qualify, write what there is, even 0, with `"note"` saying why.
- Don't include any party or political attribution of the idare (§9.1 blinding). We don't have it anyway; never add it.

## 6. Site (M3)
- **Generator:** `ihale.sitegen.build(export_dir: Path, out_dir: Path)`, plain Python with Jinja2. It writes static HTML to `site/dist/`, which is gitignored. Wrangler config is `site/wrangler.jsonc`: an assets-only Worker named `ihale-gozlemevi`.
- **Pages:**
  - `/`: **Bugün**. The latest date's records with `score ≥ 3.0`, ranked by score (§4.1), max 2 per idare, with a one-line summary of counts and the peer comparison on each card.
  - `/gun/<date>/`: every record of that day.
  - `/ihale/<id>/`: **İhale detayı**. All fields, the flags with their numbers, `okunamadı` for unreadable fields, and the source block: `Kamu İhale Bülteni, 18.11.2026, Mal – Sonuç İlanları, s. 18`, with a link to `https://ekap.kik.gov.tr/EKAP/Ilan/BultenIndirme.aspx` and how to download it.
  - `/yontem/`: **Yöntem**. How each flag and the score are computed, and their limits. It credits **ihalent** (MIT, link to github.com/gulmezeren2-byte/ihalent) as the bulletin reader.
  - M4 adds `/idare/<key-slug>/` and `/yuklenici/<key-slug>/`.
- **Unlisted (SPEC §6):**
  - `<meta name="robots" content="noindex, nofollow">` on every page.
  - `robots.txt` with `Disallow: /`.
  - A `_headers` file with `X-Robots-Tag: noindex, nofollow` for `/*`.
  - No analytics and no external links to the site.
