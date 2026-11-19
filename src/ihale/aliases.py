"""Parent-body aliases for idare names (M4 interim): clustering and the per-idare cap only.

A small, hand-kept table mapping idare-name prefixes (Turkish-casefolded, whole-word) to one parent body, each
entry with a short reason. It does NOT change scoring or the peer groups (those wait for the M4 classifier).
"""
from __future__ import annotations

from dataclasses import dataclass

from .keys import turkish_lower


@dataclass(frozen=True)
class Alias:
    prefix: str        # matched against the start of the idare name, Turkish-casefolded
    key: str           # parent body key (ASCII)
    name: str          # parent body display name
    reason: str        # why these names belong together


ALIASES: tuple[Alias, ...] = (
    Alias("DEVLET HAVA MEYDANLARI İŞLETMESİ", "dhmi", "DHMİ",
          "DHMİ Genel Müdürlüğü; havalimanı işletmeleri ve bölge müdürlükleri aynı kurumdur"),
    Alias("DEVLET MALZEME OFİSİ", "dmo", "DMO", "DMO Genel Müdürlüğü ve alım şubeleri aynı kurumdur"),
    Alias("TCDD", "tcdd", "TCDD", "TCDD işletmesi ve bölge müdürlükleri aynı kurumdur"),
    Alias("TÜRKİYE CUMHURİYETİ DEVLET DEMİRYOLLARI", "tcdd", "TCDD", "TCDD'nin açık adı"),
    Alias("DEVLET SU İŞLERİ", "dsi", "DSİ", "DSİ Genel Müdürlüğü ve bölge müdürlükleri aynı kurumdur"),
    Alias("DSİ", "dsi", "DSİ", "DSİ'nin kısa adı"),
    Alias("KARAYOLLARI", "karayollari", "Karayolları",
          "Karayolları Genel Müdürlüğü ve bölge müdürlükleri aynı kurumdur"),
    Alias("TÜRKİYE ELEKTRİK İLETİM", "teias", "TEİAŞ", "TEİAŞ'ın açık adı; bölge müdürlükleri aynı kurumdur"),
    Alias("PTT", "ptt", "PTT", "PTT A.Ş. ve müdürlükleri aynı kurumdur"),
    Alias("ORMAN GENEL MÜDÜRLÜĞÜ", "ogm", "OGM", "OGM'nin merkez ve bölge/işletme müdürlükleri aynı kurumdur"),
    Alias("TÜRKİYE ŞEKER FABRİKALARI", "turksec", "Türkşeker", "Türkşeker'in fabrikaları aynı kurumdur"),
    Alias("ELEKTRİK ÜRETİM", "euas", "EÜAŞ", "EÜAŞ'ın açık adı; santraller ve işletmeler aynı kurumdur"),
)


def _fold(s: str) -> str:
    return " ".join(turkish_lower(s).split())


_FOLDED = tuple((_fold(a.prefix), a) for a in ALIASES)


def alias_for(idare: str | None) -> Alias | None:
    """The alias whose prefix starts the idare name as whole words (e.g. 'PTT' never matches 'PTTX')."""
    if not idare:
        return None
    name = _fold(idare)
    for pre, a in _FOLDED:
        if name.startswith(pre) and (len(name) == len(pre) or not name[len(pre)].isalnum()):
            return a
    return None


def parent_of(idare: str | None) -> dict | None:
    """{"key", "name"} of the parent body, or None when no alias matches."""
    a = alias_for(idare)
    return {"key": a.key, "name": a.name} if a else None


def table_meta() -> list[dict]:
    return [{"prefix": a.prefix, "key": a.key, "name": a.name, "reason": a.reason} for a in ALIASES]
