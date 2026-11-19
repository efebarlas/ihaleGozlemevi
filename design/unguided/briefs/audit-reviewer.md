You are the design audit reviewer for İhale Gözlemevi (SPEC §9.2, Phase 1, unguided). You have fresh context. Another reviewer proposed visual directions, and a builder applied the recommended one to a non-deployed preview build. Your job is to audit that applied preview.

## Context
İhale Gözlemevi is a public-interest watchdog over Turkish public procurement, for Turkish-speaking journalists, council members and auditors of any party, and curious residents. Every day it reads the official Kamu İhale Bülteni and shows awards worth a second look, with neutral facts and a link to the source page. The site is in Turkish and built for phones first.
- The repo is at `C:\Users\yigit\OneDrive\Masaüstü\daily projects\ihaleGozlemevi`; work only inside it.
- Read `SPEC.md` §1, §3, §6, §6.1, §6.2, §9.2 and §9.3, and `design/unguided/rationale-direction.md`.
- Build the preview with `.venv\Scripts\python.exe -m ihale build --design-preview`. It writes to `site/preview/`, which is never deployed.
- Serve it locally with `.venv\Scripts\python.exe -m http.server 8766 --directory site/preview` (background), or use the built-in browser pane. The preview's default direction is the applied one. Audit that default; don't use the switch to judge other directions.

## Isolation (hard rule)
- Do not read any file outside this repo. In particular, never open any other project's design files, e.g. anything under `..\clearpile\`.
- Don't look for or ask about anyone's design preferences, and don't ask whether any feedback has been held back.
- Don't deploy anything, and don't edit the live stylesheet or templates.

## Task
Audit **every page type** at 375 px width in **light and dark**:
- Bugün, including cluster cards and fold lines;
- Gün summary and a paginated Gün page;
- İhale detayı for a flagged record and for a record with `okunamadı` fields, if any exist;
- Arşiv, Yöntem, the 404 page and an İdare or Yüklenici page, if they exist in the build.

Judge each page against these rules, which are not a matter of taste:
- **No alarm red, warning icons or siren colors** on flags. Flags read as marginal annotations.
- **No colors tied to Turkish political parties.**
- **The source link is visually present** on every card, row and detail page.
- **Readability:**
  - WCAG AA contrast (measure it);
  - touch targets ≥ 44 px (measure them in the DOM);
  - scannable money, with tabular figures and right alignment where numbers are compared;
  - correct Turkish characters;
  - no horizontal scrolling at 375 px;
  - long idare and konu text wraps cleanly.
- **Neutral wording:** check no verdict words appear (şüpheli, yolsuzluk, usulsüzlük…), persons are masked outside detail pages ("Gerçek kişi yüklenici"), and no threshold labels appear outside Yöntem prose.
- **"Default look" tells:** soft-shadow rounded cards everywhere, gradients, emoji icons, pill chips for everything, uniform spacing with no hierarchy, dark mode as plain inversion.
- **Hierarchy:** can a reader tell in five seconds what is unusual about a card and where its numbers come from?

## Deliverables
1. **Screenshots** of every page type, light and dark, at 375 px, in `design/unguided/screenshots/audit/` with descriptive filenames.
2. **`design/unguided/audit.md`:**
   - a table of findings with severity (blocker / should-fix / nice), the page, the mode, what you saw, the rule it breaks, and a concrete fix (a CSS selector and value, or a template change);
   - your measured contrast and touch-target numbers;
   - a verdict: freeze as-is, freeze after the listed should-fixes, or not freezable.

Commit only `design/unguided/audit.md` and `design/unguided/screenshots/audit/` with `git commit -m "..." -- <those paths>`, then push to `main`. Never force-push. Other sessions share this checkout; touch nothing else.

Review as thoroughly as if no one else were watching. Your final message gives the commit hash first, then the verdict and the count of blockers and should-fixes. Keep it to status: no direction names.
