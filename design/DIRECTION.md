# Visual direction: decision

**Decided 2026-11-19 by Efe, in a blind comparison.**

## How it was decided
Two design processes each produced three directions and one finished, audited version of the site:
- the frozen unguided baseline, in `design/unguided/` (tag `design-unguided`);
- a second run that used the same briefs, models, data snapshot and steps, plus product-owner guidance that stays private (SPEC §9.2).

Both finished versions were rendered the same way from the same data (phone width, light and dark). Efe saw them with random labels, after a vetting pass for giveaways, and the key was revealed only after he chose.

## Choice
**Sütun**, the second process's recommended direction: a newspaper data-desk column.
- Warm paper and serif text.
- Open, ruled entries instead of boxes.
- Flags are italic marginal notes behind a hairline rule.
- The source is set as a footnote citation with a bold arrowed link.
- Dark mode is a designed "night edition" (warm charcoal, softened ink, lighter rules), not an inversion.
- System fonts only.

The unguided pick was not chosen. It stays frozen as the baseline.

## What is in `design/chosen/`
| Path | What |
|---|---|
| `tokens/sutun.css` | The direction's token set: custom properties only, loaded before the consumer stylesheet. |
| `consumer.css` | The stylesheet that consumes the tokens, after the audit fixes (1 blocker and 8 should-fixes applied). |
| `visual.diff` | Template and code changes the direction needs, against commit `448d622`: day-page heading, hatched weekly-mix chart on İdare pages, flag lists and "Ayrıntı →" on Bugün cluster and fold entries, the `rec` heading and facts block on İhale detayı. |
| `screenshots/` | The finished version as Efe judged it: Bugün, Gün, İhale detayı and Yöntem, light and dark, 375 px wide. |

## Porting notes for the build
- `visual.diff` was made against `448d622`. `main` has moved on since, so port it by hand rather than with `git apply`.
- Do not port the preview-switch hunks in `tests/test_sitegen.py` (direction names in the preview build). The live site gets one direction and no switch.
- The rule fixes in the second run are already on `main` in their own form: source lines on dossier rows, sole-proprietor masking, and the neutral `bedel_orani` and `idare_orani` labels. Keep `main`'s versions.
- After porting, rerun the §9.2 rule checks on the live build: contrast, touch targets, no horizontal scroll at 375 px, source line on every card and row, masking and identity guards.
