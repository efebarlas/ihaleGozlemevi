# İhale Gözlemevi: PLAN

Rules: SPEC.md is the source of truth, and only the spec owner edits it. The spec owner is Efe's decision proxy, so every question goes to it, never to Efe. It escalates only SPEC §7 hard stops. Human checks queue here and don't block work. Builders commit their own work, path-scoped, and never touch SPEC.md.

## Status
- 2026-11-18: direction set with Efe (SPEC.md). Next: M0 Fresh base. The 2022 code is disposable.
- 2026-11-18 evening: orchestrator started. M0 builder running (skeleton, polite plain-HTTP EKAP fetch, fixtures, layout notes). Wrangler is already logged in on Efe's account. Data lives off OneDrive in `%USERPROFILE%\ihaleGozlemevi-data` (override with `IHALE_DATA_DIR`).

- 2026-11-18 night: M0 done. EKAP answers a plain HTTP form post (no browser, no CAPTCHA). Data dir moved to `%USERPROFILE%\ihaleGozlemevi-data` because the Claude app silently redirects AppData writes, which Task Scheduler would not see. Shared contract for parser/flags/site: `docs/data-contract.md`, `src/ihale/model.py`. Next: M1 parser, M2 store/flag, M3 site generator, built in parallel against that contract.

## Milestones
| | Milestone | State |
|---|---|---|
| M0 | Fresh base | done (c46d8ce, 95cfd4b; verified: 35 offline tests pass, 18.11.2026 mal/hizmet/yapım bulletins downloaded) |
| M1 | Parse result bulletins (mal) | in progress (parser builder + independent labeler) |
| M2 | Store and flag | in progress |
| M3 | Site v1, unlisted, with the daily run | in progress (site generator; deploy and scheduling after M1/M2 land) |
| M4 | Breadth | not started |
| M5 | History | not started |

## Decisions needed (Efe)
- none

## Human checks queued
- (after M1) Spot-check 5 hand-labeled records against the bulletin PDF; the labeler will name them.

## Non-converging issues
- none

## Environment notes
- Efe's global npm registry points at an expired private CodeArtifact (E401). Project node tooling must use the public registry (a repo `.npmrc`, or `npm_config_registry=https://registry.npmjs.org/`). Don't change his global config.
