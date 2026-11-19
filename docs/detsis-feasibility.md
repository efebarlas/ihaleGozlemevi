# DETSİS as an independent check on `idare_turu` (feasibility, 2026-11-19)

**Verdict: dropped for now (unreachable from this machine; nothing usable verified).**

## Requests (3 live, budget ~5; each >= 10 s apart through `ekap.RateLimiter`, honest UA, no retries)
| # | request | result |
|---|---|---|
| 1 | GET `https://www.detsis.gov.tr/` | connect timeout (WinError 10060, 15 s) |
| 2 | GET `https://detsis.gov.tr/` (bare host, 25 s timeout) | connect timeout |
| 3 | GET `http://www.detsis.gov.tr/` (port 80) | connect timeout |

DNS is fine (`www.detsis.gov.tr` and `detsis.gov.tr` both resolve to 212.174.186.107), other Turkish government hosts (`ekap*.kik.gov.tr`, `resmigazete.gov.tr`) answered from the same machine and network within the hour, and the three attempts differed only in host spelling and port. The host never completed a TCP handshake, so there is no HTTP status, no CAPTCHA, no login page and no terms text to report. A silent connect timeout is how IP/geo filtering usually looks, but I cannot tell that from an outage. I stopped at 3 of 5: more attempts at the same address would not add evidence and would start to look like retrying around a block.

## What is known without the site (web search only, unofficial sources)
- Public lookup is described as going through detsis.gov.tr "Genel Arama" (by unit name or the 8-digit DETSİS number) and then "Künyesine Git" for a unit's record. One guide says only top-level units can be searched directly, with no direct drill-down into sub-units.
- No official source found for whether the search needs e-Devlet, for a response format, or for terms of use. The only structured DETSİS data path I know of is EKAP v2's `/b_idare/api/DetsisKurumBirim/DetsisAgaci`, which sits behind the same sign-in/Turnstile gate documented in `docs/kik-feasibility.md`. It is not usable, and third-party clients that get around that are out of scope.

## Consequence for the idare taxonomy check
Nothing to map. If DETSİS is ever reachable (e.g. from another network; the spec owner may know whether it is open from Efe's own PC), the 50-name check would be, per name: 1 search request (name -> candidate units with DETSİS no.) + 1 künye request for the chosen unit (type and parent chain), about 100 requests at 10 s spacing, roughly 17 minutes. The mapping would need a table from DETSİS organization types (merkezi idare/bakanlık, il özel idaresi, belediye, üniversite, KİT, ...) to the 19 codes in `docs/idare-taxonomy.md`, and would stay coarse: DETSİS does not separate `saglik`, `meb_okul`, `dsi`, `karayollari`, `dmo`, `tcdd`, `enerji_kit`/`diger_kit` or `tsk_guvenlik` from `bakanlik_tasra`/`merkezi_idare` except through the parent unit's name. It could only confirm the coarse family (central, local, university, public company), not the 19-way label. Do not schedule it until a single manual browser visit confirms the site is open and shows the unit type and parent on the künye page.
