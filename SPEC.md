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

### 6.1 Effects on those named (2026-11-19)
Every flag lands on someone. A wrong or decontextualized flag costs that organization, and the people in it, far more than it costs us. In Turkey it can also bring a defamation complaint, a disinformation charge, or a court-ordered access ban (erişim engeli) against the site. The rules below follow from that.

**Scrutinize the buyer, not the seller.** The idare is a public body that is legally accountable for its procurement, and it makes the decisions: specs, disqualifications, procedure. The yüklenici is a private party.
- Scores, rates and scorecards are only ever computed for idares.
- Yüklenici pages show history (awards, totals, timelines) with no score, no rank and no "risky firm" label.
- A firm appears in a flag only as a fact of the record. Example: "the same firm's third award from this idare in 12 months."

**Natural persons.** A yüklenici whose name has no company form (no Ltd., Şti., A.Ş., Kooperatif or similar) is probably a person.
- In lists, cards, rankings and anything shareable, show them as "Gerçek kişi yüklenici".
- Their name appears only on the tender detail page, exactly as the state printed it.
- Never name officials or commission members, even where a source prints them.

**Proportionality:**
- An idare-level rate needs n≥5 awards, and a ranking needs stacked evidence (already in place).
- Dosyalar and scorecards need enough history before any comparative statement is made.
- The bigger the claim, the more evidence it needs.

