# Design audit of the applied preview (SPEC 9.2, Phase 1, unguided)

Auditor: fresh-context reviewer. Method: `ihale build --design-preview` (site/preview), served locally, rendered in headless Edge at 375 px width (mobile emulation, scale 1) in light and dark via `prefers-color-scheme`. Contrast, touch targets, overflow, colours, shadows and wording were measured in the live DOM by script (raw numbers: `screenshots/audit/measurements-raw.json`). Screenshots: `screenshots/audit/` (`*-top.png` is the first 1800 px at 1.5x, `*-full.jpg` the whole page at 1x, long pages capped at 15000 px).

Pages audited (default look only): Bugun (cards, cluster card, fold line), Gun summary, Gun page 2, detail for a flagged record (mal-A-160 with 21/b, mal-B-7 with 3 flags), detail with an `okunamadi` field (mal-A-108), Arsiv, Yontem, 404. **Idare and Yuklenici pages do not exist in this build**, so they are not audited (SPEC 3 and 6.2 still require them before G-Public).

## Verdict

**Freeze after the listed fixes (not freezable as-is).** The visual language passes the neutrality rules cleanly: no hue anywhere, no shadow, no gradient, no emoji, no pill, dark mode is a designed near-black and not an inversion, contrast is high. One hard-rule failure (source link missing on fold-line entries) and a handful of readability should-fixes remain. All are small CSS/template changes.

Count: **1 blocker, 8 should-fix, 5 nice.**

## Findings

