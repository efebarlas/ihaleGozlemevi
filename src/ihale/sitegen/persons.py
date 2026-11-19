"""Natural-person detection for yüklenici names (SPEC §6, §6.1, KVKK).

Biased towards masking. Wrongly masking a company only hides a name outside its detail page.
Failing to mask a person exposes a private individual. So:

- A single name is a *company* only when it carries a legal-entity form: A.Ş. / Anonim Şirketi,
  Ltd. Şti. / Limited Şirketi, Koll. / Kom. Şti., Kooperatif, a public body, a foundation,
  association, union or chamber, or a foreign form (GmbH, Inc., LLC, S.A., B.V. …).
  Business words such as "İnşaat", "Ticaret", "Sanayi", "Medikal" or "Mühendislik" are NOT
  legal forms: Turkish sole proprietors (şahıs işletmeleri) use them in trade names, e.g.
  "Selim Karataş İnşaat Mühendislik". Such a name is a natural person.
- A joint venture (İş Ortaklığı, Ortak Girişim, Konsorsiyum, Adi Ortaklık) is treated as
  person-containing unless every partner segment carries a legal-entity form. Partners are split
  on commas, which may over-split company names that contain commas. That errs towards masking.
- A one-word name with no legal form is masked too (it may be a surname-only trade name).
"""
from __future__ import annotations

import re
import unicodedata

PERSON_LABEL = "Gerçek kişi yüklenici"

_TR = str.maketrans({"İ": "i", "I": "ı"})

# Legal-entity markers, matched on the normalised (lower-case, dots removed) text.
_FORM_TOKENS = {
    "aş", "as", "ltd", "şti", "sti", "ltdşti", "koll", "kom", "kollşti", "komşti",
    "gmbh", "inc", "llc", "plc", "corp", "sa", "spa", "bv", "nv", "ag", "srl", "sarl", "ab", "oy", "kg",
}
_FORM_STEMS = (
    "anonim şirket", "limited şirket", "kollektif şirket", "komandit şirket", "kooperatif",
    "şirketi",
    # public bodies and non-profits
    "belediye", "müdürlüğü", "müdürlügü", "başkanlığı", "baskanligi", "üniversite", "rektörlüğü",
    "valiliği", "bakanlığı", "kaymakamlığı", "kurumu", "kurum başkan", "genel müdür", "idaresi",
    "vakfı", "vakfi", "derneği", "dernegi", "birliği", "birligi", "odası", "odasi", "sandığı",
    "döner sermaye", "işletmesi müdür", "fabrikaları", "holding",
)
_JV_STEMS = ("iş ortaklığı", "is ortakligi", "ortak girişim", "ortak girisim", "konsorsiyum", "adi ortaklık")


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFC", name).translate(_TR).lower()
    return s.replace("i̇", "i")


def _has_legal_form(segment: str) -> bool:
    s = _norm(segment)
    spaced = " " + " ".join(t for t in re.split(r"[^\w.]+", s) if t) + " "
    if any(stem in spaced for stem in _FORM_STEMS):
        return True
    dotless = s.replace(".", "")
    tokens = [t for t in re.split(r"[^\w]+", dotless) if t]
    if any(t in _FORM_TOKENS or t.startswith("ltdşti") for t in tokens):
        return True
    # spaced-out forms: "a. ş.", "ltd. şti."
    compact = re.sub(r"[\s.]+", "", s)
    return compact.endswith("aş") and (" a.ş" in s or " a. ş" in s)


def is_joint_venture(name: str | None) -> bool:
    return bool(name) and any(j in _norm(name) for j in _JV_STEMS)


def is_natural_person(name: str | None) -> bool:
    """True when the name must be masked outside the tender detail page (see module docstring)."""
    if not name or not name.strip():
        return False
    if is_joint_venture(name):
        s = _norm(name)
        for j in _JV_STEMS:
            s = s.replace(j, " ")
        partners = [p for p in re.split(r"[,;/]| - ", s) if p.strip(" .-")]
        return not partners or not all(_has_legal_form(p) for p in partners)
    return not _has_legal_form(name)
