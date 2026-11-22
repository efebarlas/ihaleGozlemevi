# M5e: Sayıştay audit reports, feasibility (2026-11-22)

Checked with **6 requests** to `sayistay.gov.tr` (budget was about 10), one at a time, 12 s apart, honest generic
client name, no cookies kept, nothing sent to EKAP. Nothing was stored in the repo; the downloaded PDF stays in the
scratchpad.

## Access
| What | Result |
|---|---|
| `robots.txt` | 200; it holds only a `Sitemap:` line, no Disallow rules |
| Sitemap (`/sitemap.xml`) | 200, 80 KB, 436 URLs, 28 report category pages (`/reports/category/<n>-<slug>`) |
| Category page, e.g. `31-belediyeler---bagli-idareler` | 200, 10 reports per page, about 324 pages (about 3,200 reports: belediyeler and their affiliated bodies) |
| Report page `/reports/<id>-<slug>` | 200, lists the report year and a download link |
| Download `/reports/download/<id>-<slug>` | 200, `application/pdf`, direct, no login, no CAPTCHA, no challenge |
| `HEAD` requests | answered 418 once (the server does not like HEAD); a normal GET of the same URL worked. Use GET only, no retries. |
| Terms of use | no terms page found in the footer or sitemap (only `/etik`, an ethics page, and "© 2026"). Not reviewed legally; the reports are official audits presented to the TBMM. |

## Format
One report fetched: Adana Büyükşehir Belediyesi, "2025 Yılı Sayıştay Denetim Raporu", Ekim 2026: **118 pages, 1.5 MB, a real
text layer** (257k characters; pdfplumber reads it, no OCR). 30 of the 118 pages mention ihale / 4734. Findings are
numbered headings ("BULGU 6: …") followed by the legal basis (for example 2886 md. 75, 4734 md. 3/g) and the audit
paragraph. Titles carry the idare name and year, so linking to our idare keys needs name matching (the same
`normalize_key` rule; a false merge is worse than a miss).

## Verdict
**Feasible, low technical risk.** Plain polite GETs, text PDFs, and a clean listing structure.

## Proposed second §11 agent-module experiment (not started; needs the spec owner's go and a request budget)
- **Task:** extract, per report, the findings that are procurement-related (BULGU heading, legal basis, idare, year),
  behind a seam like the parser's; link to idare keys.
- **Sample:** about 40 reports (belediyeler, including the 6 big büyükşehir files we already know) for independent hand
  labels of "is this finding procurement-related, which law article"; keywords vs the agent module A/B; shadow only.
- **Request budget needed:** about 40 PDF downloads plus a few listing pages, over several days at one request per
  ~12 s or slower. That is more than the "about 10" in the plan, so it needs approval.
- **Use on the site:** none yet. A Sayıştay finding is a different kind of fact (an audit opinion about a named public
  body); SPEC §6.1 says wording and linkage need care. First output would be a private table of findings per idare to
  see whether it adds signal; nothing public without the spec owner.
- **Open points:** the legal reuse terms (no terms page found; only republish short, sourced facts and link to the
  report), the report year lag (2025 reports published in October 2026), and name matching of idare vs report title.
