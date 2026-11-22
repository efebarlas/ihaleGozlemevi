# M5c draft: IMCO-style idare scorecard (computation only; not implemented yet)

Draft by the M2 builder, in the terms of `docs/m5-plan.md` row c. Implement after M5b (done: `usul_signal`, `pazarlik_21b`,
`downloader_bid_ratio`). Offline; no EKAP.

## What it is
A 0–100 **risk index per idare**, built from three sub-indices that are each a **percentile against the idare's peer group**
(same peer chain as `idare_stats`, minimum 30 other idares' awards; the group's label and n are always shown). It is framed
as "risk, not cases" (SPEC §6.1, §6.2): it says where an idare sits among comparable idares on rule-anchored measures, never
that anything is wrong. No flags, no firm-level numbers. Always shown with its components and n.

## Unit and window
- Unit: **idare key** × **bulletin type** (mal / hizmet / yapım are not comparable), computed per `(type, idare)`.
- Window: all loaded history of that type (same as `usul_pay`). A trailing-window variant (drift) is M5d.
- Eligibility: ≥ 10 awards (İKN) for the idare in that type, else no scorecard (`n` shown, "yetersiz örnek"). Components below
  their own minimum are `null` and the index is computed from the available components only if at least 2 of 3 exist.

## Components (all from data we already hold)
**Competition** (higher = less competition)
- `tek_gecerli`: share of the idare's awards with a single valid bid (`tek_teklif` or `diger_teklifler_elendi`, the §4 rate). Min 5 awards.
- `elenen`: mean `elenen_orani` over awards with ≥ 2 bids. Min 5 eligible awards.
- `downloader_bid_ratio` (later, once `downloaders` is stored): mean of downloaders/toplam_teklif, where a *high* ratio means
  many fetched the documents but few bid. Added only when ≥ 50% of the idare's awards have the field.

**Transparency** (higher = less transparent)
- `missing_estimate`: share of awards with no readable yaklaşık maliyet (the parser's `unreadable` list; `None` at confidence ≥ 0.9 counts as missing).
- `unreadable`: share of awards with any unreadable core field (§4 `unreadable`).
- `non_open`: share of awards outside açık and belli istekliler (`acik_olmayan`), by İKN count.

**Rule compliance** (higher = more reliance on exceptional procedures)
- `pazarlik_21b`: the idare's 21/b share (by İKN count; also by TRY as the secondary view): `usul_signal.pazarlik_21b`.
- `istisna`: share of istisna procedures (`usul_pay` category `istisna`), excluding structurally explained ones (structural table
  entries, e.g. 3/e: they stay in the numerator's *display* but not in the percentile, same rule as the score).
- `pazarlik`: total pazarlık share (`usul_signal.pazarlik`), shown but weighted below 21/b.

## Computation
1. For each eligible `(type, idare)` compute every component value `v`.
2. **Percentile vs peers:** `pct = share of peer idares (excluding itself) with value < v + 0.5 × share with value = v`, where
   the peer idares are the idares of the same peer group (same chain: turu+il → turu → all of the type) that are themselves
   eligible; the group must contain ≥ 30 idares (else the next wider group, as everywhere). Ties get the mid-rank.
3. **Sub-index** = mean of its available component percentiles × 100 (equal weights inside a sub-index; fixed, not tuned).
4. **Index** = mean of the three sub-indices (equal weights, IMCO-style), 0–100. Keep the sub-indices visible: the single
   number is never shown alone.
5. Export per idare file (`export/idare/<slug>.json`), per type:
   ```json
   "scorecard": {"mal": {"n": 63, "index": 71.4, "peer": {"label": "Türkiye'deki belediyeler (mal)", "idares": 412},
     "sub": {"competition": {"index": 80.2, "components": {"tek_gecerli": {"value": 0.41, "percentile": 88.0, "n": 63}, …}},
             "transparency": {…}, "rule_compliance": {…}}}}
   ```
   Every component carries its raw value, its percentile and its n. Missing components are `null`, never zero.

## Guards (so it cannot mislead)
- **No cliffs:** continuous percentiles only; the site shows the value and its peer context, not "high/low risk" labels or a
  threshold (SPEC §6.2). Bands, if the site wants them, are the site's, with the date they took effect.
- **Structural exclusions** follow the structural table (§4.1.1): they never raise a risk component.
- **Small and very large idares:** n shown always; percentiles of idares with fewer than 20 awards carry a "düşük örnek" note.
- **Persons and firms:** nothing here refers to a yüklenici. `yuklenici_payi` is deliberately not an input (firm-level fact).
- **Stability:** peers are recomputed on every export; the scorecard is a derived view, never stored in the DB.

## Tests to write with the implementation
Percentile with ties, peer fallback at 30, component minimums, `null` handling, two-of-three rule, the DMO/3-e exclusion,
per-type separation, export shape and byte-stability, and "no yüklenici in the file".

## Open questions for the spec owner
1. Equal weights are fine for v1, but should the **rule-compliance** sub-index count `pazarlik` in total or only 21/b? (Draft: 21/b and istisna count, total pazarlık is shown only.)
2. Minimum eligibility: 10 awards per type (draft) vs 5 (the idare-rate minimum used elsewhere).
3. The M5g weight fit would later replace the equal weights; keep the component list stable so the fit can reuse it.
