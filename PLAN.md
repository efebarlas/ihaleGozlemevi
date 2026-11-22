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

- 2026-11-19: Efe chose Sütun in the blind comparison. Ported to the live build as the only direction (42c47e9), plus usul-share tables (513589f), simulated-user fixes (3e761af) and the identity guard (48f305a). **Not live yet:** the combined deploy failed safely ("File could not be uploaded" on the first D1 batch; nothing written; live site unchanged), and it needs ~48k D1 rows against the 100k/day free limit. The site builder is fixing batch size and compressing pages, and adding a dry-run. **Deployed 2026-11-19 17:26 UTC** after the fix (c0e6686: gzip BLOB pages, one row per page; 733be30: 80k daily budget guard with dry-run). Dry-run: 13,525 rows, 58,332 of 80,000 today. The D1 database shrank from 157 MB to 66 MB. Bulk pages answered 503 for about 8 s per batch during the import (about 3.5 min total). Verified live: Sütun stylesheet, noindex and charset on all pages, usul tables on idare pages, no maintainer identity, 404s.

- 2026-11-21/22: **Live data moved to Efe's SSD**: `E:\ihaleGozlemevi\live-data` (exFAT, label T7). Verified identical (same ihale.db SHA-256, integrity ok, same file list). Resolution: `$IHALE_DATA_DIR`, else the pointer file `~/.ihaleGozlemevi-data-dir`, else the old default. The scheduled task sets IHALE_DATA_DIR itself. **Missing-data guard** (ab5a02f): if the folder or its ihale.db is missing (SSD unplugged), `data_dir()` raises and `run_daily.ps1` exits 7, doing nothing. A test run from E: outside the app worked except the deploy (no login, as before). Deployed 20 Nov data from E: (live). The old C: copy is deleted, except the EKAP limiter files, which the research scan started before the move still uses. A small backup of oracle, slugs and manifests is in `~/ihaleGozlemevi-small-backup`. D1 staging moved to the data dir and the empty-site deploy guards are in (d518c51). The last C: folder was deleted after the research scan switched to the E: limiter.

## Handoff to the "ai" Windows account (2026-11-21 19:00 PT)
Efe moved İhale Gözlemevi to the "ai" account. The yigit session family has stopped. Nothing under yigit calls EKAP or writes to `E:\ihaleGozlemevi\live-data` any more. The yigit `ihaleGozlemevi-daily` scheduled task is **disabled** (by the spec owner, not deleted).

**Live site:** https://ihale-gozlemevi.clearpile-reader-server.workers.dev (unlisted).
- **Data:** mal, hizmet and yapım, 21 Oct – 20 Nov 2026 (19,761 records), in the Sütun design.
- **Last deploy:** 2026-11-21 ~18:35 PT. It includes the table_first peer classifier, the 0.7 confidence floor and the 30-award peer minimum (commit cd3e0a0 and earlier). Evidence: the live DB was re-flagged at 18:23 and exported at 18:26, and the D1 manifest was written at 18:35 by that deploy. Live, İzFAŞ (2026-11-20-hizmet-B-3) shows the peer "Türkiye'deki belediye şirketleri", which only exists after the 30-minimum change.
- **D1 usage on 2026-11-22 UTC:** 20,164 rows written (`d1-usage.json`).

**Cutover done under "ai" (2026-11-21 ~19:00 PT, spec owner):**
- **Live data moved back to the internal drive:** `C:\Users\ai\ihaleGozlemevi-data`. That's the code's default, so there's no pointer file. Writing was quiet since 18:51. The copy was verified: same 8,502 files and sizes, same ihale.db SHA-256, integrity ok, 19,761 records. BLOCKED, `ihale.db.pre-m5a` and the half-done M5a state came across unchanged.
  - The E: copy was renamed to `E:\ihaleGozlemevi\live-data-backup-2026-11-21` and kept as a backup. Anything still pointed at the old path now fails loudly (exit 7).
  - `research-archive` stays on E:.
  - Wherever this file says `E:\ihaleGozlemevi\live-data` below, read `C:\Users\ai\ihaleGozlemevi-data`.
- **Daily task `ihaleGozlemevi-daily-ai`** at 21:30, as user ai: interactive logon, start-when-available, 2 h limit. yigit's disabled task still holds the old name.
  - It puts Node (fnm, `C:\Users\ai\.fnm\aliases\default`) on PATH itself and passes the script's exit code through.
  - Test-run from Task Scheduler: it read the C: data dir and exited 3 on BLOCKED, as designed.
