# İhale Gözlemevi: PLAN

Rules: SPEC.md is the source of truth, and only the spec owner edits it. The spec owner is Efe's decision proxy, so every question goes to it, never to Efe. It escalates only SPEC §7 hard stops. Human checks queue here and don't block work. Builders commit their own work, path-scoped, and never touch SPEC.md.

## Status
- 2026-11-18: direction set with Efe (SPEC.md). Next: M0 Fresh base. The 2022 code is disposable.
- 2026-11-18 evening: orchestrator started. M0 builder running (skeleton, polite plain-HTTP EKAP fetch, fixtures, layout notes). Wrangler is already logged in on Efe's account. Data lives off OneDrive in `%LOCALAPPDATA%\ihaleGozlemevi` (override with `IHALE_DATA_DIR`).

## Milestones
| | Milestone | State |
|---|---|---|
| M0 | Fresh base | in progress |
| M1 | Parse result bulletins (mal) | not started |
| M2 | Store and flag | not started |
| M3 | Site v1, unlisted, with the daily run | not started |
| M4 | Breadth | not started |
| M5 | History | not started |

## Decisions needed (Efe)
- none

## Human checks queued
- none

## Non-converging issues
- none

## Environment notes
- Efe's global npm registry points at an expired private CodeArtifact (E401). Project node tooling must use the public registry (a repo `.npmrc`, or `npm_config_registry=https://registry.npmjs.org/`). Don't change his global config.
