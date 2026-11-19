"""Peer-group proxy for idare comparisons (docs/data-contract.md §4.1).

The bulletin has no sector or province field, so: `idare_turu` from keywords in the idare *name*, `il` from
exactly one of the 81 province names in the idare *name* (never the yüklenici address), sector = bulletin type.
"""
from __future__ import annotations

import re

from . import classify
from .keys import turkish_lower, _tokens

# (keywords, turu) checked in order; a keyword is a lowercase substring unless listed in _TOKEN_ONLY.
IDARE_TURU_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("belediye",), "belediye"),
    (("üniversite",), "üniversite"),
    (("hastane", "sağlık"), "sağlık"),
    (("su ve kanalizasyon",), "su-kanalizasyon"),
    (("jandarma", "emniyet", "polis"), "güvenlik"),
    (("millî eğitim", "milli eğitim", "okul"), "eğitim"),
    (("karayolları",), "karayolları"),
    (("dsi", "devlet su işleri"), "dsi"),
]
_TOKEN_ONLY = {"dsi"}   # too short to match inside other words
OTHER = "diğer"

TURU_PLURAL = {
    "belediye": "belediyeler", "üniversite": "üniversiteler", "sağlık": "sağlık idareleri",
    "su-kanalizasyon": "su ve kanalizasyon idareleri", "güvenlik": "güvenlik idareleri",
    "eğitim": "eğitim idareleri", "karayolları": "karayolları idareleri", "dsi": "DSİ idareleri",
    OTHER: "diğer idareler",
}

TURU_PLURAL = {**TURU_PLURAL, **classify.TURU_PLURAL}      # the new taxonomy's codes (classify.py)

PROVINCES = (
    "Adana Adıyaman Afyonkarahisar Ağrı Aksaray Amasya Ankara Antalya Ardahan Artvin Aydın Balıkesir Bartın Batman "
    "Bayburt Bilecik Bingöl Bitlis Bolu Burdur Bursa Çanakkale Çankırı Çorum Denizli Diyarbakır Düzce Edirne Elazığ "
    "Erzincan Erzurum Eskişehir Gaziantep Giresun Gümüşhane Hakkari Hatay Iğdır Isparta İstanbul İzmir Kahramanmaraş "
    "Karabük Karaman Kars Kastamonu Kayseri Kilis Kırıkkale Kırklareli Kırşehir Kocaeli Konya Kütahya Malatya Manisa "
    "Mardin Mersin Muğla Muş Nevşehir Niğde Ordu Osmaniye Rize Sakarya Samsun Siirt Sinop Sivas Şanlıurfa Şırnak "
    "Tekirdağ Tokat Trabzon Tunceli Uşak Van Yalova Yozgat Zonguldak").split()

# Common short forms that name the same province (matched as whole words).
_ALIASES = {"afyon": "Afyonkarahisar", "maraş": "Kahramanmaraş", "antep": "Gaziantep", "urfa": "Şanlıurfa"}

_PROV_BY_TOKEN = {turkish_lower(p): p for p in PROVINCES} | _ALIASES


def _legacy_idare_turu(name: str | None) -> str:
    if not name:
        return OTHER
    low = turkish_lower(name)
    toks = set(_tokens(low))
    for kws, turu in IDARE_TURU_KEYWORDS:
        for kw in kws:
            if (kw in toks) if kw in _TOKEN_ONLY else (kw in low):
                return turu
    return OTHER


def _legacy_il_of(name: str | None) -> str | None:
    """The one province named in the idare name (whole-word match), else None (none or several)."""
    if not name:
        return None
    found = {_PROV_BY_TOKEN[t] for t in _tokens(turkish_lower(name)) if t in _PROV_BY_TOKEN}
    return next(iter(found)) if len(found) == 1 else None


def idare_turu(name: str | None) -> str:
    """Peer type of an idare. `legacy` (default) = today's rules; otherwise the classifier named by
    $IHALE_PEER_CLASSIFIER (keywords | table | hybrid), see classify.py."""
    impl = classify.peer_classifier()
    if impl == "legacy":
        return _legacy_idare_turu(name)
    return classify.classify(name, impl).turu or "diger"


def il_of(name: str | None) -> str | None:
    impl = classify.peer_classifier()
    if impl == "legacy":
        return _legacy_il_of(name)
    return classify.classify(name, impl).il


def locative_ki(place: str) -> str:
    """'Antalya' → "Antalya'daki", 'İzmir' → "İzmir'deki", 'Tokat' → "Tokat'taki" (harmony + voiceless final)."""
    low = turkish_lower(place)
    last_vowel = next((c for c in reversed(low) if c in "aıoueiöü"), "a")
    back = last_vowel in "aıou"
    voiceless = low[-1] in "çfhkpsşt"
    return f"{place}'{'t' if voiceless else 'd'}{'a' if back else 'e'}ki"


SECTOR_LABEL = {"mal": "mal", "hizmet": "hizmet", "yapim": "yapım"}


def peer_label(scope: str, turu: str, il: str | None, sector: str, usul: str | None = None) -> str:
    """scope: 'turu_il' | 'turu' | 'sector'. `usul` (e.g. "4734/3-g") is added after the sector."""
    sec = SECTOR_LABEL.get(sector, sector)
    if usul:
        sec = f"{sec}, {usul}"
    if scope == "turu_il":
        return f"{locative_ki(il)} {TURU_PLURAL[turu]} ({sec})"
    if scope == "turu":
        return f"{locative_ki('Türkiye')} {TURU_PLURAL[turu]} ({sec})"
    return f"Tüm idareler ({sec})"
