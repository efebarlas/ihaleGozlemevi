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

**Base rates (2026-11-19).** On their own, these flags fire on a large share of all tenders. İhaleGlobal reports that about 43% close with a single valid bid, and that 67% of contracts go to a firm that has won from that idare before. These are their numbers and are unverified. A flag that fires on half of everything isn't a signal.
- **Rank Bugün by how unusual a tender is, not by whether a flag fired.**
- **What counts as unusual:**
  - several flags stacking on one tender;
  - the same idare–yüklenici pair repeating in tenders that also show those flags;
  - an idare whose rates are far above its peers in the same sector and province.
- **Show the peer comparison next to each figure**, e.g. "this idare: 80% tek teklif; peers in the same sector and province: 35%".
- **Measure the real base rates from our own data** before choosing thresholds.

### Users, signals and surfaces (2026-11-19)
**Positioning: the nonpartisan evidence layer.** Turkish procurement reporting already exists, but it is slow and partisan:
- Reporters build a firm's history by hand from EKAP's search.
- They read Sayıştay audit reports separately from the tender data.
- Stories often start from one party's tip about another party's municipality.

We apply the same measures to every idare regardless of party, join the public sources, and make every figure one tap from its official source.

**Users:**
1. Journalists.
2. Municipal council members and auditors of any party, who are often the source of those tips.
3. Local residents curious about their own municipality or hospital.

**Signals worth showing.** Prefer signals that are concrete, local, comparable and checkable over outrage:
- **Compound and peer-relative unusualness** (see Base rates above).
- **Rule-anchored behavior.** Exceptions the law says should be rare. Examples: frequent 21/b urgent negotiation since its 2025 narrowing, or an idare's share of pazarlık usulü vs. its peers. These rest on the rule, not on opinion.
- **Continuity timelines.** For example, "this firm won 14 of 15 cleaning tenders at this hospital since 2019." Show it as a dated sequence, not a verdict.
- **Unit price vs. a public reference price.** Starting categories:
  - fuel per liter vs. the EPDK pump price on that date;
  - vehicle rental per month;
  - later, construction items vs. the ministry's official birim fiyatlar.

  Show a category only once its quantity parsing is reliable.
- **What happened next.** KİK board decisions on the same tender, cancellations and re-tenders. Close loops; don't stop at the first flag.

**Surfaces:**
- **Bugün:** the daily ranked list of unusual awards. Aimed at journalists.
- **Dosyalar:** a page per idare and per firm. All its awards and totals, plus linked Sayıştay findings, KİK decisions and debarment status. This replaces an afternoon of manual EKAP lookups.
- **Kartlar:** shareable, self-contained fact cards. One figure, one comparison, one source link, in neutral Turkish. They work as an image on social media and invite the reader to check them.

**Public sources to join.** Check each source's terms before use, and fetch politely:
- EKAP result bulletins (we have these).
- Sayıştay audit reports, one per idare per year.
- KİK board decisions.
- EKAP's debarment list (yasaklılar).
- KİK's semiannual statistics, for baselines.
- EPDK fuel prices.
- The ministry's construction unit prices.

**Not now:**
- **Ticaret Sicili** (company founders and partners) is person-level enrichment, which goes against §6. Revisit only with Efe, after G-Public.
- **Automated social posting** (a bot) counts as going public, so it is a hard stop.

### Borrowed from abroad (2026-11-19)
All the code named below is permissive; licenses were checked on GitHub.

**Indicators: split "tek geçerli teklif" now (M2).** It follows the Open Contracting Partnership's red flags, as implemented in its Cardinal library.
- **"Tek teklif"** (Cardinal R018): only one bid was submitted.
- **"Diğer teklifler elendi"** (R035): more than one bid came in, but only the winner was valid. This is the stronger, more specific signal, because it can point to tailored specs or selective disqualification. It weighs more in the score than R018.
- **"Çok sayıda teklif elendi"** (R038): a high share of bids were disqualified, measured against peers.
- These come from the bulletin's total and valid bid counts, which we already parse.

**More GTI risk indicators (M2 if the fields exist, else M5).** These are the Government Transparency Institute's corruption risk indicators (Fazekas & Kocsis 2020, *British Journal of Political Science*), validated against price outcomes across many countries.
- **Non-open procedure** (pazarlık, 21/b).
- **Decision period:** the days from ihale tarihi to sözleşme tarihi. Unusually short or long periods stand out.
- **The winner's share of the idare's spending** in the window.
- **Advertisement period**, from the ilan date to the deadline. This one needs the ilan reader (M6).