| # | Sev | Page | Mode | What I saw | Rule | Fix |
|---|---|---|---|---|---|---|
| 1 | blocker | Bugun, fold card "Bu idareden bugun 21 kayit daha" | both | The 21 entries are one-line list items (title, money, Puan, flag text). None has a source line or EKAP link (DOM: 21 `li`, 0 `.srcline`). Every normal card, cluster entry, Gun row and detail page does have one. | Source link visually present on every card/row (9.2) | Emit the same `<p class="srcline">` inside each `.fold li` (as `.clist .srcline` already does), or at minimum a "Kaynak: s. N" link per entry. The `.clist .srcline` rule at the end of style.css can be reused as `.fold .srcline{margin-top:var(--sp-2)}`. |
| 2 | should | Bugun cards, Gun rows, cluster entries | both | The source link "EKAP Bulten Indirme" is an inline link, 19 px high (min over cards 19, rows 19). The ruled strip is large but only the underlined words are tappable. It is the most important link on the card. | Touch target >= 44 px; source present | `.srcline a{display:inline-flex;align-items:center;min-height:2.75rem}` or restructure the strip as `display:flex;flex-wrap:wrap` with the link as its own 44 px row (the strip already has padding, so net height grows by about 20 px). |
| 3 | should | Bugun cluster card ("3 DHMI ihalesi") | both | Each member is one run-on sentence: idare name (whole name is the underlined link), then "- 43.732.700,00 TRY - 2 teklif verildi... - Puan: 8,9". Money is buried mid-sentence, not bold, not aligned, three entries cannot be compared by eye. Card shows no flag list or peer line. | Scannable money; hierarchy | Render each `.clist li` as the card pattern: link on its own line, then `<span class="money">` (800 weight, `font-size:var(--money-fs)`) on a second line, flags and Puan as muted lines. CSS: `.clist .money{display:block;font-weight:var(--money-weight);font-size:var(--money-fs)}`. |
| 4 | should | Bugun fold entries | both | Same run-on pattern as #3 (title - money - Puan - flag text - "Bu yuklenici son 12 ayda ... sozlesme aldi"). A reader cannot find the lira amount. | Scannable money | Same template change as #3: put the money in its own bold span at the start of the second line. |
| 5 | should | Gun page 2 (and all Gun pages), also Bugun rows | both | Money (`.rb`, 800 weight, tabular) is left-aligned under the idare line. On a 375 px list, amounts of different digit counts do not line up, so ranking by size means reading every figure. (Right alignment only exists from 40 rem.) | Tabular figures and right alignment where numbers are compared | `.row .rb{text-align:right}` below 40 rem, or put the money on the same line as the title: `.row{grid-template-columns:1fr auto}` for the title/money pair at all widths. Tabular nums already in place (`lining-nums tabular-nums` measured on body). |
| 6 | should | Yontem | both | The two rate tables sit in `.tw{overflow-x:auto}`; table is 437 px wide in a 375 px viewport, so the page does not scroll but the table does, the last column is cut ("Tekrarlayan ..."), with no visible cue. First column wraps mid-code ("4734/3-" / "g"). Percentages are left-aligned. | No horizontal scrolling at 375 px; right alignment of numbers | `.rules td:first-child,.rules th:first-child{white-space:nowrap}` is not enough; instead shorten the column labels (e.g. "Tek", "Elendi", "Yakin", "Tekrar") with the long names in a note, set `.rules td+td,.rules th+th{text-align:right;white-space:nowrap}` and reduce cell padding to .3rem .4rem. If it still exceeds 343 px, add a visible right-edge fade/hint. |
| 7 | should | Yontem prose | both | Text says "OCP kirmizi bayrak R018 / R035" ("red flag") next to the flag descriptions. It is a source-code label, but on the page it reads as the verdict colour in words, against the neutral-wording and no-red rule. | Neutral wording | Template change (content): drop the parenthetical or say "OCP gosterge R018". |
| 8 | should | All pages in this preview | both | Hidden direction-switch anchor `<a class="sw" href="?yon=...">.</a>` in the footer (a 44 x 44 box) and the inline script that reads `?yon=`/`?tema=` and localStorage. Preview-only, but if the stylesheet is frozen by copying the preview, the switch ships and violates the "no direction, no switch" blind rule. | 9.2 blind rule | Strip `a.sw`, the `<script>` block and `a.sw` CSS from the template when the preview flag is off (confirm the production build does not emit them). |
| 9 | should | Bugun cards (hierarchy) | both | In five seconds the eye lands on the heavy lira amount and the underlined title. What is unusual (the flags, a) b)) is 14 px regular and visually the same weight as the body; the peer comparison, which is the number that explains the flag ("%70,1 - benzer idarelerde ortanca %43"), is muted grey 14 px under a dotted rule. Where the numbers come from (the source strip) is clear. | Hierarchy | `.peer{color:var(--c-fg);font-size:var(--fs-base)}` and `.flag{font-weight:600}` (or make the peer line the first line inside `.flags`). Keep no colour, no icon. |
| 10 | nice | Detail pages | both | The "Bilgiler" list prints Yaklasik maliyet and Sozlesme bedeli at normal weight (`.detail dd`), whereas the card prints money at 800. The most important figures sit among 15 other rows. | Hierarchy, scannable money | Add `class="money"` to those two `<dd>` and `.detail .money{font-weight:var(--money-weight)}`. |
| 11 | nice | Detail pages | both | Source appears three times: strip under the title, then a "Kaynak" h2 plus bold "Kaynak: ..." line at the bottom, plus "Bu sayfada ilgili gunun..." paragraph. The bottom heading repeats itself ("Kaynak" then "Kaynak: Kamu Ihale Bulteni..."). | Polish | Drop the bold repeat line in the bottom section. |
| 12 | nice | Bugun, filter chips | both | The five chip filters wrap to five rows (about 190 px). Chips are rectangular (good, not pills) but push the first card below the first screen. | Hierarchy, phone-first | `.chips{flex-wrap:nowrap;overflow-x:auto}` with a visible edge, or a 2-column grid: `.chips{display:grid;grid-template-columns:1fr 1fr}`. |
| 13 | nice | Detail pages | both | Breadcrumb link "Bugun" is 40 x 44 px (width under 44). Skip link is 23 px tall when focused. | Touch target | `.crumbs a{min-width:2.75rem;justify-content:center}`; `.skip:focus{padding:.75rem}`. |
| 14 | nice | Gun page rows and detail flag text | both | The flag sentence "idarenin tek gecerli teklif payi, karsilastirma grubunun payinin belirgin bicimde uzerinde" uses "belirgin bicimde" ("markedly"), a soft evaluative adverb. Not a verdict word, but the only qualitative intensifier in flags. | Neutral wording | Content: replace with the numbers already available ("%100, karsilastirma grubunda %23"). Out of scope for design; flag to the spec owner. |

