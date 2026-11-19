# Visual direction review (SPEC 9.2, Phase 1, unguided)

Reviewer: fresh-context direction reviewer. Worked only from this repo (SPEC, templates, the real build in `site/dist/`).

## What was done

- Three token sets: `tokens/gazete.css`, `tokens/defter.css`, `tokens/evrak.css`. Each is scoped to `<html data-direction="NAME">`, so all three can be loaded together and the hidden switch just changes that attribute. Theme: `data-theme="light|dark"` forces a theme; without it `prefers-color-scheme` decides.
- `consumer/style.proposed.css`: a drop-in replacement for `style.css` (same class names) that reads only these tokens. The repo's real `style.css` and templates were not touched.
- Applied to the **real built pages** (19 Kasim 2026 Bugun with 34 cards, the Gun page with 591 rows, tender detail pages `mal-B-7` (3 flags, DMO/3-g) and `mal-A-160` (2 flags, 21/b), and Yontem), rendered in Edge at a 375 px layout width in light and dark. Screenshots: `screenshots/directions/<direction>-<light|dark>-<bugun|detay|gun|yontem>.png`.
- Contrast ratios below were computed from the token files (WCAG 2.x relative luminance), not eyeballed.

## Markup deltas (needed by every direction; small)

The source-link rule is not met by the current markup, whatever the colours are:
1. On cards the only link is "Ayrinti ve kaynak" which goes to the detail page; the real source (bulletin date, page, EKAP link) appears only at the bottom of a ~3,400 px detail page.
2. Day-page rows have no source at all.

The screenshots therefore include one added element, `<p class="srcline"><span class="lbl">Kaynak</span>Kamu Ihale Bulteni, 19.11.2026, Mal - Sonuc Ilanlari, s. 167 · <a href="EKAP">EKAP Bulten Indirme</a></p>`, placed (a) at the foot of each Bugun card, (b) directly under the title on the detail page. The text is the same `c.src_text` the template already prints in the Kaynak section. Recommended for the builder: add it in `_macros.html` / `_record.html`; the bottom Kaynak section can stay. Day rows were left without it (a 591-row list); consider a one-line source on expand. Optional: a `class="money"` on the contract-value `<dd>` (the consumer CSS currently targets `.facts div:nth-child(3) dd`).

## Direction A: Gazete

**Idea.** The site is a reading copy of the Kamu Ihale Bulteni, so it looks like a gazette page: warm newsprint, a serif text face, a double rule under a centred masthead, entries numbered and divided by rules (no boxes), flags as italic marginal notes in sepia ink with a hairline bracket on the left.
**For this product's readers.** Calm, long-form reading of the neutral sentences; the "annotated record" feel is strongest. Numbered entries make "see no. 3" easy to say in a newsroom.
**Rules.** Flags: sepia ink on newsprint, no fill, no icon, no red/orange. Parties: palette is newsprint, ink-black, ink-blue links and brown ink; nothing red, orange-yellow, purple-green or light blue. Source: bold, ruled "Kaynak" line plus link on every card and under the detail title. Readability: AA everywhere (table below); 44 px targets via `min-height:2.75rem` on nav, chips, link rows, summaries; `tabular-nums lining-nums` on all text; Turkish glyphs (I/i with dot, g with breve) rendered correctly in Sitka/Charter/Cambria. Default-look tells: no shadows, radius 0, no pills, no gradients, no emoji; dark is a warm lamp-lit page with sepia notes pushed lighter, not an inversion.
**Weaknesses.** Tallest cards (stacked italic labels were reduced to a 5.4 rem label column but values still wrap a lot). Serif body on Android depends on Noto Serif being present; fallback is generic `serif`. Warm paper plus blue links is the one palette that comes near a "yellow-blue" reading (very low saturation, so judged safe, but it is the least neutral of the three). Georgia is deliberately excluded because its default old-style figures hurt scanning money.

## Direction B: Defter (recommended)

