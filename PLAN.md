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

## Milestones
| | Milestone | State |
|---|---|---|
| M0 | Fresh base | done (c46d8ce, 95cfd4b; verified: 35 offline tests pass, 18.11.2026 mal/hizmet/yapım bulletins downloaded) |
| M1 | Adopt ihalent | done (e096656; verified: adapter over ihalent 0.5.1 scores 100% correct+confident on all 6 core fields over 69 hand labels; ihalent alone 95.7% on bedel because it drops EUR; 626/626 notices, ToC complete; 69 s per day) |
| M2 | Store and flag | done (cc13bd4; 534 tests; 30-day backfill 13,830 records; rarity-weighted score within procedure, value weight, 3-g DMO split, typo rule; oracle candidates) |
| M3 | Site v1, unlisted, with the daily run | live 2026-11-19 at https://ihale-gozlemevi.clearpile-reader-server.workers.dev (noindex header + meta, robots disallow, verified). Daily task `ihaleGozlemevi-daily` at 21:30 PT registered and test-run outside the app: everything works except deploy, which waits on the one-time Cloudflare login (human check). Until then a session deploys. |
| M4 | Dosyalar and better peers | in progress: hizmet/yapım adapter + labels (parser builder), per-type groups + Dosyalar export (M2 builder); site pages next |
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
- none

## Human checks queued
- **Cloudflare login for the daily job (one-time, about 1 minute).** Double-click `scripts\cloudflare_login.cmd` in the repo folder (outside the Claude app), then click "Allow" in the browser. Optional: until then a session deploys after each daily run. Why: the Claude app keeps its own private copy of the Cloudflare login, and Windows Task Scheduler can't see it. Until this is done, the daily job still downloads and processes bulletins, but the site only updates when a session deploys it.

## Non-converging issues
- none

## Environment notes
- Efe's global npm registry points at an expired private CodeArtifact (E401). Project node tooling must use the public registry (a repo `.npmrc`, or `npm_config_registry=https://registry.npmjs.org/`). Don't change his global config.
