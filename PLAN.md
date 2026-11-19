# İhale Gözlemevi: PLAN

Rules: SPEC.md is the source of truth, and only the spec owner edits it. The spec owner is Efe's decision proxy, so every question goes to it, never to Efe. It escalates only SPEC §7 hard stops. Human checks queue here and don't block work. Builders commit their own work, path-scoped, and never touch SPEC.md.

## Status
- 2026-11-18: direction set with Efe (SPEC.md). Next: M0 Fresh base. The 2022 code is disposable.
- 2026-11-18 evening: orchestrator started. M0 builder running (skeleton, polite plain-HTTP EKAP fetch, fixtures, layout notes). Wrangler is already logged in on Efe's account. Data lives off OneDrive in `%USERPROFILE%\ihaleGozlemevi-data` (override with `IHALE_DATA_DIR`).

- 2026-11-18 night: M0 done. EKAP answers a plain HTTP form post (no browser, no CAPTCHA). Data dir moved to `%USERPROFILE%\ihaleGozlemevi-data` because the Claude app silently redirects AppData writes, which Task Scheduler would not see. Shared contract for parser/flags/site: `docs/data-contract.md`, `src/ihale/model.py`. Next: M1 parser, M2 store/flag, M3 site generator, built in parallel against that contract.

- 2026-11-19: SPEC §4.1, so we build on ihalent (pinned 0.5.1, MIT). We keep our own downloader: ihalent's waits only 2 s. License audit found `certifi` (MPL-2.0) via `requests`, so `requests` is being replaced by stdlib urllib, with a license test added. Bugün ranks by a compound score (contract §4.1). Sector/province peers are deferred to M4 because the bulletin has no such fields.

- 2026-11-19: M1 done. M2/M3 code landed. Running a 30-day mal backfill (polite, sequential) for base rates and the repeat-winner flag, then first deploy and the scheduled task.

- 2026-11-19: independent label spot-check (fresh agent, page images, not the labeler): 10 records (B4, A76, B2, B275, A183 plus random B421, A184, A3, B3, B321), 80 fields, 0 mismatches.

- 2026-11-19: M3 live. Bugün 19 Nov: 51 of 591 records shown. Scheduled task runs the pipeline daily; auto-deploy needs Efe's one-time Cloudflare login (optional; a session deploys meanwhile). Next: §9.2 unguided visual pass, then M4.

- 2026-11-19: M4 hizmet/yapım parsing verified (80970e3): ≥96.9% on every core field over 32 hizmet + 27 yapım hand labels (100% after one label correction); ToC complete for both. 30-day hizmet/yapım backfill running. Dosyalar data export landed (1507573). Unguided design: direction proposed and applied to a non-deployed preview; audit running.

- 2026-11-19: live site updated (clean build of 0720aa5): mal + hizmet + yapım (18,966 records, 21 days), İdare (2,940) and Yüklenici (5,232, companies only) pages, paginated day pages, parent-body clusters, source line on every card. 13,772 files, 154 MB.
- **File-count risk:** about 300 new files a day (detail pages plus new idare/firm pages) means the 19,000-file guard is hit in about 2 weeks, and the M5 backfill is impossible as static files. Planned fix (M4 infra): pre-rendered HTML for detail/idare/yüklenici pages stored in a free-tier D1 database and served by the Worker; only the core pages stay as static assets.
- Base-rate reconciliation (M4): single valid bid per tender, 21 days: açık 20.1%, pazarlık 43.3%, 4734 istisna 40.0%; açık+pazarlık 26.5% (mal 28.7%, hizmet 36.6%, yapım 12.4%). İhaleGlobal reports ~43%. Its figure is closest to our pazarlık or istisna rates. Explain in Yöntem once its definition is known.