No finding relates to Idare/Yuklenici pages (not built).

## Rules that passed (with evidence)

- **No alarm colour / icons.** Chroma scan of every computed colour, border and outline on every page: the only coloured values are the neutral greys `rgb(78,86,94)` (light) and `rgb(154,163,171)`/`rgb(160,168,176)` (dark); no hue. No emoji or pictographs in any page text. Flags are lettered notes (`a)`, `b)`) with a dotted rule beneath, no fill, no icon.
- **No party colours.** Nothing red, orange, yellow, green, blue or purple exists in the palette (links are the text colour with a 2 px underline; visited links go grey).
- **Default-look tells.** 0 elements with `box-shadow`, 0 gradients, 0 rounded corners except an off-screen radio input (`50%`), no pills (chips are square), spacing steps are unequal and the card has a 3 px top rule with hierarchy inside. Dark mode is a separate palette (surfaces step up in lightness, muted tones dimmed), not an inversion. System font only.
- **Turkish characters.** İ, ı, ş, ğ, ç, ö, ü render correctly in all headings, uppercase labels (`text-transform:uppercase` with `lang="tr"` gives "İDARE", "İHALE KAYIT NO", "SÖZLEŞME") and the brand mark "İHALE GÖZLEMEVİ".
- **No horizontal page scroll.** `documentElement.scrollWidth` = 375 on all 9 pages in both modes. The only element wider than the viewport is the Yöntem table inside `.tw` (finding 6) and the off-screen skip link.
- **Long text wraps.** Idare names ("DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ DEVLET MALZEME OFİSİ TRABZON BÖLGE MÜDÜRLÜĞÜ"), 120-character konu strings and the detail h1 all wrap cleanly in the label/value grid (`overflow-wrap:anywhere`).
- **Tabular figures.** Computed `font-variant-numeric: lining-nums tabular-nums` on body, everywhere.
- **Neutral wording.** No verdict word on any page (searched: şüpheli, yolsuz, usulsüz, hile, rüşvet, kayırma, skandal, vurgun, risk, alarm, tehlike). Hits for "uyarı" and "sınır" are a company name and the footer link "Yöntem ve sınırlar" / a tender title. Threshold-like text ("≥ 0,97", "Eşikler") occurs only in Yöntem prose, which is allowed. "%97"/"%95" hits on Bugün are measured values (e.g. "%97,3"), not labels.
- **Persons masked.** "Gerçek kişi yüklenici" appears in Bugün (1) and Gün page 2 (7); detail pages print the named person ("İsa İşler" on mal-A-108) as allowed.
- **Source on cards/rows/detail.** Bugün: 31 `.srcline` for 26 cards (+ cluster entries), 0 cards without; Gün page 2: 50 rows, 50 `.srcline`, 0 without; every detail page has the strip under the title and a Kaynak section. Exception: the fold card (finding 1). The Gün summary page and Arşiv are index pages with no records; the summary tells the reader where the source is.
- **`okunamadı` field.** On mal-A-108 "Sözleşme süresi" prints italic muted "okunamadı", distinct from the em dash for a missing field; it does not look like an error state.

## Measured numbers

Contrast (WCAG 2.x, computed from rendered fg over actual background, every text node, 375 px; large text threshold 3, otherwise 4.5). **No failures on any page, either mode.**

| Pair | Light | Dark |
|---|---|---|
| Lowest on any page: 11 px "KAYNAK" / label caps (`span.lbl`) | 6.24 | 6.33 |
| Muted body (`.muted`, `.crumbs`, `.rm`, dt) | 6.83 on page, 7.46 on card | 7.86 on page, 7.26 on card |
| Peer line (`.peer`) | 7.46 | 7.26 |
| Flag text | 14.3 - 15.7 | 12.2 - 13.2 |
| Source strip text and link | 15.05 | 12.63 - 13.68 |
| Links, nav, brand | 16.48 | 15.69 - 17.0 |
| Table header on th fill | 15.05 | 12.63 |

