# Hand-labeled accuracy sample (M1 parser, SPEC §5)

`mal_2026-11-18.json` holds 69 hand-labeled records from the 2026-11-18 mal sonuç bulletin
(`BULTEN_18112026_MAL_SONUC.pdf`, Kamu İhale Bülteni Sayı 5744, 464 pages, 626 records).
It is the ground truth for the SPEC §5 accuracy gate (>= 95 % field accuracy on the core fields
`ikn`, `idare`, `yuklenici`, `sozlesme_bedeli`, `yaklasik_maliyet`, `gecerli_teklif`).

## Rule for parser builders

**Never edit a label to make a test pass.** If the parser disagrees with a label, a human re-checks
the page (render it, look at it) and only then the label may change, in a commit that says which page
and why. The labels are deliberately independent of `src/ihale/parse.py`.

## How the labels were made

- **Method:** read visually from rendered page images. No label-extraction regex or parser was written,
  and `src/ihale/parse.py` was never read or run.
- **Renderer:** `pdfplumber` `page.crop((0, 70, 595.32, 800)).to_image(resolution=150)` (pypdfium2 under the
  hood), one PNG per page, kept outside the repo. The crop only removes the running header and footer.
- **Navigation only:** pdfplumber page text was used to find *which pages* hold which kind of record
  (seq numbers, usul, EUR amounts, repeated ikns). Values were then read off the images.
- **Text cross-check (after labeling):** the pdfplumber text was used only to double-check what had been read:
  that every ikn, amount, count and usul equals the printed value in the record's own text span, and
  that every idare / yüklenici string occurs verbatim in the page text. It did not produce any label.
- **Format:** amounts are decimal strings in major units (`2.894.258,50` -> `"2894258.50"`); a dual estimate
  keeps the TRY figure plus `"alt"` (EUR); an empty field is `null`; text is verbatim with wrapped lines joined by
  one space. `idare` is the unlabeled all-caps block under the title (the repeated title is not part of it).
  `page_start` is the 1-based page in the full PDF, `seq` the number printed above `SONUÇ İLANI`.
  `in_fixture` is true when the whole record is inside `tests/fixtures/mal_sonuc_excerpt.pdf`.

## Which records, and why

All 17 records that *start* in the fixture excerpt (A 1-7, 75-77; B 1-5, 90-91) are labeled; 13 are fully inside
the excerpt (`in_fixture: true`), the other 4 (A7, A77, B5, B91) have their tail outside it and were labeled from
the full PDF. 52 more were chosen to cover, on purpose:

| coverage | records |
|---|---|
| section A / section B | 33 A, 36 B (A = 202 of 203 long layout plus the short `Açık` A76) |
| usul | Açık 15, Pazarlık MD 21 B 11, MD 21 F 6, MD 21 C 1 (A92, only one), 3-g 32, 3-a (B91), 3-b (B6), 3-e (B321), 3-f (B323) |
| kısmi lots of one ikn | `2026/1757863` x4 (B166, 167, 168, 274), `2026/1757810` x4 (B8-B11), `2026/1757844` x2, `2026/1757890` x5, `2026/1833735` x5 (A5-A9), `2026/1766844` (A3, A4), `2026/1454976` (A133, 49 valid bids, lot = 0.02 % of estimate), `2026/1189991`, `2026/1286427`, `2026/1469148` |
| split across a page break | 31 records (see `notes`) |
| EUR / dual currency | EUR contract value with TRY estimate: B7, B90, B275; dual estimate `47.407.500,00 TRY (1.072.475,00 EUR)`: B4 |
| empty / non-numeric Yaklaşık Maliyeti | A76 (empty, `null`); B91 (text "İhalenin ilgili mevzuat gereğince yaklaşık maliyeti bulunmamaktadır." -> `null`) |
| contractor is a person (sole proprietor) | A3, A5, A133, A150, B165, B322 |
| contractor is a public body | B91 (Tarım İşletmeleri Genel Müdürlüğü), B321 (Devlet Malzeme Ofisi Genel Müdürlüğü) |
| joint ventures | none found: the text of the whole bulletin contains no "Ortak Girişim" / "İş Ortaklığı" / "Adi Ortaklık" / "Konsorsiyum" |
| long multi-line idare | A132, A183, B6, B163, B164, B165 (3 lines), B275, B319, B322 and others |
| single valid bid | A2, A14, A26, A78 (7 bids, 1 valid), A92, A100, A149, A150, B2-B3, B7, B91, B164, B321 ... |
| valid < total | A48, A78, A93, A184, A185, B4, B320 |
| old ikn year | `2023/949122` (A37), `2025/353442` (A132), `2025/1643181` (B4), suffix `-1` (A76) |
| document edges | first/last record of A (A1, A203) and of B (B1, B423, p458-459); pages 457-459 |
| duplicates | B92 / B93: same ikn, yüklenici and bedel, only `Süresi` differs (dedupe key `ikn, yüklenici, bedeli` collapses them) |

## Printed oddities kept verbatim

The labels reproduce what is printed, including source typos: B93/B92 `Yakışlar Demir Elektirik ve İnşaat ...`,
B423 `Fresenıus` (dotless ı, confirmed at 600 dpi), `Hakan-Ticaret Pazarlama ...`, `Aslanoğlu İth.İhr.Ticaret ...`.
A parser that "fixes" these is wrong for this purpose.

## Self-check and corrections

Ten records were drawn at random (seed 20261118: A3, A6, A14, A99, A148, A150, A183, A202, B11, B91). Nine of
them (all but A6) were re-opened against their page images and every field re-read, including the
title/idare boundary and wrapped lines: **0 corrections** from this visual re-check (A6 was only covered by the
text cross-check). The text cross-check, run over all 69 records, found **2 transcription slips of mine**, both
fixed: B423 yüklenici (`Fresenius` -> `Fresenıus`, dotless ı, then confirmed on the image at 600 dpi) and B92/B93
yüklenici (`Elektrik` -> `Elektirik`, then confirmed on the page-258 render). No amount, count, usul or ikn
needed a correction.