**Innocent explanations go next to every flag.** Each flag type carries its common legitimate reasons, on the Yöntem page and inline. Examples:
- Purchases from public suppliers named in 4734/3-e (prison and school workshops, DMO as a seller, TCDD, MKE and others) are single-supplier by law.
- Where an exclusion rests on our own judgment rather than on the law (e.g. DMO's 3/g series purchases), Yöntem labels it as a judgment, and an agent checks the reasoning against the records.
- 21/b can follow a real emergency.
- A repeat winner may be the only local supplier.

Where the data shows a known innocent cause, such as the procedure type or a declared emergency, say so or exclude the case.

**Anticipate gaming.** Flagged organizations adapt. They might arrange cover bids to avoid "tek teklif", split tenders, or move purchases into istisna or doğrudan temin, where they're out of view.
- Watch for drift. For example: single-bid rates fall while bedel stays near 100% of the estimate. Or an idare's EKAP volume drops while its istisna share rises.
- On the Yöntem page, state the limits of bulletin-only data in general terms. Never list the ways to avoid a flag: that would be an evasion guide (see §6.2).

**Don't provoke data closure.** If the bulletins come to look like a liability, the cheapest response for the state is to publish less. That would hurt everyone, not just us. So:
- keep a low, constructive profile;
- don't sensationalize;
- keep up the EKAP politeness rules (§6).

**Corrections.** Any figure found wrong is fixed and marked as corrected, with the date. Before G-Public there must be a working correction and reply channel.

**G-Public gate.** All of these must be true before Efe can say yes:
1. A Turkish media or press lawyer has reviewed the site, the wording and the method. This costs money, so it's Efe's call.
2. Efe has decided who publishes: him personally or an entity. Today the public repo is under his own name.
3. The correction and reply channel works.
4. The M5 weights are validated against outcomes. Unvalidated hand-set rankings don't go public.
5. A plan exists in case Turkey blocks access to the site.
6. The §6.2 baseline is frozen, and the escape-route view exists.

### 6.2 Release policy: raise accountability without pushing behavior out of view (2026-11-19)
Pressure can move bad behavior out of view: into procedures, channels or tricks the bulletins don't show. That's a net loss of transparency, so the goal isn't the most pressure. It's the most accountability for the least displacement.

1. **No cliffs to sit under.**
   - Show actual values with their peer context, e.g. "yaklaşık maliyetin %98,6'sı · benzer idarelerde ortanca %87". No public threshold labels like "≥ %97", whether in flags, chips or cards.
   - Scoring prefers continuous, peer-relative measures. Thresholds are fitted to data (M5), described on the Yöntem page with the date they took effect, and allowed to move with the data.
2. **Explain the method, not how to evade it.**
   - Yöntem says what is measured, why, and its general limits.
   - It never says which behaviors would avoid a flag.
3. **See the escape routes before adding pressure.** Before G-Public, every İdare page shows its procedure mix over time: açık vs pazarlık (including 21/b) vs istisna, plus its volume trend. Displacement then shows up as a visible, rule-anchored signal instead of vanishing. Add istisna and doğrudan temin result data where it can be fetched without bypassing EKAP's human verification.
4. **Freeze a baseline before publicity.** Backfilled history is pre-publicity by definition, because we didn't exist. At G-Public, freeze a dated "t0" snapshot of every idare's indicators. After launch, compare flagged and unflagged idares for displacement signs:
   - single-bid rates falling while prices stay at the estimate;
   - bunching of prices just under former thresholds;
   - a move to istisna, pazarlık or doğrudan temin;
   - EKAP volume dropping.

   Report what we find on the Yöntem page, including any harm we may have caused.
5. **Stage the audience.**
   - **G-Limited** comes before G-Public: invited readers only (journalists, researchers, council members), behind Cloudflare Access on the free tier.
   - Inviting people is contact, so it's Efe's call.
   - G-Public opens up only after the displacement signals have been watched for a while.
6. **Dose the pressure.** At launch the site is pull-only: no bots, no tagging agencies or officials, no push alerts aimed at named bodies. Any push mechanism is a later, separate decision by Efe.

## 7. Autonomy
**Standing OKs:**
- Commit and push to `main` on the public GitHub repo.
- Create and deploy a free-tier Cloudflare Worker for this project on Efe's account. Every deploy, manual or scheduled, goes through the dry-run budget guard. If today's D1 writes plus the projected rows would exceed 80% of the free daily writes, it writes nothing, prints both numbers and leaves the live site as it is. Budgets are enforced in code, not by estimates.
- Run the scraper on Efe's PC, and register its daily scheduled task. Tell him when it's registered.

**Hard stops** (escalate to Efe, work on other things meanwhile):
- Making the site public: indexable, or shared or linked anywhere.
- Money: a paid plan, a payment method, a new account.
- EKAP blocking, CAPTCHA or login. The pipeline's `BLOCKED` marker in the data dir halts every EKAP request until Efe clears it. Every process shares a cap of 60 EKAP requests per UTC day, enforced in the client. Bulk historical backfills need Efe's OK with a daily request budget. (First block: 2026-11-21, during a spec-owner research backfill.)
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

### 9.1 Günün sorusu: Efe as the oracle (from M3 on)
Efe gives at most **one verification a day**. It is the project's scarcest resource; spend it carefully.
- **Only what agents can't check:** newsworthiness, whether wording reads as neutral, Turkish context, and anything behind Efe's own login or hands. Never parsing, arithmetic, rendering or a news search.
- **Pick the question with the most value.** Each question states what its answer will change. If nothing would change, don't ask.
- **The format:**
  - one question, answered with buttons in under a minute, on his phone;
  - skipping is fine, and three skips in a row lower the frequency;
  - prefer pairwise choices over ratings. Ask about the thing the score measures, not novelty: "Rakamlara bakınca hangisi daha yakından incelenmeyi hak ediyor?" ("Looking at the figures, which deserves a closer look?"). Learned 2026-11-19: "more worth a reporter's time" mixed up exotic with warrants-checking, and Efe couldn't choose.
  - always offer "Ayırt edemiyorum" ("can't tell"), and log the reason. A can't-tell answer is data about the cards: they may lack the context needed to judge.
  - show each tender with the same context side by side: bid counts, bedel/yaklaşık maliyet with the peer median, the idare's rate with n, and what the item is.
- **Blinding:** when asking about newsworthiness, hide which party runs the idare.
- **Log every answer.** The spec owner writes it to `oracle/log.jsonl` in the local data folder (outside the public repo and the site, because these are Efe's own judgments) with the date, the question, the options shown, the answer and what it was meant to change. The answers are one rater's judgment, not ground truth.
- **Priority of questions:**
  1. Ranking calibration: pairwise tender choices that feed the M5 weights.
  2. Agent-vs-code disagreements that the hand-checked sample can't settle.
  3. Fairness of anything heading toward G-Public.
  4. Signal-discovery verdicts (M7).
- **The pipeline supplies candidates.** Each daily run writes `oracle/candidates.json` to the local data folder: a few tender pairs where the current score is least certain. Every tender has its fields and source link.

### 9.2 Visual direction (after M3, before G-Public)
Adapted from clearpile's R-Visual mechanism, made lighter.

**The look carries credibility.** It should read like a careful public record: a newspaper data desk or an annotated official document. It should not read like a startup dashboard.

**Neutral visual language is a rule, not taste:**
- No alarm red, warning icons or siren colors on flags. Flags look like marginal annotations on a document. A flag in alarm red is a verdict, whatever the words say.
- No color tied to political parties.
- The source link is always visually present, not buried.

**Phase 1, unguided.** Runs once real data is live.
- A fresh-context reviewer proposes 2–3 distinct directions, each grounded in this product rather than generic app conventions.
- Each direction is a **set of design tokens** (colors in light and dark, type scale, spacing, flag treatment) applied to the real Bugün and İhale detayı pages with real tenders. No static mocks.
- The builder applies the reviewer's recommendation, but only on a non-deployed preview. Efe is not asked to pick: a pick would already be guidance.
- **Blind until the comparison (Efe, 2026-11-19).** Efe must see neither version, nor descriptions of either, before both are presented to him unlabeled. The live site keeps its pre-design style until then: no direction, no switch. Design reports to the spec owner are status only, with no direction names or descriptions.

- No reviewer reads another project's design files. In particular, clearpile's `design/BRIEF.md` holds Efe's taste.
- Efe's own design guidance is private and never enters this public repo. The guidance itself, and Phase 2 work that quotes or reflects it, stay outside git; `.gitignore` guards `design/BRIEF.md`, `design/private/` and `design/guided/`. Only the unguided baseline and neutral outcomes are committed.
- After the direction is applied, a fresh reviewer runs a design audit of every page in light and dark at phone width, judged against these rules.

**Freeze the baseline** once Phase 1 and its audit are done:
- save `design/unguided/`: the token sets, both reviewers' rationale, and the screenshots;
- tag the commit `design-unguided`;
- tell the spec owner.

**Freeze requirement:** also save the exact briefs given to the direction reviewer and the audit reviewer, verbatim, in `design/unguided/briefs/`.

**Phase 2** is run by the spec owner after the freeze, apart from the main build. Its outcome, and what Efe decides from it, is recorded in `design/DIRECTION.md`. Until then, the live site keeps its pre-design style.

**Outcome (2026-11-19):** Efe chose Sütun blind. See `design/DIRECTION.md`; the files are in `design/chosen/`. The build ports it to the live site as the only direction, with no switch, and reruns the rule checks above.

### 9.3 Hold-off (all feedback, design included)
Adopted from clearpile (Efe, 2026-11-19).
- Efe may mark a piece of feedback as **"hold-off"**. The spec owner records it privately, outside the repo and the data folder, and **never relays it** to builders or reviewers.
- When the review phase that should cover it finishes, the spec owner tells Efe which held-back items the reviews caught and fixed on their own, and which they missed. The design audit in §9.2 is one such phase.
- Only the missed items are then released, as normal feedback.
- The share caught on their own tells Efe how hands-off he can get.
- **Builders and reviewers:** don't look for held-back items or ask about them, and don't treat a missing rule as permission. Review as thoroughly as if no one else were watching.

**"Default look" tells to avoid**, taken from clearpile's list and extended by the reviewer:
- generic rounded cards with soft shadows everywhere;
- indigo or purple gradients;
- emoji as icons;
- pill chips for everything;
- uniform spacing with no hierarchy;
- dark mode as a plain inversion.

**Ties:** readability and the neutral visual language win ties over style. That means WCAG AA contrast, 44 pt touch targets, numbers you can scan, and the source link present.

**One audit pass before G-Public:** screenshots of every page in light and dark, judged against the chosen direction and these rules.

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
  - Export `oracle/candidates.json` so Günün sorusu can start (§9.1).
  - Right after deploy: the visual direction pass (§9.2), running in parallel with M4.

The order from here was set by the spec owner on 2026-11-19, under Efe's delegation. The reasoning: trust and ranking quality first, breadth second, public-facing features last.

- **M4 Dosyalar and better peers:**
  - İdare and Yüklenici pages with continuity timelines.
  - Add the *hizmet* and *yapım* bulletins.
  - KİK board decisions: link out to EKAP's decision search, with the ikn to copy. Fetch nothing: since 2026-11-19 it sits behind a sign-in wall (§7 hard stop; never use Turnstile or signed-header clients). Debarment: parked until M5 (see M5).
  - **First agent-module experiment (§11):** sector and idare-type classification. A build session classifies every known idare name and item name once into a reviewed lookup table. Score it against keyword rules on the hand-checked sample, then run it in shadow mode, and promote it only if it wins. This makes real same-sector, same-type peers possible.
  - Export OCDS (via ocdskit) and FollowTheMoney, and run Cardinal on the export as a cross-check. The exports stay private until G-Public.
  - **Simulated-user check:** agent personas do real reporting tasks on the site, e.g. "find every award firm X won at idare Y". It catches broken flows; it says nothing about demand.
- **M5 Weights, rules and history:**
  - Backfill at a polite rate.
  - Fit the score's weights GTI-style, to outcomes and to the oracle's pairwise judgments. This replaces the hand-set weights.
  - Add the rule-anchored signals: 21/b and pazarlık share vs. peers.
  - Add the IMCO-style idare scorecard.
  - Link Sayıştay findings per idare. Their extraction is the second agent-module experiment.
  - Debarment from Resmî Gazete yasaklama notices, if the format check finds a reliable second identifier. Legal entities only; natural persons are never matched or shown. Show a match only on an exact normalized legal name plus a second agreeing identifier. Shown as a neutral, dated fact with a link, on yüklenici pages only: never on Bugün and never in the score.
- **M6 Kartlar:**
  - Shareable fact cards, still unlisted.
  - Unit price vs. a reference price, starting with fuel vs. EPDK.
  - Quantity extraction from the ilan notices, via a new reader joined to results by ikn. This is the third agent-module experiment.
- **M7 Signal discovery:**
  - Agents propose new risk patterns and test each against outcomes in the data.
  - Only patterns that pass reach Efe as Günün sorusu, and his verdict is the final gate.
  - The goal is a set of red flags validated for Turkey and documented on the Yöntem page.
- **G-Limited:** invited readers only, behind Cloudflare Access (§6.2). Efe decides.
- **G-Public:** Efe decides whether to go public, once the §6.1 gate conditions hold and the displacement signals have been watched during G-Limited.
- **After G-Public only:**
  - a read-only MCP tool server over our data, so people can bring their own agent;
  - usability tests with real journalists and council members;
  - right of reply;
  - A/B tests of card formats.

  These either create a public endpoint or contact real people.
- **Coverage note:** add doğrudan temin and istisna purchases only if they can be fetched without EKAP's human verification. Never work around it.

## 11. Agents inside the product
A module can be replaced by an agent only behind a seam:
- **One interface** with per-field confidence, a coded implementation, and an agent implementation.
- **An offline A/B test** on the hand-checked sample, measuring:
  - accuracy per field;
  - cost per record;
  - consistency: run the agent twice on the same input and check that it agrees with itself.
- **Shadow mode** in the daily run, with every disagreement logged.
- **Promotion on evidence only.** The best end state is usually a hybrid: code first, the agent only where code is unsure.

**Prefer a one-time lookup table** built by a build session over calling an agent at run time. Vocabularies like idare names and item names barely change, so this costs almost nothing.

**Never an agent:**
- flags, scores, peer statistics and the downloader;
- the final value of any number shown on the site. An agent may propose a value, but code must verify it.

Calling an agent at run time costs money per call, which is a §7 hard stop. A local model on Efe's PC is allowed only under a permissive license (Apache-2.0, MIT); Llama-style custom licenses don't qualify.
