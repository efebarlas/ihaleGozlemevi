"""KİK Kurul kararları / yasaklılar: feasibility guards only (see docs/kik-feasibility.md).

Finding (2026-11-19): neither source is cleanly reachable by a plain polite client.
  * ekap.kik.gov.tr/EKAP/Vatandas/KurulKararSorgu.aspx now serves the EKAP v2 single-page app shell, whose data API
    (https://ekapv2.kik.gov.tr/...) answers an unauthenticated client with HTTP 429 `API_QUOTA_EXCEEDED`
    (`suggestSignIn: true`, retryAfterSeconds 3600). Public client code reaches it only with a Cloudflare Turnstile
    verification cookie and signed `X-Ekap-Sec-*` headers; reproducing those would be circumventing bot detection,
    which SPEC §6 forbids.
  * The e-Devlet mirrors (turkiye.gov.tr) need a login.

So this module deliberately contains no client. It holds the detector that turns those responses into
`ekap.BlockedError`, so any future code path that touches EKAP v2 stops instead of retrying.
"""
from __future__ import annotations

import json

from .ekap import BlockedError

V2_HOST = "ekapv2.kik.gov.tr"


def is_spa_shell(html: str) -> bool:
    """True for the EKAP v2 Angular shell (no server-rendered form, data only via the signed API)."""
    low = html.lower()
    return "<base href=\"/\"" in low and "main." in low and ".js" in low and "<form" not in low


def classify_api_response(status: int, body: bytes | str) -> None:
    """Raise BlockedError for the quota / sign-in / auth answers of the EKAP v2 API; return None otherwise."""
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    info: dict = {}
    try:
        info = json.loads(text)
        if not isinstance(info, dict):
            info = {}
    except ValueError:
        pass
    if status in (401, 403, 407, 429, 511) or info.get("code") == "API_QUOTA_EXCEEDED" or info.get("suggestSignIn"):
        raise BlockedError(
            f"EKAP v2 API refused an unauthenticated client (HTTP {status}, code={info.get('code')!r}, "
            f"retryAfterSeconds={info.get('retryAfterSeconds')!r}). Stop and escalate; do not retry or work around."
        )
