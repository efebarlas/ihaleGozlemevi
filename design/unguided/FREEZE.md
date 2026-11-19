# Unguided baseline: frozen (SPEC §9.2, Phase 1)

- **Frozen:** 2026-11-19, by the orchestrator. Git tag `design-unguided`.
- **Code at freeze:** commit `07179fa`, the audit fixes applied. The direction exists only in the preview build (`python -m ihale build --design-preview` → `site/preview/`, gitignored). It has never been deployed, and `deploy()` refuses preview output.
- **Data snapshot used for screenshots:** the export generated `2026-11-19T11:15:46+03:00` (mal + hizmet + yapım, bulletins 2026-10-21 … 2026-11-19, 18,966 records). The direction screenshots were taken earlier, on the mal-only export of 2026-11-19 (13,830 records).
- **Isolation:** neither reviewer read any other project's design files, and no preference or held-back feedback was asked for or passed on. Both reviewers were fresh-context agents, briefed with the exact text in `briefs/`.

## Contents
- `briefs/direction-reviewer.md`, `briefs/audit-reviewer.md`: the exact briefs, verbatim.
- `tokens/*.css`: the proposed token sets. The recommended one is the preview default.
- `consumer/style.proposed.css`: the stylesheet that reads only the tokens.
- `rationale-direction.md`: the direction reviewer's rationale, recommendation and measured contrast.
- `audit.md`: the audit reviewer's findings, measurements, verdict ("freeze after fixes"), and the "Fixes applied" table.
- `screenshots/directions/`: each direction at 375 px, light and dark.
- `screenshots/audit/`: every page type audited at 375 px, light and dark.
- `screenshots/applied/`: the applied default after the fixes.

## Open at freeze (all "nice" severity, or wording for the spec owner)
- Audit items 10–14 in `audit.md`. Item 14 ("belirgin biçimde" in the idare-rate flag text) is a wording call for the spec owner.

Phase 2 (guided directions, blind comparison) is run by the spec owner. Its outcome goes in `design/DIRECTION.md`.