- Unattended deploys still need Efe's Cloudflare login (he does it himself). Pushing needs a GitHub credential under ai.

**Hard stop cleared 2026-11-21 19:08 PT by Efe** ("Checked, clear it"). The marker text is archived in `logs/BLOCKED-cleared-2026-11-21.txt`. The 60/day shared cap still applies. The record below is kept for history.

**Hard stop (SPEC §7, EKAP login wall, 2026-11-21 18:15/18:16 PT, research job):** `E:\ihaleGozlemevi\live-data\BLOCKED` stays until Efe clears it. Every entry point and the EKAP client itself refuse while it exists, and there is a shared cap of 60 requests per UTC day (75d5699).

**Done since M4 (all on main):**
- M4 is complete: hizmet/yapım, Dosyalar, D1 page store (gzip, dry-run plus 80k daily budget guard, empty-site guards), the classifier experiment and table_first promotion, the simulated-user fixes, the identity guard and the Sütun port.
- The data dir is on the SSD (pointer file plus missing-data guard).
- **M5a** (1ce5254, c3dc9c1): the parser stores `downloaders`, `yuklenici_adresi` and `yuklenici_il` (schema v6). The address goes to the DB and raw_fields only, and a privacy test guarantees it never reaches export or site. Labels score 100% for downloaders and il, and 100% for the address on mal; two misses on hizmet/yapım are label errors ("Nıda", "Iş Merkezı" are printed with dotless ı).
- **M5b** (a044c34): rule-anchored signals as indicators only (`idare_stats.usul_signal`, `indicators.pazarlik_21b`, `downloader_bid_ratio`), plus base_rates tables. No score points.
- **M5c draft** (f343de1): the idare scorecard computation is a document only.