**Validate weights with data, not guesses (M5).** Once history is loaded, follow GTI's method: keep and weight the indicators that actually predict worse outcomes in Turkish data, such as a higher bedel/yaklaşık maliyet ratio. Replace the hand-set +1/+2 weights with them, and publish the regression on the Yöntem page.

**An idare scorecard (M5, on İdare pages).** Follows IMCO's Índice de Riesgos de Corrupción (Mexico):
- a 0–100 score per idare, built from three sub-indices: competition, transparency and compliance with the rules;
- always shown with its components and n;
- framed as IMCO frames it: it measures risk, not cases.

**Standards and journalists' tools (M4):**
- Export our records as **OCDS**, the Open Contracting Data Standard, using `ocdskit` (BSD-3).
- Run OCP's **Cardinal** (`cardinal-rs`, MIT) on that export. Our flags are then computed by the international reference implementation, not only our own code.
- Also export **FollowTheMoney** entities with `followthemoney` and `followthemoney-ocds` (MIT). Journalists can load them into OCCRP's Aleph and cross-reference our data with company records and leaks.
- Publish the exports as downloadable files only after G-Public.

**Scraping more sources (M5).** For Sayıştay reports and municipal sources, follow the structure of Querido Diário (Open Knowledge Brasil, MIT): one Scrapy scraper per source, plus a shared pipeline.

**Fairness, after G-Public:**
- **Right of reply**, following DOZORRO (Ukraine): an idare or firm can send an explanation, shown next to the flag.
- **Ask the reader to verify**, following Serenata (Brazil): every Kart asks the reader to help check it rather than accusing anyone. A Kart might say "Bu bedel sizce makul mü? Kaynağa bakın." ("Does this price look reasonable to you? Check the source.")
- Both mean receiving inbound contact, so they are part of the G-Public decision.

**Watch, don't act:** KİK and the Rekabet Kurumu (competition authority) signed a protocol on AI-assisted competition analysis in procurement. The state may become a source of data or of legitimacy. Any contact with them is Efe's call.

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

### 4.1 Build on ihalent (Efe, 2026-11-19)
- **Use ihalent for the parsing and flags.** [ihalent](https://github.com/gulmezeren2-byte/ihalent) is an open-source library under the MIT license. It already fetches and parses result bulletins and computes the single-bid, near-estimate and HHI concentration flags.
  - Use it as a pinned dependency. Fork or wrap it only where it falls short.
  - Its required dependencies are permissive too: rich, typer and pdfplumber are MIT.
- **License gate.** Efe's condition is that we build on very permissive code only. Every dependency must be MIT, BSD, Apache-2.0, ISC or similar. Anything copyleft (GPL, AGPL, LGPL, MPL) is a hard stop: report it, don't add it.
- **Credit it.** Keep ihalent's MIT copyright notice in the repo. Name ihalent on the site's Yöntem page.
- **Our own value is what ihalent doesn't do:** a daily, phone-first feed of individual flagged tenders, each with neutral wording and a source link. Also the repeat-winner-per-idare view, if ihalent lacks it.
- **Keep our M0 downloader only if it beats ihalent's `fetch-bulletin`.** The EKAP politeness rules in §6 apply either way.
- **No upstream contact without Efe's OK.** Opening issues or pull requests on ihalent is outward-facing.

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
- Any dependency that isn't permissively licensed (see §4.1).
- Contacting outside projects or people, including issues or PRs on ihalent.

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
- **M1 Adopt ihalent:**
  - Pin it, and run it on our fixtures and on today's *mal* result bulletin.
  - Measure its core-field accuracy against a hand-labeled sample. The target is ≥95%.
  - Where it falls short, fix it in a thin wrapper or a fork.
- **M2 Store and flag:**
  - Load ihalent's awards into SQLite.
  - Use its single-bid and near-estimate flags, and add repeat-winner-per-idare if it lacks one.
  - Export JSON for the site.
- **M3 Site v1 (unlisted):**
  - Deploy Bugün, İhale detayı and Yöntem on Cloudflare.
  - Run the pipeline daily on Efe's PC.
  - This gives the first daily check with real data.
- **M4 Dosyalar:** İdare and Yüklenici pages with continuity timelines, plus *hizmet* and *yapım* bulletins. Link KİK board decisions and debarment status.
- **M5 Rules and history:**
  - Backfill at a polite rate.
  - Add rule-anchored signals (21/b and pazarlık share vs. peers).
  - Link Sayıştay findings per idare.
- **M6 Kartlar:**
  - Shareable fact cards.
  - Unit price vs. reference price, starting with fuel vs. EPDK.
  - Cards stay unlisted, like the site, until G-Public.
- **G-Public:** Efe decides whether to go public.