**Idea.** Readers check figures. The page is a ledger: cool paper, one neutral ink, hairline rules, letter-spaced capital labels, contract value set at 800 weight in tabular figures, flags as lettered notes to the entry ("a) ... b) ...") like footnotes to a table. There is no hue at all. Links are the text colour with a 2 px underline (colour is never the only cue), visited links dim to grey.
**For readers.** Densest layout (label column + value column; the lira amount is the heaviest thing in each card), good for journalists and auditors comparing many entries; the lettered flags let you cite "flag b" in a note; the source is a bordered grey strip with "KAYNAK" at each card foot.
**Rules.** Flags: graphite, no fill, no colour, dotted rule beneath; no icon. Parties: structurally impossible to read as a party colour, because there is no colour. Source: boxed strip on every card, repeated under the detail title. Readability: highest contrast of the three (link 16.5:1 light, 17:1 dark), tabular figures, 44 px targets as above. Default-look tells: square corners, no shadow, no pill, no gradient; dark is a designed near-black with dimmed secondary tones (not white-to-black inversion; surfaces step up in lightness for cards).
**Weaknesses.** Least memorable; the absence of a link colour makes in-paragraph links less discoverable (underline only) for people who expect blue. System sans differs by platform. Uppercase labels at 11 px are the smallest text anywhere (contrast 6+:1, but size is small; they are labels, not content).

## Direction C: Evrak

**Idea.** Each record is a sheet of official paper in a dosya: sheets on a greige desk, "No 1" folio marks, typewriter-style monospace capital labels, flags as typed "NOT" slips with a dashed left edge, and the source as a ruled stamp box ("KAYNAK") in blue-black stamp ink.
**For readers.** The strongest "annotated official document" metaphor, and the source box is the most visible of the three. Dark mode becomes a night archive with chalk-blue ink.
**Rules.** Flags: tan slip with ink-blue "NOT" label, no red, no icon, innocent-explanation text sits inside the slip. Parties: greige plus navy ink; no red/orange/purple-green. The tan desk next to navy is the second-closest to a "yellow-blue" reading, so keep the desk colour grey-biased (it is). Source box on every card and under the detail title. AA everywhere; targets as above.
**Weaknesses.** Boxed sheets with fills are the nearest of the three to generic "cards", and the tan flag slip is the nearest thing to a callout box; long idare names wrap in a narrow value column; monospace labels are decorative and the "NOT" word adds a (Turkish) word that is not in the data; a stamp metaphor can read as officialdom, which a watchdog may not want to borrow.

## Recommendation

**Defter (B) as the default, Gazete (A) as the warm alternative in the switch.** Defter is the only set whose neutrality is structural (no hue, so no party reading and no verdict colour), it has the highest contrast and the densest, most scannable money column, and its lettered flag notes plus ruled source strip satisfy the annotation and source rules with the least decoration. Gazete is the better long-form read and the more distinctive identity, so it should stay one tap away; Evrak is the fallback if a stronger "document" metaphor is wanted.

## Exact token values (see the files for the full set)

Palette (light | dark):

| token | Gazete | Defter | Evrak |
|---|---|---|---|
| bg | #f5f0e4 \| #1b1813 | #f4f5f6 \| #0f1113 | #e8e4da \| #141518 |
| card surface | transparent (bg) \| transparent | #ffffff \| #171a1d | #f8f6f0 \| #1d1f23 |
| text | #1d1a15 \| #ebe4d4 | #14171a \| #e8eaec | #1b1b1d \| #e7e3d9 |
| muted | #595143 \| #aea590 | #4e565e \| #a0a8b0 | #56534b \| #aaa699 |
| link | #1a3c73 \| #a9c1ee | #14171a \| #f1f3f4 | #1f3358 \| #a9bde3 |
| visited | #4a5568 \| #aab3c4 | #4e565e \| #a0a8b0 | #4c4a52 \| #b0adb8 |
| flag text / bg / mark | #5b3a10 / none / #8a5a1f \| #e0c08f / none / #b08a52 | #1f2428 / none / #14171a \| #d3d8dc / none / #9aa3ab | #26231d / #e6e1d2 / #243558 \| #ddd9cc / #2a2c33 / #8ea3cb |
| source label / strip bg | #5b3a10 / none \| #e0c08f / none | #4e565e / #e9ebed \| #a0a8b0 / #22262a | #243558 / none \| #a9bde3 / none |

