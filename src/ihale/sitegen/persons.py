"""Natural-person detection for yüklenici names (SPEC §6.1).

Conservative on purpose: `is_natural_person` is True only when the name has NO company-form or
business-word token. Anything ambiguous is treated as a company (its name is then shown as printed in the
official bulletin); a masked name is shown only on the tender detail page.
"""
from __future__ import annotations

import re
import unicodedata

PERSON_LABEL = "Gerçek kişi yüklenici"

# Whole-token matches (short forms that would false-hit as substrings, e.g. "aş" in "Aşkın").
_EXACT = {
    "ltd", "şti", "sti", "aş", "as", "koll", "kom", "co", "inc", "gmbh", "ltdşti",
    "san", "tic", "ort", "ve", "oda", "odası", "birlik", "vakıf", "dernek", "ortak", "girişim",
    "ticaret", "sanayi", "taahhüt", "ortaklığı",
}
# Substring matches inside a token (long, unambiguous stems).
_STEMS = (
    "limited", "şirket", "sirket", "anonim", "kooperatif", "komandit", "kollektif", "birliği", "birligi",
    "vakfı", "vakfi", "derneği", "dernegi", "üniversite", "müdürlü", "başkanlı", "belediye", "işletme",
    "kurumu", "holding", "ortaklı", "konsorsiyum", "ticaret", "sanayi", "inşaat", "insaat", "mühendislik",
    "nakliyat", "otomotiv", "medikal", "tekstil", "elektronik", "bilişim", "yazılım", "pazarlama", "makina",
    "makine", "hizmetleri", "hizmetler", "ürünleri", "ilaç", "gıda", "turizm", "temizlik", "güvenlik",
    "mimarlık", "danışmanlık", "ithalat", "ihracat", "dağıtım", "enerji", "kırtasiye", "tarım", "hayvancılık",
    "bakanlığı", "valiliği", "genel müdür", "hastane", "okul", "fakülte", "rektörlü", "şubesi", "merkezi",
)
_TR = str.maketrans({"İ": "i", "I": "ı"})


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFC", name).translate(_TR).lower()
    return s.replace("i̇", "i")


def is_natural_person(name: str | None) -> bool:
    """True only when `name` has no company-form token (Turkish-case-insensitive, punctuation tolerant)."""
    if not name or not name.strip():
        return False
    s = _norm(name)
    dotless = s.replace(".", "")                      # "a.ş." -> "aş", "ltd.şti." -> "ltdşti"
    tokens = [t for t in re.split(r"[^\w]+", dotless) if t]
    spaced = " " + " ".join(re.split(r"[^\w]+", s)) + " "
    if " ortak girişim" in spaced or " a ş " in spaced or " l t d " in spaced:
        return False
    if any(t in _EXACT or t.startswith("ltd") or t.endswith("şti") for t in tokens):
        return False
    if any(stem in t for t in tokens for stem in _STEMS):
        return False
    if len(tokens) < 2:                               # a single word is not a safe "person" signal
        return False
    return not any(ch.isdigit() for ch in s)