- 2026-11-19: **Person masking fixed** (4f018ca). The old rule let trade names of sole proprietors and joint ventures of persons through, exposing names on 41 dossier pages. Legal-entity forms now decide. A deploy guard refuses any build where a masked name appears in a yüklenici field outside its own detail page. Live.
- 2026-11-19: **KİK board decisions / debarment: EKAP v2 API returned a sign-in wall (429, suggestSignIn).** Reported to the spec owner as a §7 hard stop. We stopped. Default: detail pages only link out to EKAP's decision search. Debarment via Resmî Gazete notices is the spec owner's call. Bulletin download is unaffected.
- 2026-11-19: open exports (OCDS, FtM) done, private. The Cardinal cross-check was skipped: the PyPI package has no indicators, and a binary download is not allowed.
- 2026-11-19: unguided design baseline frozen (tag `design-unguided`). Nothing design-related is deployed.
- 2026-11-19: D1 live. Database `ihale-pages` (free, eeur): 13,541 bulk pages, 30,464 rows, 155 MB. About 45 static core pages. Core pages and D1 pages verified live (noindex, 404s). Debarment parked: Resmî Gazete notices give no usable second identifier (2696f1f).
- **M5 storage note:** the D1 pages take about 124 MB per 30 days. D1 free allows 500 MB per database, 10 databases, 5 GB total. The 2010 backfill needs compression (gzip BLOBs) or Worker-side rendering from data rows. Plan this before M5.
- M4 classifier experiment (SPEC §11): on 200 independent hand labels, keywords score 89.0% turu / 99.0% il, the lookup table (2,938 names, built once, two passes 99.9% consistent) 97.5% / 100%, and hybrid 90.0% / 99.5%. `table_first` (6366a7d) is in shadow from the 2026-11-19 evening run. **Promote** (`IHALE_PEER_CLASSIFIER=table_first` in the scheduled task) after 3 shadow runs, around 2026-11-22. The spec owner approved promotion without a Günün sorusu. When it switches, report the before/after Bugün counts and the top 5 score movers. The table gets extended from `<data>/logs/classify-new-names.txt`. DETSİS independent check: dropped (site unreachable, 3 requests, a4a361f).

## Milestones
| | Milestone | State |
|---|---|---|
| M0 | Fresh base | done (c46d8ce, 95cfd4b; verified: 35 offline tests pass, 18.11.2026 mal/hizmet/yapım bulletins downloaded) |
| M1 | Adopt ihalent | done (e096656; verified: adapter over ihalent 0.5.1 scores 100% correct+confident on all 6 core fields over 69 hand labels; ihalent alone 95.7% on bedel because it drops EUR; 626/626 notices, ToC complete; 69 s per day) |
| M2 | Store and flag | done (cc13bd4; 534 tests; 30-day backfill 13,830 records; rarity-weighted score within procedure, value weight, 3-g DMO split, typo rule; oracle candidates) |
| M3 | Site v1, unlisted, with the daily run | live 2026-11-19 at https://ihale-gozlemevi.clearpile-reader-server.workers.dev (noindex header + meta, robots disallow, verified). Daily task `ihaleGozlemevi-daily` at 21:30 PT registered and test-run outside the app: everything works except deploy, which waits on the one-time Cloudflare login (human check). Until then a session deploys. |
| M4 | Dosyalar and better peers | in progress. Done: hizmet/yapım, İdare/Yüklenici pages, OCDS/FtM exports (private), D1 page store (live). Blocked: KİK decisions/debarment (EKAP sign-in wall). Classifier: table wins (97.5% vs 89%), shadow then promote. Simulated-user check done (5 personas, about 85 requests, no blockers, no broken links). The fix batch (units, chip counts, rounding, the 'yakın' label above 100%, kısmi caveat, il filter, pazarlık share vs peers) is with the builders, to ship in one deploy. |
| M5 | History | not started |

## Queued for later milestones (SPEC §6.2 release policy)
- M4: each İdare page shows its procedure mix over time (açık / pazarlık incl. 21/b / istisna) and its volume trend, so displacement stays visible.
- M4: reconcile our single-valid-bid rate (29.1% per tender, mal only, 21 days, 65% of records 3-g) with İhaleGlobal's ~43% once hizmet and yapım are loaded; compute the comparable figure and explain any gap in Yöntem.
- M4: split 3-g base rates into "3-g DMO" and "3-g others" (DMO is 8,308 of 8,964 3-g records), so other 3-g buyers aren't measured against DMO's norms.
- M5: drift monitoring (incl. DMO against its own history, contract §4.1.1).
- G-Limited (new, before G-Public): invited readers behind Cloudflare Access.
- G-Public: dated t0 baseline snapshot; legal review; who publishes; validated weights.
- Launch is pull-only: no bots or push alerts aimed at named bodies.

## Decisions needed (Efe)
- (spec owner) Who publishes the site: the footer GitHub link, which shows Efe's account, was removed until this is decided (G-Public item).

## Human checks queued
- **Cloudflare login for the daily job (one-time, about 1 minute).** Double-click `scripts\cloudflare_login.cmd` in the repo folder (outside the Claude app), then click "Allow" in the browser. Optional: until then a session deploys after each daily run. Why: the Claude app keeps its own private copy of the Cloudflare login, and Windows Task Scheduler can't see it. Until this is done, the daily job still downloads and processes bulletins, but the site only updates when a session deploys it.

## Non-converging issues
- none

## Environment notes
- Efe's global npm registry points at an expired private CodeArtifact (E401). Project node tooling must use the public registry (a repo `.npmrc`, or `npm_config_registry=https://registry.npmjs.org/`). Don't change his global config.