Touch targets (DOM bounding boxes at 375 px):

| Element | Size | Result |
|---|---|---|
| Nav links, brand, chips, summary, "Ayrıntı →", pager, archive rows, buttons | height >= 44 (min measured 44) | pass |
| Chip rows | 44 px high, 5 rows | pass |
| Inline source link `EKAP Bülten İndirme` in strip | 19 px high (min 19, widths 137 or more) | fail (#2), exempt only under WCAG 2.5.8 inline rule |
| Inline "Nasıl hesaplanıyor?" and in-paragraph links | 19 - 21 px high | exempt as inline, nice-to-have |
| Breadcrumb "Bugün" on detail pages | 40 x 44 | width fails (#13) |
| Skip link (when focused) | 77 x 23 | fails (#13) |
| Hidden switch `a.sw` | 44 x 44 | passes, but must not ship (#8) |

Page heights at 375 px: Bugün 15667, Gün summary 1702, Gün page 2 15388, detail 1924 - 2681, Arşiv 1297, Yöntem 9050, 404 812.

## Notes for the builder

- Verify after fixing #1 that the fold entries still render in two lines each; the open fold is about 2500 px high today.
- Raw internal code `tekrarlayan_eslestik` mentioned in the earlier direction review no longer appears (searched index, mal-A-160, mal-B-7).
- Not measured: real-device rendering on iOS/Android (only Windows Edge, Segoe UI); focus rings; screen reader behaviour; wide layouts.

## Fixes applied

Commit: see `git log -- design/unguided/audit.md` (the commit that adds this table). "Live" = the normal build, "preview" = `ihale build --design-preview`. Screenshots of the affected pages (375 px, light and dark): `screenshots/applied/fix-*.jpg`.

| # | Finding | Where fixed | Status |
|---|---|---|---|
| 1 | Fold entries had no source line | live + preview: fold and cluster entries are `.ent` items with money, flags, Puan and `srcline` (test: every fold entry has `srcline` and `money`) | fixed |
| 2 | Source link only 19 px high | live + preview CSS: `.srcline a{display:inline-flex;align-items:center;min-height:2.75rem}` (measured 44 px in the preview) | fixed |
| 3 | Cluster entries were run-on sentences | live + preview: link line, own money element (right-aligned), muted flag/Puan line, source line | fixed |
| 4 | Fold entries were run-on sentences | same markup as #3 | fixed |
| 5 | Money left-aligned in Gün rows | live + preview: `.rb,.money` right-aligned, tabular figures on body | fixed |
| 6 | Yöntem tables clipped at 375 px | live + preview: `.rules.stack` reflows to stacked label/value rows below 40 rem (also applied to the Gün summary and the idare and yüklenici tables); no horizontal scroll | fixed |
| 7 | "OCP kırmızı bayrak" wording | live: now "OCP göstergesi R018/R035/R038"; "kırmızı bayrak" and "red flag" are in the forbidden-words test | fixed |
| 8 | Switch shipping in the live build | switch link and script are emitted only with `preview_design`; tests assert the live build never contains `class="sw"`, `?yon=`, `localStorage`, tokens or `data-direction`; `deploy()` refuses preview output | confirmed |
| 9 | Peer line and flags too quiet | preview only: `.peer` at body colour and size, `.flags .flag` at weight 600 | fixed (preview) |
| 10 | Money weight in the detail field list | not done (nice) | open |
| 11 | Source repeated three times on detail pages | not done: the bold "Kaynak: ..." line is kept because the spec text requires that exact string | open |
| 12 | Chips wrap to five rows | not done (nice) | open |
| 13 | Breadcrumb width, focus-state skip link | not done (nice) | open |
| 14 | "belirgin biçimde" in the idare-rate flag text | wording is the spec owner's call; flagged, not changed | open |