Type: A body Charter, Sitka Text, Cambria, Noto Serif, DejaVu Serif, serif; base 1.0625 rem, scale .8125/.9375/1.0625/1.1875/1.375/1.875 rem, line-height 1.55. B body system-ui stack; base 1 rem, scale .75/.875/1/1.0625/1.25/1.6 rem, line-height 1.45, money 1.125 rem at 800. C body system-ui, labels ui-monospace/Cascadia Mono/Consolas; base 1 rem, scale .75/.875/1/1.0625/1.3/1.65 rem, line-height 1.5. All use `font-variant-numeric: lining-nums tabular-nums`. System fonts only; no external CDN, nothing to self-host.
Spacing (rem): A 0.25/0.5/0.8/1.1/1.7/2.6/3.6, gutter 1.1; B 0.2/0.4/0.65/0.9/1.4/2/2.8, gutter 1; C 0.25/0.5/0.75/1/1.5/2.25/3.25, gutter 0.9. Steps are unequal on purpose so line < entry < section.

### Measured contrast (WCAG ratio; AA needs 4.5 text, 3 non-text)

| pair | Gazete L | Gazete D | Defter L | Defter D | Evrak L | Evrak D |
|---|---|---|---|---|---|---|
| text on page | 15.25 | 13.97 | 16.48 | 15.69 | 13.55 | 14.25 |
| text on card | 15.25 | 13.97 | 17.99 | 14.49 | 15.91 | 12.88 |
| muted on page | 6.88 | 7.23 | 6.83 | 7.86 | 6.05 | 7.50 |
| muted on card | 6.88 | 7.23 | 7.46 | 7.26 | 7.11 | 6.78 |
| link on page | 9.53 | 9.73 | 16.48 | 17.00 | 9.89 | 9.63 |
| link on card | 9.53 | 9.73 | 17.99 | 15.70 | 11.62 | 8.70 |
| visited link on card | 6.62 | 8.39 | 7.46 | 7.26 | 8.07 | 7.48 |
| flag text on flag bg | 8.98 | 10.20 | 15.66 | 12.17 | 11.98 | 9.87 |
| flag title label (muted) on flag bg | 6.88 | 7.23 | 7.46 | 7.26 | 5.87 | 5.72 |
| flag marker text/bar on flag bg | 5.18 | 5.56 | 17.99 | 6.82 | 9.31 | 5.48 |
| source label on source bg | 8.98 | 10.20 | 6.24 | 6.33 | 11.26 | 8.70 |
| source link on source bg | 9.53 | 9.73 | 15.05 | 13.68 | 11.62 | 8.70 |
| selected chip / button text | 15.25 | 13.97 | 17.99 | 15.69 | 11.26 | 7.42 |

All pass AA. Not measured: real-device 44 px target sizes (set in CSS as `min-height:2.75rem` on nav, brand, chips, card link rows, summaries, buttons, breadcrumbs, footer links; inline links inside paragraphs are exempt under WCAG 2.5.8 but are not enlarged); screen-reader behaviour; font fallbacks on iOS/Android (only Windows/Edge was rendered).

## Findings outside the visual brief (for the builder / spec owner)

- The "Puan" breakdown list on detail pages prints a raw internal code: `tekrarlayan_eslestik: 1,6 puan` (a flag key, not the Turkish title). Data/template bug, visible in all directions.
- Cards show "Puan: 10,4" as a plain muted line; the SPEC 6.2 wording suggests peer context is the primary figure, the Puan the secondary. Hierarchy here is already right (peer line above), kept.
- Chips wrap into five rows at 375 px (about 190 px of height). If vertical space matters, shorten labels or use a single scrolling row with a visible edge.
- Gun page rows have no source link and no money alignment; with the proposed CSS the money is bold under the names. A right-aligned money column only appears at >= 40 rem.
- The wide-screen (>= 40 rem) layout was not reviewed visually; only 375 px was.
