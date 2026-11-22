# M5 plan: weights, rules and history (orchestrator, 2026-11-22)

SPEC §10 M5. Context: an EKAP hard stop (SPEC §7) is in force since 2026-11-21. Bulk backfills now also need Efe's OK and a daily request budget (the shared cap is 60 requests/day). The order is therefore: offline work first, new non-EKAP sources second, history last.

| # | Piece | Needs EKAP? | Owner | State |
|---|---|---|---|---|
| a | **Parser gap:** store `downloaders` (3a) and `yuklenici_adresi` (4f), recovered from PDF words because ihalent drops the address row. Re-parse the stored bulletins. Store only, no flags. Addresses of natural persons are never displayed. | no | parser builder | next |
| b | **Rule-anchored signals:** idare's 21/b and pazarlık share vs its peers (from `usul_pay`), plus `downloaders / geçerli teklif` once (a) lands. Indicators with n and peer context; no score points until base rates are measured. | no | M2 builder | next |
| c | **IMCO-style idare scorecard:** a 0–100 score per idare from three sub-indices: competition (tek-geçerli share, elenen oranı, later downloader/bid ratio), transparency (missing estimate, unreadable fields, non-open procedure share) and rule compliance (21/b share, istisna share). Each is a percentile vs the idare's peer group (min n 30). Always shown with its components and n, framed as "risk, not cases". | no | M2 data, site builder page | after b |
| d | **Drift monitoring:** each idare's procedure mix and score parts vs its own trailing history, with the 80% D1 usage warning already in. Weekly summary in the logs. | no | M2 builder | after c |
| e | **Sayıştay findings:** feasibility check of sayistay.gov.tr audit reports (access, terms, format; at most ~10 requests, polite). If accessible: second §11 agent-module experiment (extraction behind a seam, independent labels, A/B, shadow). | no (other host) | parser builder | after a |
| f | **History backfill:** blocked by the hard stop and by the bulk-backfill rule. Open questions for the spec owner/Efe are below. | **yes** | — | blocked |
| g | **GTI weight fit:** fit the indicator weights to outcomes (bedel/estimate ratio, single bidding) and the oracle's pairwise answers (only 2 so far), and publish the regression in Yöntem. Needs history. | via f | M2 builder | after f |
| — | Debarment (Resmî Gazete) | — | — | parked (no second identifier) |

## Storage for history (affects f)
D1 holds 30 days of all three types in ~69 MB (gzip pages). Sixteen years would be ~13 GB, but the free tier gives 5 GB (10 × 500 MB). Options, to decide before f:
1. Deploy detail pages only for the last N months. Older years appear on İdare/Yüklenici pages and in day lists, without per-tender pages.
2. Render older detail pages in the Worker from compact data rows instead of pre-rendered HTML.
3. Both.

The default is option 1, since it needs no new code paths in the Worker.

## Open questions (sent to the spec owner)
- **Raw bulletins:** can the live store reuse the raw bulletins already in `E:\ihaleGozlemevi\research-archive` (same public files) instead of downloading them again? That would cut the EKAP requests history needs to zero for the years it covers.
- **Budget:** when the block clears, what daily request budget does Efe approve for a history backfill?
