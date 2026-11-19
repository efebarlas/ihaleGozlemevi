"""Per-record indicators (docs/data-contract.md §4.2). Values only: they are not part of the score yet."""
from __future__ import annotations

import re
from datetime import date

from .keys import turkish_lower

OPEN_USUL = ("acik", "belli_istekliler")


def usul_turu(usul: str | None) -> str | None:
    """Map the verbatim ihale_usulu to a code: acik, belli_istekliler, pazarlik_21a..f, istisna_3x,
    dogrudan_temin_22x (or dogrudan_temin), else diger. None for an empty input."""
    if not usul or not usul.strip():
        return None
    low = turkish_lower(usul).strip()
    if low.startswith("açık"):
        return "acik"
    if low.startswith("belli"):
        return "belli_istekliler"
    m = re.search(r"md\.?\s*21\s*[-/ (]*([a-f])\b", low) or re.search(r"\b21\s*[/-]\s*\(?([a-f])\)?", low)
    if "pazarlık" in low and m:
        return f"pazarlik_21{m.group(1)}"
    m = re.search(r"4734\s*/\s*3\s*[-/ ]?\s*\(?([a-z])\)?\b", low)
    if m:
        return f"istisna_3{m.group(1)}"
    if "doğrudan" in low or re.search(r"\b22\s*[-/ ]\s*\(?[a-g]\)?", low):
        m = re.search(r"22\s*[-/ ]?\s*\(?([a-g])\)?\b", low)
        return f"dogrudan_temin_22{m.group(1)}" if m else "dogrudan_temin"
    return "diger"


def acik_olmayan(usul_code: str | None) -> bool | None:
    return None if usul_code is None else usul_code not in OPEN_USUL


def elenen_orani(toplam: int | None, gecerli: int | None) -> float | None:
    """Share of bids disqualified, (toplam - gecerli) / toplam, defined for toplam >= 2."""
    if toplam is None or gecerli is None or toplam < 2 or gecerli < 0 or gecerli > toplam:
        return None
    return (toplam - gecerli) / toplam


def karar_suresi_gun(ihale: date | None, sozlesme: date | None) -> int | None:
    """Days from ihale_tarihi to sozlesme_tarihi; negative or missing → None."""
    if ihale is None or sozlesme is None:
        return None
    d = (sozlesme - ihale).days
    return d if d >= 0 else None
