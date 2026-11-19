# EKAP bulletin layout (for the M1 parser)

Observed on the real **2026-11-18 mal** bulletin (Kamu İhale Bülteni **Sayı 5744**). Everything here was measured on that one day; treat counts as indicative and re-check on other days and on hizmet/yapım.

## 1. What EKAP gives you

`POST BultenIndirme.aspx` returns a zip (served with `Content-Type: text/html` and `Content-Disposition: attachment;filename=BULTEN_18112026_MAL.zip`, so detect it by the `PK` magic, not by content type). The zip contains **two PDFs**:

| file | size | pages | content |
|---|---|---|---|
| `BULTEN_18112026_MAL.pdf` | 3.5 MB | 228 | *İhale ilanları* (announcements of tenders to come). **Not needed** for the watchdog. |
| `BULTEN_18112026_MAL_SONUC.pdf` | 7.4 MB | 464 | **Sonuç ilanları** (award results). This is the parser input. |

Same-day hizmet: `..._HIZMET.pdf` 3.2 MB, `..._HIZMET_SONUC.pdf` 1.8 MB. Yapım: `..._YAPIM.pdf` 1.9 MB, `..._YAPIM_SONUC.pdf` 1.6 MB (page counts not measured). Naming: `BULTEN_{ddmmyyyy}_{TYPE}[_SONUC].pdf`, TYPE in `MAL|HIZMET|YAPIM|DANISMANLIK`.

The PDFs are **born-digital text** (Times New Roman / Arial Narrow embedded TrueType). `pdfplumber` extracts text fine; **no OCR needed**. Page size 595.32 × 842.04 (A4), single column.

## 2. Page structure of `*_MAL_SONUC.pdf`

- p.1: cover (`18 KASIM 2026 – Sayı 5744` only).
- p.2–16: **İÇİNDEKİLER** (table of contents). Heading `MAL ALIMI İHALELERİ BÜLTENİ – Sonuç İlanları`, then section lines, then a table `S.NO İHALE KAYIT NO İŞİN ADI SAYFA` with one row per record, e.g. `1. 2026/1880594 14 KALEM MUHTELİF ÜRÜNLER .......... 17`. Handy for cross-checking the record count; it is **not** needed to parse. The ToC is *not* one row per IKN: the same IKN is listed once per record.
- p.17 → ~p.4xx: the records.
- Last pages: an alphabetical **idare index** (`<İDARE ADI> ......... <page>`), no records. Stop parsing records when no `SONUÇ İLANI` marker is left.
- Every page has a **header** and **footer**:
  - header lines: `KAMU İHALE BÜLTENİ 18 KASIM 2026 – Sayı 5744` and `MAL ALIMI İHALELERİ BÜLTENİ – Sonuç İlanları`. On the first record page of a section they are followed by the section lines (`A- 4734 SAYILI KANUN KAPSAMINDAKİ İLANLAR`, `1. İHALE SONUÇLARININ İLANLARI`, `1.1. MAL ALIMI İHALELERİ BÜLTENİ – Sonuç İlanları`, sometimes printed twice).
  - footer: `Kamu İhale Kurumu – www.kik.gov.tr 18` (the number is the PDF page number, 1-based, same as the PDF page index + 1). It sits at the end of the page text, **in the middle of a record** whenever a record is split.
  - Geometry (pdfplumber, points, page 19): a horizontal rule at `top≈73` (under the header) and one at `top≈793` (above the footer). Crop the body to `73 < top < 793` to drop header and footer without text matching.

### Sections
Two sections, the numbering `1,2,3…` **restarts** in each:

1. `A- 4734 SAYILI KANUN KAPSAMINDAKİ İLANLAR` (pages 17–202; 203 records). Mostly the "long" layout (§3.1), pazarlık and açık ihale.
2. `B- 4734 SAYILI KANUN KAPSAMINDA OLMAYAN İLANLAR (DİĞER İLANLAR)` (from p.203; 423 records). Almost all `Usulü : 4734 / 3-g` etc. (exemptions, "short" layout §3.2).

Total on this day: **626 records**, 162 distinct IKNs.

## 3. Record structure

Each record starts with a fixed 3-line block and ends with `Kamuoyuna saygıyla duyurulur.`:

