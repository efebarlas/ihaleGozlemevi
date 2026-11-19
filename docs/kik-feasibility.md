# KİK Kurul kararları and yasaklılar: feasibility (2026-11-19)

Investigation with 9 live requests in total (limit ~10), >= 10 s apart through `ekap.RateLimiter` (same limiter file), honest UA from `ihale.config`, no retries. Samples are in `tests/fixtures/kik/`. The only guard code is `src/ihale/kik.py` (response classifier), tested in `tests/test_kik.py`.

## Requests made
| # | request | result |
|---|---|---|
| 1 | GET `ekap.kik.gov.tr/EKAP/Vatandas/KurulKararSorgu.aspx?KararTip=2` | 200, 16 KB: the **EKAP v2 Angular shell** (`<base href="/">`, `main.*.js`), not the old WebForms form |
| 2 | GET `ekap.kik.gov.tr/EKAP/Vatandas/main.<hash>.js` | 404 (my wrong asset path) |
| 3 | GET `ekap.kik.gov.tr/main.<hash>.js` | 404 (that host serves the shell only) |
| 4 | GET `ekapv2.kik.gov.tr/sorgulamalar/kurul-kararlari` | 200, byte-identical shell (16 326 B) |
| 5 | GET `ekapv2.kik.gov.tr/main.<hash>.js` | 200, 175 KB bundle; routes are lazy chunks, so no endpoint list in it |
| 6 | POST `ekapv2.kik.gov.tr/b_ihalearama/api/Ihale/GetListByParameters` (plain JSON, no signature) | **429** `API_QUOTA_EXCEEDED`, `HAN.EXCEPTIONS.KURUM_IP_KOTASI.API_QUOTA_SIGN_IN`, `suggestSignIn: true`, `retryAfterSeconds: 3600` |
| 7 | GET `www.resmigazete.gov.tr/robots.txt` | 200; only per-bot `Noindex:` lines for Googlebot/Bing/Slurp/Yandex, no `Disallow` and no `User-agent: *` |
| 8 | GET `www.resmigazete.gov.tr/eskiler/2026/11/20261118.htm` | 200, plain static page |
| 9 | GET `www.resmigazete.gov.tr/ilanlar/eskiilanlar/2026/11/20261118.htm` | 200, 44 KB static Word-exported HTML linking `...-2.htm` ... `-5.htm` |

Request 6 was a deliberate single unsigned probe of a *public* v2 endpoint to learn whether the API accepts plain clients. It does not. I stopped there: the 429 is a sign-in/quota wall (SPEC §6: login wall = hard stop). No further requests to `ekap*.kik.gov.tr` were made, and none should be made from this IP for at least an hour.

## Verdicts

### KİK Kurul kararları (board decisions) via EKAP: BLOCKED
- The legacy URL `ekap.kik.gov.tr/EKAP/Vatandas/KurulKararSorgu.aspx` is no longer a form; it serves the v2 SPA, whose data comes from `ekapv2.kik.gov.tr/.../api/...` (POST JSON).
- That API refuses an unauthenticated client (429, sign-in suggested).
- Public open-source clients (saidsurucu/ihale-mcp, MIT; yargi-mcp, MIT, which has a KİK module) get past it only with a Cloudflare Turnstile verification cookie and AES-signed `X-Ekap-Sec-1..4` headers built from a key embedded in the front end (read from their public source, not tested by me). Reproducing that is circumventing bot detection. **Not an acceptable reuse alternative**, even though the licenses are permissive.
- Query by ikn: the v2 decision search filters (per the public page descriptions) are karar no, date, Resmî Gazete date, applicant, idare and free text; decision texts cite tenders as "2023/25302 İhale Kayıt Numaralı", so an ikn would be a text search, not a key.
- e-Devlet mirrors (`turkiye.gov.tr/kik-kurul-karar-sorgula`) need an e-Devlet login: wall.

### Yasaklı sorgulama (debarment) via EKAP / e-Devlet: BLOCKED (unprobed, same stack)
- EKAP's "Yasaklılık Sorgulama" is part of the same v2 application (and an e-Devlet service). Same API gate, plus login on e-Devlet. I did not send further requests to find its endpoint.

### Resmî Gazete ilan section for debarment notices: ACCESSIBLE, usable with extra work
- Yasaklama kararları are published in the Resmî Gazete ilan section and take effect on publication (4734 md. 58/4 per legal commentary), so the Gazette is the primary public record.
- The site is static HTML/PDF, no CAPTCHA, no login, robots.txt has no disallow. The per-day ilan index is `ilanlar/eskiilanlar/YYYY/MM/YYYYMMDD.htm` (Word-exported HTML, windows-1254) linking category pages `YYYYMMDD-2.htm` ... `-5.htm`; individual notices are PDFs `YYYYMMDD-<cat>-<n>.pdf` (category 4 in the examples found by search).
- Not verified (outside the request budget): which category page holds "ihale yasağı" notices on a given day, and how notice titles are worded. Notices name the firm (and sometimes the tax/ID number), the issuing body and the duration; corrections and court cancellations are published too. Terms of use were not read.
- Matching is by firm name (and VKN where printed), so false merges are a real risk (SPEC §6 and the contract §3 "conservative").

## Proposal (nothing implemented beyond the guards)
1. **Kurul kararları:** do not scrape. Options for the spec owner:
   (a) skip it for v1;
   (b) ask KİK for an official data/API channel (an email, which is outward contact and Efe's call);
   (c) link out only: on the İhale detayı page, show a link to the EKAP Kurul kararları search with the ikn as the search text, no data fetched by us.
   I recommend (c) now, (b) if Efe wants it.
2. **Yasaklılar from the Resmî Gazete (M5-sized, only if wanted):** a nightly job that fetches `YYYYMMDD.htm` of the ilan section (1 request) plus the category page(s) (1–2), keeps only titles that mention "yasak", and downloads those PDFs (a handful per week). That is about 3 requests/day plus about 3 PDFs/week, all to `resmigazete.gov.tr`, at the same 10 s spacing and with the same UA. Backfill is one day per request pair. Store the notice text as is and show on a yüklenici page only an exact normalized-name match with the notice date and a link, worded neutrally ("... tarihli Resmî Gazete'de ... süreyle ihale yasağı ilanı"), never as a flag on Bugün without a human-checked sample first.
3. If the spec owner wants the Gazette path, the first step is a 1–2 request verification of one day that has a yasaklama notice (find via search, then fetch the category page) to learn the title wording and the PDF text layout, then fixtures and a parser.