**Half-done:**
- **M5a DONE (2026-11-22, orchestrator):** all 22 stored days re-parsed from cached files (no EKAP), 19,761 records, integrity ok; parsed fields identical to the pre-reparse backup (`ihale.db.pre-m5a-reparse`), only score/flags were reset and recomputed by `flag`. Address and downloaders reach neither export nor site (only a field name in `unreadable`). `build` + deploy dry-run: 0 changed pages (the new columns are private), 0 D1 rows, so live is unchanged and still correct. The two hand labels were fixed to the printed text ("Nıda", "Iş Merkezı"). 914 tests pass.
- **M5g DONE (2026-11-22, orchestrator; spec owner's scoring-precision milestone):** (1) `structural.marka_belirli`: DMO order + brand/model word in the title (whole word, dotless-insensitive; list in `structural.BRANDS`) -> no points for tek_teklif, elenen, bedel_orani, idare_orani, repeat pair; flags stay visible; 104 records, hand check 20/20 matched are brand orders, 0/20 of unmatched single-bid DMO titles were (all medical/pharma), recall on non-medical single-bid ~86% before the list was extended. Pharma 'SAĞLIK MARKET' single-bid DMO orders (8.43) are NOT touched: a different cause (sole-source drugs), a possible follow-up. (2) `belediye-sirketi`: hand list `structural.IN_HOUSE` with public sources (Sayıştay reports: Er Konut A.Ş. of Erzurum BB, Ulaşımpark A.Ş. of Kocaeli BB), same-municipality match required; no tek_teklif / repeat points, 9 records. The auto list from belediye_sirketi idare names was NOT built (idare and winner names rarely match; a false merge is worse). (3) bedel baseline: per-ikn median price/estimate is 0.677 for >=4 valid bids vs 0.829 for 2-3 and 0.929 for 1 bid (the 0.419 appears only per-record, dividing one lot's bedel by the whole tender's estimate). Partial awards (ratio<0.2, estimate covers lots not awarded in that record) are 9.4% of 4+ tenders (16% of mal), the rest is the real price-competition effect. Scoring is unaffected (flag fires at ratio>=0.97); the peer median is display only, no change made. Bugün 2026-11-20: 64 -> 61 (out: Iveco Eurocargo 16.88, Skoda Superb, Komatsu loader; none in); month >=3: 2,287 -> 2,178. Deployed through the guard (4,547 D1 rows; 22,384 of 80,000 today). Backup `ihale.db.pre-m5g`.
- **Next:** M5c (idare scorecard), M5d (drift monitoring), M5e (Sayıştay feasibility, <=10 requests), backfill ramp decision after 3 clean nights.
- **Label fixes, two hand labels in `tests/labels/downloaders_address_2026-11-18.json`:** hizmet A-17 "Nıda" and yapım A-9 "Iş Merkezı" should be corrected to the printed text after a page check.

**Next (`docs/m5-plan.md`):**
- **c:** the IMCO scorecard implementation, then its page.
- **d:** drift monitoring.
- **e:** Sayıştay feasibility, at most ~10 polite requests, another host.
- **f:** history backfill, blocked by the hard stop. It also needs Efe's approved daily budget, and none is approved.
- **g:** the GTI weight fit, after history.

**Spec-owner answers recorded for "ai":**
- **(1)** The research archive holds no raw bulletins: the zips were deleted after parsing. It has only pdftotext text (`text/*.txt.gz`, ~99 bulletin-days) and `archive.db` (~11.3k records over 15 scattered dates). Reusing it is ai's call, and it saves few requests.
- **(2)** No backfill budget is approved. That's Efe's decision under "ai", after the block clears.
- **(3) Storage recommendation:** per-tender pages for recent months; older years on İdare/Yüklenici pages and day lists. 16 years of pre-rendered pages would be ~13 GB, against D1's 5 GB free.

**Human checks still open:**
- **Cloudflare login:** the one-time Cloudflare login for unattended deploys (`scripts\cloudflare_login.cmd`). Under "ai" this needs re-doing for that account's wrangler config.
- **Publisher decision:** who publishes, at G-Public.

## Milestones
| | Milestone | State |
|---|---|---|
| M0 | Fresh base | done (c46d8ce, 95cfd4b; verified: 35 offline tests pass, 18.11.2026 mal/hizmet/yapım bulletins downloaded) |
| M1 | Adopt ihalent | done (e096656; verified: adapter over ihalent 0.5.1 scores 100% correct+confident on all 6 core fields over 69 hand labels; ihalent alone 95.7% on bedel because it drops EUR; 626/626 notices, ToC complete; 69 s per day) |
| M2 | Store and flag | done (cc13bd4; 534 tests; 30-day backfill 13,830 records; rarity-weighted score within procedure, value weight, 3-g DMO split, typo rule; oracle candidates) |
| M3 | Site v1, unlisted, with the daily run | live 2026-11-19 at https://ihale-gozlemevi.clearpile-reader-server.workers.dev (noindex header + meta, robots disallow, verified). Daily task `ihaleGozlemevi-daily` at 21:30 PT registered and test-run outside the app: everything works except deploy, which waits on the one-time Cloudflare login (human check). Until then a session deploys. |
| M4 | Dosyalar and better peers | done. Done: hizmet/yapım, İdare/Yüklenici pages, OCDS/FtM exports (private), D1 page store (live). Blocked: KİK decisions/debarment (EKAP sign-in wall). Classifier: table wins (97.5% vs 89%), shadow then promote. Simulated-user check done (5 personas, about 85 requests, no blockers, no broken links). The fix batch (units, chip counts, rounding, the 'yakın' label above 100%, kısmi caveat, il filter, pazarlık share vs peers) is with the builders, to ship in one deploy. |
| M5 | Weights, rules and history | in progress at handoff: a (code done, re-parse half-done) and b done, c drafted; plan in `docs/m5-plan.md`: offline pieces first (parser gap, rule signals, IMCO scorecard, drift); Sayıştay feasibility; history backfill blocked by the EKAP hard stop and the bulk-backfill rule |

## Backfill (M5f)
History fetcher, **fetch only**: `ihale backfill-history` (src/ihale/backfill_history.py) walks back from the day before the oldest stored day (derived from the DB) over Mon-Fri (no holiday list; a holiday costs up to 3 requests once, then is remembered), types mal, hizmet, yapim, into the bulletins cache only. No parse, no DB, no site. Days with a cached zip or in `<data>/no-bulletin.txt` cost nothing; stops at 2010-01-01 (`--earliest`).
- **Budget:** 150 requests per run (`--max-requests`; the form GET counts). Shared cross-process cap is now 200 per UTC day (150 backfill + headroom for the daily run's ~10-25). Spacing: random 150-240 s between requests (`--min-gap-seconds`, `--max-gap-seconds`) on top of the 10 s RateLimiter.
- **Window:** only inside `--window-utc` (default 22:00-04:30 UTC = 01:00-07:30 TRT); outside it the command logs and exits 0 without a request, so a manual start cannot burst by day. A run that outlives the window stops.
- **Exit codes:** 0 done / run budget used / outside window, 3 BLOCKED (marker written, evidence saved), 5 shared daily cap, 1 error (unexpected page: stops, a human looks).
- **Task:** `scriptsegister_tasks.ps1` (idempotent) registers `ihaleGozlemevi-backfill-ai` (14:00 local PC time = 01:00 TRT on PST; 8 h limit) and refreshes `ihaleGozlemevi-daily-ai` (trigger kept; 2 h limit). Both Interactive/Limited, on battery OK. The PC runs US Pacific: when it is on PDT the 14:00 trigger lands at 21:00 UTC, outside the window, so that day does nothing; shift the trigger by an hour then.
- **Progress:** `<data>/logs/backfill-progress.log` (one line per request: UTC time, day, type, fetched|no_bulletin, requests_today; START/STOP lines), `<data>/backfill-state.json` (counts, oldest_reached, stop_reason, next_day), `<data>/logs/scheduler-backfill-YYYY-MM-DD.log`.
- **Stop:** `Disable-ScheduledTask ihaleGozlemevi-backfill-ai`, or create/keep `<data>\BLOCKED` (any block writes it itself; nobody deletes it but Efe).
- **Block evidence:** whenever the block detector fires, the response body is saved to `<data>/logs/blocked-responses/<UTC ts>-<type>-<day>.html|.bin` with a `.json` sidecar (status, content type, reason, headers), to tell a false positive (2026-11-21: bare "giriş yap") from a real login wall. The detector itself is unchanged.
- Parsing the fetched history into the DB/site is a separate, later step (D1 size and file-count limits above).

## Queued for later milestones (SPEC §6.2 release policy)
- M4: each İdare page shows its procedure mix over time (açık / pazarlık incl. 21/b / istisna) and its volume trend, so displacement stays visible.
- M4: reconcile our single-valid-bid rate (29.1% per tender, mal only, 21 days, 65% of records 3-g) with İhaleGlobal's ~43% once hizmet and yapım are loaded; compute the comparable figure and explain any gap in Yöntem.
- M4: split 3-g base rates into "3-g DMO" and "3-g others" (DMO is 8,308 of 8,964 3-g records), so other 3-g buyers aren't measured against DMO's norms.
- After M5 planning (parser): store `downloaders` (3a 'Dokümanı EKAP üzerinden e-imza kullanarak indiren sayısı') and `yuklenici_adresi` (4f). ihalent drops the address row on purpose, so it has to be recovered in the wrapper from the PDF words. Store only, no flags until the spec owner has measured base rates. Addresses of natural persons are never displayed (KVKK). Re-parse the stored bulletins.
- M5: drift monitoring (incl. DMO against its own history, contract §4.1.1).
- G-Limited (new, before G-Public): invited readers behind Cloudflare Access.
- G-Public: dated t0 baseline snapshot; legal review; who publishes; validated weights.
- Launch is pull-only: no bots or push alerts aimed at named bodies.

## Decisions needed (Efe)
- **HARD STOP (SPEC §7, EKAP block), 2026-11-21 18:15/18:16 PT:** the spec owner's research backfill got two login-wall responses. `E:\ihaleGozlemevi\live-data\BLOCKED` is set, and all runs exit 3 without contacting EKAP. Efe decides when it's cleared. No session probes, retries or deletes the marker. The site stays up with data through 20 Nov. Hardening in progress (code only): marker check inside the EKAP client, plus a cross-process cap of 60 requests per UTC day.
- (spec owner) Who publishes the site: the footer GitHub link, which shows Efe's account, was removed until this is decided (G-Public item).

## Human checks queued
- **Cloudflare login for the daily job (one-time, about 1 minute).** Double-click `scripts\cloudflare_login.cmd` in the repo folder (outside the Claude app), then click "Allow" in the browser. Optional: until then a session deploys after each daily run. Why: the Claude app keeps its own private copy of the Cloudflare login, and Windows Task Scheduler can't see it. Until this is done, the daily job still downloads and processes bulletins, but the site only updates when a session deploys it.

## Non-converging issues
- none

## Environment notes
- Efe's global npm registry points at an expired private CodeArtifact (E401). Project node tooling must use the public registry (a repo `.npmrc`, or `npm_config_registry=https://registry.npmjs.org/`). Don't change his global config.