```
3                                  <- per-section running number, alone on its line
SONUÇ İLANI                        <- record marker (626 occurrences == 626 "Kamuoyuna saygıyla duyurulur.")
3. 2026/1766844 17 KALEM TEMİZLİK MALZEMESİ ALIMI    <- "<no>. <ikn> <title>" (title may wrap to a 2nd line)
17 KALEM TEMİZLİK MALZEMESİ ALIMI                    <- title again, unnumbered (may wrap)
ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ ANTALYA MANAVGAT DEVLET HASTANESİ
BAŞHEKİMLİĞİ                                          <- idare adı: ALL CAPS, 1–3 lines, no label
İhale kayıt numarası : 2026/1766844
1- İhalenin
...
Kamuoyuna saygıyla duyurulur.
```

Record delimiter: split on the regex `\n(?=\d+\nSONUÇ İLANI\n)` (after removing header/footer), or take everything from one `SONUÇ İLANI` to the next. `Kamuoyuna saygıyla duyurulur.` is a safe end marker.

**idare adı has no label.** It is the block of ALL-CAPS lines between the duplicated title and `İhale kayıt numarası`. The title is printed twice (numbered line, then plain), so the first plain title line(s) must be skipped: compare with the numbered line. Wrapped idare names continue on the next line (e.g. `... BAŞHEKİMLİĞİ`).

**ikn**: `İhale kayıt numarası : 2026/1766844` (`YYYY/NNNNNNN`). Variants: a suffix is possible (`2026/1772339-1`, p.84); the year may be older than the bulletin year (`2025/1643181`, p.205) since contracts are published after the tender date. The same ikn at the start of the title line is redundant.

### 3.1 "Long" layout (section A, 202 of 203 records)

Exact labels (verbatim, including the odd `Yerli malı`, `Yüklenicisi`):

```
İhale kayıt numarası : 2026/1880594
1- İhalenin
a) Tarihi : 21.10.2026
b) Türü : Mal alımı
c) Usulü : Pazarlık (MD 21 F)
d) Pazarlık Usulünün Seçilme : İdarelerin yaklaşık maliyeti 4734 sayılı Kanun’un 21’inci     <- only for pazarlık
Gerekçesi maddesinin (f) bendinde ... (label wraps; text continues in the value column)
e) Yaklaşık Maliyeti : 2.894.258,50 TRY            <- letter is d) when there is no "Pazarlık Usulünün Seçilme" row (açık ihale)
f) Sözleşmeye Esas Kısımlarının : 1.015.419,40 TRY  <- only on some records (letter e) or f)); label wraps onto "Yaklaşık Maliyeti"
Yaklaşık Maliyeti
2- İhale konusu malın
a) Adı : 14 Kalem Muhtelif Ürünler
b) Yapılacağı/teslim edileceği yer : Siverek Açık Ceza İnfaz Kurumu Müdürlüğü
c) Teslim tarihi : 01/11/2026-31/12/2026            <- also "Teslim tarihleri"
3- Teklifler
a) Dokümanı EKAP üzerinden : 5
e-imza kullanarak indiren sayısı                    <- label wraps
b) Toplam Teklif Sayısı : 2
c) Toplam Geçerli Teklif Sayısı : 2                 <- the "geçerli teklif sayısı"
d) Yerli malı teklif eden istekli : Uygulanmamıştır
lehine fiyat avantajı uygulaması                    <- label wraps
4- Sözleşmenin
a) Tarihi : 16.11.2026
b) Bedeli : 2.767.200,00 TRY                        <- sözleşme bedeli
c) Süresi : 16.11.2026 - 31.12.2026                 <- may be EMPTY ("c) Süresi :") (p.19)
d) Yüklenicisi : Emir Sosyal Hizmetler ... Limited Şirketi (wraps onto next line)
e) Yüklenicinin uyruğu : Türkiye
f) Yüklenicinin adresi : Selahaddin-i Eyyubi Mahallesi ... (2–3 lines)
Kamuoyuna saygıyla duyurulur.
```

### 3.2 "Short" layout (section B, 423 of 424 short records; one short `Açık` record in section A, p.84)

No pazarlık gerekçesi, no `Dokümanı EKAP üzerinden`, no `Yerli malı…`, no `Yüklenicinin uyruğu`; `Yüklenici` (not `Yüklenicisi`) and a different lettering:

```
İhale kayıt numarası : 2026/2227691
1- İhalenin
a) Tarihi : 16.11.2026
b) Türü : Mal alımı
c) Usulü : 4734 / 3-g
d) Yaklaşık Maliyeti : 3.675.000,00 TRY
2- İhale konusu malın
a) Adı : 1 Ad Kubato U56-5 Mini Ekskavatör (Çelik Paletli 60 cm Yerli
Kova ile)
3- Teklifler
a) Toplam Teklif Sayısı : 1
b) Toplam Geçerli Teklif Sayısı : 1
4- Sözleşmenin
a) Tarihi : 16.11.2026
b) Bedeli : 3.324.800,00 TRY
c) Süresi : 12.11.2026 - 01.12.2026
d) Yüklenici : Kale Makina Pazarlama Anonim Şirketi
e) Yüklenicinin adresi : İstanbul Anadolu Yakası O.S.B. ...
Kamuoyuna saygıyla duyurulur.
```

**Do not key on the letters** (`a)`, `d)` …): they shift between layouts. Key on the label text after the letter.

### Label → field map

| field | label (verbatim) | notes |
|---|---|---|
| ikn | `İhale kayıt numarası` | no letter, no `1-` prefix |
| ihale tarihi | `a) Tarihi` under `1- İhalenin` | `DD.MM.YYYY`. A second `a) Tarihi` exists under `4- Sözleşmenin` (sözleşme tarihi) → scope by the numbered group heading |
| tür | `Türü` | always `Mal alımı` here |
| usul | `Usulü` | observed: `Açık` (149), `Pazarlık (MD 21 B)` (32), `Pazarlık (MD 21 F)` (21), `Pazarlık (MD 21 C)`, `4734 / 3-g` (419), `4734 / 3-a`, `3-b`, `3-e`, `3-f` |
| yaklaşık maliyet | `Yaklaşık Maliyeti` | all 626 records (one is empty); the label also appears as the 2nd line of `Sözleşmeye Esas Kısımlarının / Yaklaşık Maliyeti` (do not confuse) |
| esas kısımların yaklaşık maliyeti | `Sözleşmeye Esas Kısımlarının` (+ wrapped `Yaklaşık Maliyeti`) | 134 records; see kısmi §4 |
| konu | `Adı` under `2- İhale konusu malın` | multi-line, value lines may sit **above and below** the label line (§5) |
| toplam / geçerli teklif | `Toplam Teklif Sayısı`, `Toplam Geçerli Teklif Sayısı` | integer; present on all 626 records |
| sözleşme bedeli | `Bedeli` under `4- Sözleşmenin` | present on all 626; value like `83.000,00 TRY` |
| yüklenici | `Yüklenicisi` (long) / `Yüklenici` (short) | company or **a person's name** (e.g. `Mustafa Öz`, `Yurdakul Bostancı`; KVKK care, SPEC §6) |
| yüklenici adresi | `Yüklenicinin adresi` | 2–3 lines; ends with a repeated `İlçe/İl` token |

## 4. Kısmi (partial) awards and repeated IKNs

A tender awarded in parts / to several contractors is published as **one record per award, repeating the whole header** with the same ikn, idare and `Yaklaşık Maliyeti` but a different `Bedeli` and `Yüklenicisi`:

- ikn `2026/1833735` (19 KALEM TIBBİ SARF MALZEME ALIMI): record 5 (`Bedeli : 83.000,00 TRY`, `Yurdakul Bostancı`) and record 6 (`Bedeli : 250.000,00 TRY`, `Bioart Medikal ...`) with the same `e) Yaklaşık Maliyeti : 10.946.227,50 TRY`, and so on for further lots. Fixture pages 4–6.
- In total 33 ikns repeat; the extreme ones are `2026/1757863` (109 records), `2026/1757890` (100), `2026/1757810` (82), `2026/1757844` (69).
- `Yaklaşık Maliyeti` is therefore the estimate of the **whole tender**, while `Bedeli` is only one lot. **Comparing them naively makes lots look far below the estimate.** Where present, `Sözleşmeye Esas Kısımlarının Yaklaşık Maliyeti` is the estimate of the lots actually contracted; it is not lot-specific either (in the records above it equals the whole-tender estimate). The price/estimate flag must be conservative for repeated ikns (e.g. compare the sum of `Bedeli` over the ikn's records, or skip the flag).
- `Yerli malı teklif eden istekli lehine fiyat avantajı uygulaması` can name lots: `Uygulanmıştır / 1. Kısım, 2. Kısım Kısımlarında %15 (On Beş)`, `Uygulanmıştır / 13.Grup - Temizlik Malzemeleri Kısmında`.
- "single valid bid" must be read per record: the `Toplam Geçerli Teklif Sayısı` of a lot record is the count for the whole tender (it repeats identically) in the samples seen.
- Dedupe key idea: (ikn, yüklenici, bedeli); numbering `N` is not stable across days.

## 5. Oddities the parser must survive

1. **Two-column table rendered as text.** Labels live in a left column (x≈75–240), a `:` sits at **x=242**, values start at **x≈248**. pdfplumber's plain `extract_text()` interleaves them. Facts:
   - Long labels wrap *inside the left column*, so a continuation line looks like `Gerekçesi maddesinin (f) bendinde ...` (label word + value text), or `e-imza kullanarak indiren sayısı` (label continuation **with no value**).
   - Long values wrap on following lines that start at x≈248 (no label), e.g. contractor names, addresses, `Adı`.
   - Vertically-centred labels: the label can be printed **between** value lines, e.g.
     ```
     Hidromek-Hidrolik ve Mekanik Makina İmalat Sanayi ve Ticaret
     d) Yüklenici :
     Anonim Şirketi
     ```
     and for `Adı`:
     ```
     Üniversitemiz Sağlık Uygulama Araştırma Merkezi (Hastane)
     a) Adı :
     İçin 3 Yıl Süreli ... Elektrik Enerjisi Alımı
     ```
     Using word coordinates (split at x≈242: left = label, right = value; group by row) is much more reliable than text lines.
2. **Records split across pages in 441 of 626 cases.** A page ends mid-record (footer in the middle), and the next page begins with header lines then the rest (`c) Usulü : Pazarlık (MD 21 B)` / `d) Pazarlık ...`). Strip header/footer before splitting records; join pages first, then split on `SONUÇ İLANI`.
3. **Empty values:** `d) Yaklaşık Maliyeti :` (1 record, p.84: nothing after the colon) and `c) Süresi :` (empty). Missing ≠ zero.
4. **Currency:** `TRY` almost everywhere; `Bedeli` can be `EUR` (3 records: `230.000,00 EUR`, `154.050,00 EUR`, `594.360,00 EUR`) while the estimate is in TRY, and one estimate is dual: `d) Yaklaşık Maliyeti : 47.407.500,00 TRY (1.072.475,00 EUR)`. **Never divide EUR bedel by a TRY estimate.** Always carry the currency token.
5. **Number format:** Turkish, dot as thousands, comma decimals: `2.894.258,50 TRY`, `3.955,00 TRY`, `99,99 TRY`. Always two decimals; up to 9 integer digits (`999.999.999,99`). Currency token follows after a space.
6. **Dates:** `DD.MM.YYYY` for `Tarihi`; `Teslim tarihi` is free text (`01/11/2026-31/12/2026`, or prose). `Süresi` is `DD.MM.YYYY - DD.MM.YYYY` or empty.
7. **Typographic characters:** `’` in `Kanun’un`, `³` in `20-22 m³`, Turkish `İ ı ş ğ`; mixed case in values (`Bedeli`…) but ALL CAPS for the repeated title and the idare name. The title block sometimes differs in case (`14 KALEM MUHTELİF ÜRÜNLER` vs `14 Kalem Muhtelif Ürünler` in `Adı`).
8. **Contractors that are people:** several `Yüklenicisi` are natural persons (sole proprietors). Show only what the bulletin says (SPEC §6).
9. **Hizmet/yapım** use the same frame but different headings/labels (hizmet: `İhale konusu hizmetin`, yapım: `İhale konusu yapının`, etc., not verified). Check before M4.
10. Idare names wrap across lines and sometimes include two entities; there is no separate "idare kodu".

## 6. Fixture excerpt

`tests/fixtures/mal_sonuc_excerpt.pdf` (12 pages, ~357 KB) was cut with `scripts/make_fixture.py` from pages **17, 18, 19, 20, 21, 22, 84, 85, 203, 204, 205, 257** (1-based) of `BULTEN_18112026_MAL_SONUC.pdf`. Fixture page → what it contains:

| fixture page | source page | records starting on it | notes |
|---|---|---|---|
| 1 | 17 | no. 1 (`2026/1880594`) | section A heading; pazarlık `MD 21 F`, with `Pazarlık Usulünün Seçilme` text |
| 2 | 18 | no. 2, no. 3 | no. 3 (`2026/1766844`) is split onto the next page |
| 3 | 19 | no. 4 | `c) Süresi :` is **empty** for a lot with `Yerli malı ... Uygulanmıştır / %15`; no. 4 continues on fixture page 4 |
| 4–6 | 20–22 | no. 5, 6, 7 (all `2026/1833735`) | kısmi lots of one ikn, each split across a page break; `f) Sözleşmeye Esas Kısımlarının` appears mid-record after a page break (fixture page 6 starts with it) |
| 7–8 | 84–85 | no. 75, 76 (`2026/1772339-1`), 77 | no. 76 is the short `Açık` record: ikn suffix `-1` and an **empty** `d) Yaklaşık Maliyeti :`; also an empty `c) Süresi :` on page 84 |
| 9 | 203 | no. 1, 2 of section B | `B- 4734 SAYILI KANUN KAPSAMINDA OLMAYAN İLANLAR (DİĞER İLANLAR)` heading, numbering restarts at 1, `4734 / 3-g` |
| 10 | 204 | no. 3 | top of page holds the tail of no. 2: wrapped `Yüklenici` with the label between value lines (`Hidromek-...` / `d) Yüklenici :` / `Anonim Şirketi`) |
| 11 | 205 | no. 4 (`2025/1643181`, older ikn year), no. 5 | dual-currency estimate `47.407.500,00 TRY (1.072.475,00 EUR)`; no. 5 is split onto the next page |
| 12 | 257 | no. 90, 91 | no. 90 has `Bedeli : 154.050,00 EUR` (TRY estimate!); no. 91 is cut at the page end |

(The pages in the fixture are verbatim source pages, so the same page-boundary splits show up in the fixture; record 7's and 91's tails are not in the excerpt.)

The fixture pages keep their original header/footer, so the footer page numbers inside the text are source page numbers (17…257). Pages 2 and 464 (ToC, idare index) are *not* included: their fonts alone added ~1 MB.

## 7. Source of the "old" knowledge

From the 2022 code (deleted in M0, still in git history): it parsed the same two-column table with pdfplumber using `explicit_vertical_lines=[0, 243]` (the `:` column at x≈242–243, confirmed above), matched labels fuzzily (thefuzz) after ASCII-folding, and detected result bulletins by the word `sonuc` in the page-2 header. It also assumed the table groups `ihalenin / ihale konusu malın / teklifler / sözleşmenin`, which matches §3. Its field names: `ikn`, `idare adi`, `ihale tarihi`, `ihale turu`, `ihale usulu`, `ihale yaklasik maliyeti`, `esas kisimlarin yaklasik maliyeti`, `mal adi`, `toplam teklif sayisi`, `toplam gecerli teklif sayisi`, `sozlesme tarihi`, `sozlesme bedeli`, `sozlesme suresi`, `yuklenici`, `yuklenici uyruğu`, `yuklenici adresi`. The new parser is free to use better names.

## 8. Hizmet and yapım result bulletins (measured 2026-11-18)

`BULTEN_18112026_HIZMET_SONUC.pdf` (60 pages) and `BULTEN_18112026_YAPIM_SONUC.pdf` (48 pages) have the same frame as mal: one record per `SONUÇ İLANI`, the same two-column form and colon column, the same header/footer rules, and the `A-` / `B-` sections with the numbering restarting. The adapter (`ihale.parse`) reads both without changes; ihalent's own check against the table of contents is complete for both.

| | records | distinct ikn | section A / B | ihalent read / rejected / missing / unlisted | parse time |
|---|---|---|---|---|---|
| hizmet | 65 | 57 | 55 / 10 | 65 / 0 / 0 / 0 (`complete=True`) | ~16 s |
| yapım | 55 | 55 | 51 / 4 | 55 / 0 / 0 / 0 (`complete=True`) | ~16 s |

### What differs from mal
- **Group 2 heading:** `2- İhale konusu hizmetin` (hizmet), `2- İhale konusu yapım işinin` (yapım), instead of `... malın`. Parts stay numbered 1–4, so the adapter keys on the part number and the label.
- **`Türü`:** `Hizmet alımı` / `Yapım işi`.
- **Group 2 fields:** `Adı`, `Yapılacağı yer`, `Süresi` (no `Teslim tarihi`). `Süresi` here is free text: `12 aydır`, `45 gündür` in hizmet, a bare day count (`45`, `300`) in yapım. It is *not* the contract `Süresi` in group 4. Both land in `raw_fields` only.
- **Group 3 (section A):** `Dokümanı EKAP üzerinden e-imza kullanarak indiren sayısı`, `Toplam Teklif Sayısı`, `Toplam Geçerli Teklif Sayısı`, then `Yerli istekli lehine fiyat avantajı uygulaması` (mal says `Yerli malı teklif eden istekli ...`). Section B has only the two counts.
- **Yüklenici label:** hizmet always prints `Yüklenici` (also in section A, unlike mal's `Yüklenicisi`). Yapım prints `Yüklenicisi` in section A (51 records) and `Yüklenici` in section B (4). The adapter accepts both. `Yüklenicinin uyruğu` exists only in the long (section A) layout.
- **Section B** is the short layout (no gerekçe, no document count, no uyruk) and is headed `B- 4734 SAYILI KANUN KAPSAMINDA OLMAYAN İLANLAR (DİĞER İLANLAR)` / `1. İSTİSNA SONUÇLARININ İLANLARI`; yapım continues with `2. KAPSAM DIŞI SONUÇLARININ İLANLARI` and the line `Bu sayıda "Kapsam Dışı Sonuçlarının İlanı" bulunmamaktadır.` (no records), which the parser must not read as a record.
- **Usul values seen:** hizmet `Açık` (38), `Pazarlık (MD 21 F)` (13), `Pazarlık (MD 21 B)` (4), `4734 / 3-g` (9), `4734 / 3-i` (1); yapım `Açık` (45), `Pazarlık (MD 21 B)` (6), `4734 / 3-i` (3), `4734 / 3-k (5737/79 md.)` (1; the parenthesis is part of the value). The `Pazarlık Usulünün Seçilme Gerekçesi` text is printed for every pazarlık record.
- **Estimate:** printed as in mal (`Yaklaşık Maliyeti : 1.391.000,00 TRY`), always present on these two days (no empty or "bulunmamaktadır" case). In yapım, `Pazarlık (MD 21 B)` records print a stray ` -->` after the amount in the PDF text (`229.985.668,10 TRY -->`); ihalent removes it before the value reaches us.
- **Kısmi lots:** `Sözleşmeye Esas Kısımlarının Yaklaşık Maliyeti` appears in 17 of 65 hizmet records and 2 of 55 yapım records, with the same repeated-header structure as mal §4 (hizmet ikns repeat up to 5 times, e.g. `2026/1765500`).
- **Currency:** hizmet has one `USD` bedel (B-5, `138.107,00 USD`, TRY estimate); no EUR, no dual-currency estimate, in either type that day. Bedel above the estimate occurs in 2 hizmet and 2 yapım records.
- **Empty `Süresi` (contract, group 4):** 15 of 65 hizmet and 32 of 55 yapım records (yapım prints it empty far more often than mal).
- **Joint ventures (yapım):** the contractor is one cell with the partners separated by a comma and a final `İş Ortaklığı`, e.g. `MAŞ İnşaat Sanayi ve Ticaret Anonim Şirketi, Ersin Başak İş Ortaklığı`, or two companies, or a company plus a person (`Mehmet Özen, ASN ... Şirketi İş Ortaklığı`). 4 of 55 yapım records; none in hizmet. `Record.yuklenici` keeps the full string. Do not split on the comma: company names themselves contain commas (`Genç Grup Danışmanlık, Çevre, Mühendislik, ... Limited Şirketi`). ihalent's `Award` splits JVs, and that cuts the name to the first partner; the adapter does not use `Award`.
- **Odd identifiers:** a six-digit ikn (`2026/763412`, yapım B-2); a contractor name starting with digits (`111 İnşaat ...`) or containing initials (`Osman Kutanoğlu HG Yapı İnşaat Taahhüt`); a typo printed in the source (hizmet A-17: `Fresenıus` with a dotless ı), so text must be compared verbatim, not "corrected".
- **Heading block above the record:** the first page of a section has the section lines directly above the record number (hizmet p.5, p.51; yapım p.4, p.44), and some records have 3–4 line titles; the title/idare split by the repeated title still works.
