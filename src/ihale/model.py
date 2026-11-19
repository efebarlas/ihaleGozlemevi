"""Shared record types. The contract between parse (M1), store/flag/export (M2) and the site (M3).

See docs/data-contract.md. Change these only together with that document.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# A field counts as "confident" (usable for flags) at or above this score.
CONFIDENT = 0.9

# Core fields: SPEC §5 accuracy target applies to these.
CORE_FIELDS = (
    "ikn",
    "idare",
    "yuklenici",
    "sozlesme_bedeli",
    "yaklasik_maliyet",
    "gecerli_teklif",
)


@dataclass(frozen=True)
class Money:
    """An amount exactly as printed. `kurus` is the amount * 100 as an int (no float rounding)."""
    kurus: int
    currency: str  # "TRY", "EUR", "USD", ... exactly the token printed after the number
    alt: "Money | None" = None  # dual figure, e.g. "47.407.500,00 TRY (1.072.475,00 EUR)"

    @property
    def amount(self) -> float:
        return self.kurus / 100


@dataclass
class Record:
    """One SONUÇ İLANI record (one award; kısmi tenders yield several records with the same ikn)."""
    # provenance
    bulletin_date: date
    bulletin_type: str            # "mal" | "hizmet" | "yapim"
    source_file: str              # e.g. "BULTEN_18112026_MAL_SONUC.pdf"
    section: str                  # "A" (4734 kapsamında) | "B" (kapsam dışı / diğer)
    seq: int                      # running number within the section, as printed
    page_start: int               # 1-based PDF page where the record starts
    page_end: int                 # 1-based PDF page where it ends

    # fields (None = absent or unreadable; see `confidence`)
    ikn: str | None = None
    title: str | None = None              # işin adı from the numbered title line
    idare: str | None = None              # unlabeled ALL-CAPS block, lines joined with a space
    ihale_tarihi: date | None = None
    ihale_turu: str | None = None
    ihale_usulu: str | None = None        # verbatim, e.g. "Açık", "Pazarlık (MD 21 B)", "4734 / 3-g"
    yaklasik_maliyet: Money | None = None
    esas_kisim_yaklasik_maliyet: Money | None = None
    konu: str | None = None               # "Adı" under "2- İhale konusu ..."
    toplam_teklif: int | None = None
    gecerli_teklif: int | None = None
    sozlesme_tarihi: date | None = None
    sozlesme_bedeli: Money | None = None
    sozlesme_suresi: str | None = None
    yuklenici: str | None = None
    yuklenici_uyrugu: str | None = None
    yuklenici_adresi: str | None = None

    # per-field confidence in [0, 1], keyed by the attribute names above.
    # Every field the parser attempted has an entry. Absent-by-layout fields
    # (e.g. yuklenici_uyrugu in the short layout) are left out.
    confidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # Every (part, label, value) triple the notice printed, verbatim, in order
    # (from ihalent's BulletinNotice.fields; part "0".."4"). Kept so later
    # milestones can read fields we don't model yet (e.g. "niteliği, türü ve
    # miktarı", pazarlık gerekçesi) without re-parsing old bulletins.
    raw_fields: list[tuple[str, str, str]] = field(default_factory=list)

    def confident(self, name: str) -> bool:
        return getattr(self, name) is not None and self.confidence.get(name, 0.0) >= CONFIDENT
