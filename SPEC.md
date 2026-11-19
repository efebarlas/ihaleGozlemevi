# İhale Gözlemevi: SPEC

Owner: the spec-owner session (Efe's decision proxy). Only that session edits this file. Decided with Efe on 2026-11-18.

## 1. Goal

A public-interest **watchdog over Turkish public procurement**. Every day it reads EKAP's new result bulletins (sonuç ilanları), pulls out each awarded contract, and shows the ones worth a second look, with the facts behind each and a link to the source bulletin.

**Audience:** Turkish-speaking journalists, researchers and curious citizens.

**Core benefit:** in about a minute, someone can see which tenders, idares and contractors look unusual, and check the figures behind them. Rank work by this: correct data and clear flags first, polish later.

### Flags (v1)
- **Tek geçerli teklif:** the tender had only one valid bid.
- **Bedel / yaklaşık maliyet:** contract price compared to the estimate. Prices very close to or above the estimate stand out.
- **Tekrarlayan yüklenici:** the same contractor keeps winning at the same idare.
- Later: share of pazarlık usulü (negotiated) procurement per idare, and price trends.

## 2. Non-goals
- Lead finding or alerts for bidders.
- Accusations. The site states facts and never gives verdicts.
- Anything that needs an EKAP login, or a paid service.

## 3. Product shape
- A static site on Cloudflare (free tier, a Worker with static assets on Efe's account), built from exported data. The UI is in Turkish and designed for phones first.
- **Pages:**
  - **Bugün:** today's flagged tenders.
  - **İhale detayı:** all fields, the flags, and a link to the source bulletin (date and page).
  - **İdare** and **Yüklenici** pages.
  - **Yöntem:** how each flag is computed and its limits.

## 4. Pipeline
**The 2022 code is disposable** (Efe, 2026-11-18). Reuse a piece only where it helps, e.g. its notes on bulletin layout and its field names. Rewrite or replace everything else freely, including the language, the libraries and Selenium.

1. **Scrape:** download the day's bulletin zip from EKAP's BultenIndirme.aspx. Prefer a plain HTTP form post; use a headless browser only if a form post doesn't work. As of 2026-11-18 the page still has the same form controls, and there is no CAPTCHA or login wall.
2. **Parse:** split the bulletin into tender records, each with a per-field confidence.
3. **Store:** a local SQLite database.
4. **Flag:** compute the flags from that data.
5. **Export:** write JSON for the site.
6. **Build and deploy:** build the static site and deploy it with wrangler.
- **Order of coverage:**
  1. *mal* result bulletins, from today forward.
  2. *hizmet* and *yapım*.
  3. Backfill to 2010 at a polite rate.
- **Runs on Efe's PC**, once a day via Windows Task Scheduler, in the evening after bulletins are out. Stale data while his PC is off is acceptable.

## 5. Quality bar
- Parser tests run offline against small fixture PDFs in `tests/fixtures/`. No test may hit EKAP.
- Measure field accuracy against a hand-labeled sample. Target ≥95% on the core fields: ikn, idare adı, yüklenici, sözleşme bedeli, yaklaşık maliyet, geçerli teklif sayısı.
- A flag is computed only from fields that parsed confidently. Otherwise the site shows "okunamadı" and computes no flag.

## 6. Care with data and people
- **Facts, not verdicts.** Use neutral wording, e.g. "tek geçerli teklif", "sözleşme bedeli yaklaşık maliyetin %99'u". Never use "şüpheli", "yolsuzluk" or similar. Every flag links to its source.
- **Real persons.** Some contractors are sole proprietors, so they are named people (KVKK). Show only what the official bulletin publishes. Never enrich it from other sources.
- **Unlisted until Efe says otherwise.** Use noindex and a robots disallow, and don't link the site anywhere.
- **Polite to EKAP:**
  - Download sequentially, at most one file per ~10 s.
  - No disguises.
  - If EKAP blocks us, adds a CAPTCHA or requires a login, stop scraping and report. Never work around it.
- **The repo is public.** Never commit secrets, tokens or bulk raw PDFs. Bulletins stay local and gitignored, except the small test fixtures.

## 7. Autonomy
**Standing OKs:**
- Commit and push to `main` on the public GitHub repo.
- Create and deploy a free-tier Cloudflare Worker for this project on Efe's account.
- Run the scraper on Efe's PC, and register its daily scheduled task. Tell him when it's registered.

**Hard stops** (escalate to Efe, work on other things meanwhile):
- Making the site public: indexable, or shared or linked anywhere.
- Money: a paid plan, a payment method, a new account.
- EKAP blocking, CAPTCHA or login.
- Irreversible git operations on `main` (force-push, history rewrite).

## 8. Operating model
This works like clearpile:
- **Spec owner:** Efe's interface. It owns SPEC.md and PLAN.md, decides for Efe, and escalates only the hard stops in §7.
- **Orchestrator:** a session that runs the milestones and starts one builder session per milestone. Builders run on Sonnet at medium effort.
- **Questions** go to the spec owner, never to Efe.
- **Human checks** are asynchronous. They queue in PLAN.md and don't block work.
- **Non-convergence:** an issue that keeps recurring gets reuse or scope-cut options, never blocks, and is reported to the spec owner.

## 9. Daily check
Efe opens the live site on his phone. The spec owner gives him a 3-line note: what changed on the site, what's next, and anything only he can decide. The note describes what he will see, not process.

## 10. Milestones
- **M0 Fresh base:**
  - Set up a clean project skeleton. Starting from scratch is fine.
  - Remove the dead parts: the committed `chromedriver.exe` and the Heroku files.
  - Download today's bulletins again.
  - Get offline fixture tests passing.
- **M1 Parse:** turn *mal* result bulletins into records with confidence, scoring ≥95% on the labeled sample.
- **M2 Store and flag:** SQLite, the three v1 flags, and a JSON export.
- **M3 Site v1 (unlisted):**
  - Deploy Bugün, İhale detayı and Yöntem on Cloudflare.
  - Run the pipeline daily on Efe's PC.
  - This gives the first daily check with real data.
- **M4 Breadth:** İdare and Yüklenici pages, plus *hizmet* and *yapım* bulletins.
- **M5 History:** backfill at a polite rate, and add trends.
- **G-Public:** Efe decides whether to go public.
