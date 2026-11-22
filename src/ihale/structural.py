"""Structural single-bid rules (docs/data-contract.md §4.1.1, SPEC §6.1).

A small, explicit, public table of patterns whose single-bid structure has a known cause. Never a hidden special
case: every entry carries its reason in Turkish, shown on the record and in Yöntem. Add an entry only together
with a stated reason.
"""
from __future__ import annotations

from dataclasses import dataclass

from .keys import turkish_lower

NO_SINGLE_BID_POINTS = "no_single_bid_points"   # tek_teklif / diger_teklifler_elendi stay as facts, add no points
OWN_PEER_GROUP = "own_peer_group"               # compared only with its own history: no peer group in v1
PEER_NOTE = "Kendi geçmişiyle karşılaştırılır"


@dataclass(frozen=True)
class Rule:
    id: str
    prefix: str | None     # idare name prefix, Turkish-casefolded match; None = any idare
    usul_turu: str
    effects: tuple[str, ...]
    reason_tr: str
    match_tr: str
    added: str

    def as_meta(self) -> dict:
        return {"id": self.id, "match_tr": self.match_tr, "effects": list(self.effects),
                "reason_tr": self.reason_tr, "added": self.added}


RULES: tuple[Rule, ...] = (
    Rule(
        id="istisna-3e",
        prefix=None,
        usul_turu="istisna_3e",
        effects=(NO_SINGLE_BID_POINTS,),
        reason_tr=("4734 sayılı Kanun md. 3/e: alım, Kanunda adı sayılan kamu kuruluşundan (ör. ceza infaz "
                   "kurumu işyurtları, DMO, TCDD, Et ve Balık Kurumu) yapılır; tek tedarikçi Kanun gereğidir."),
        match_tr="Usul 4734/3-e'dir (idare fark etmez)",
        added="2026-11-19",
    ),
)


def _fold(s: str) -> str:
    return " ".join(turkish_lower(s).split())


def match(idare: str | None, usul_turu: str | None) -> Rule | None:
    """The first rule matching this idare name and usul_turu, else None."""
    if not idare or not usul_turu:
        return None
    name = _fold(idare)
    for rule in RULES:
        if usul_turu == rule.usul_turu and (rule.prefix is None or name.startswith(_fold(rule.prefix))):
            return rule
    return None


def rules_meta() -> list[dict]:
    return [r.as_meta() for r in RULES] + record_rules_meta()


# ---------------------------------------------------------------------------------------------- M5g (2026-11-22)
# Record-level structural rules: they look at the title or the winner, not only at idare + usul.
NO_COMPETITION_POINTS = "no_competition_points"   # tek_teklif, elenen, bedel_orani, idare_orani and repeat pairs add no points
NO_REPEAT_AND_SINGLE_POINTS = "no_repeat_single_points"   # tek_teklif, elenen and repeat-winner pairs add no points

DMO_PREFIX = "devlet malzeme ofisi"

# Brand / model words that a DMO order names. Narrow on purpose: vehicles, trucks, buses, tractors, construction
# machinery, motorcycles. Whole-word, Turkish-casefolded match against the işin adı. A word only counts as a
# brand when it stands for the maker; ambiguous words (man, case, ford alone is fine for Ford Trucks/Transit) are
# listed as multi-word phrases.
BRANDS: tuple[str, ...] = (
    "isuzu", "ford", "mercedes", "mercedes-benz", "actros", "renault", "dacia", "volkswagen", "fiat", "hyundai",
    "toyota", "iveco", "scania", "volvo", "bmc", "otokar", "karsan", "temsa", "togg", "kubota", "new holland",
    "massey ferguson", "john deere", "caterpillar", "jcb", "hidromek", "komatsu", "crown", "bmw", "suzuki",
    "yamaha", "honda", "kawasaki", "peugeot", "citroen", "citroën", "opel", "nissan", "mitsubishi", "škoda",
    "skoda", "kia", "tofaş", "tofas", "case cx", "case ih", "man tgs", "man tge", "man tgm", "man tgx",
    "mahindra", "tümosan", "erkunt", "tourneo", "transit", "novociti", "eurocargo", "boreal", "duster", "megane",
    "amarok", "proace", "hilux", "d-max", "t475s", "t460s", "cx220d", "hitachi", "hitaci", "linde", "çukurova", "netlift", "altekma", "asmaksan", "as-mak-san", "pilotcar", "green car", "case 695", "case856d", "kubato", "komsilaj", "t5.110", "mf 5m",
)

MARKA_BELIRLI_TEXT = ("Alım Devlet Malzeme Ofisi aracılığıyla ve belirli bir marka/model adıyla yapılıyor; "
                      "yalnızca o markanın yetkili satıcıları teklif verebildiği için tek teklif ve bedel/maliyet "
                      "oranı bu kayıtta puan eklemez. Olgular kayıtta görünür.")

IN_HOUSE_TEXT = "Yüklenici, ihaleyi yapan belediyenin kendi şirketidir ({kaynak}); tekrarlayan yüklenici ve tek teklif puan eklemez."


def _has_word(folded: str, phrase: str) -> bool:
    import re
    return re.search(r"(?<![\wçğıöşü])" + re.escape(phrase) + r"(?![\wçğıöşü])", folded) is not None


def marka_belirli(idare: str | None, title: str | None) -> str | None:
    """The matched brand word when a DMO order names a brand/model in its title, else None."""
    if not idare or not title or not _fold(idare).startswith(DMO_PREFIX):
        return None
    folded = _fold(title).replace("ı", "i")      # "ISUZU" folds to "ısuzu"; brand words are compared dotless-insensitively
    for b in BRANDS:
        if _has_word(folded, _fold(b).replace("ı", "i")):
            return b
    return None


# Municipality-owned companies, hand-confirmed from a public source (Sayıştay audit reports). A company is listed
# only with the source; a winner matches when its normalized name equals `name_key` AND the awarding idare is of
# the same municipality (`owner_prefix`, Turkish-casefolded prefix of the idare name).
@dataclass(frozen=True)
class InHouse:
    name_key_prefix: str       # normalize_key(yuklenici) must start with this
    owner_prefix: str          # idare name (folded) must start with this
    source: str
    source_url: str


IN_HOUSE: tuple[InHouse, ...] = (
    InHouse("er konut inşaat taahhüt", "erzurum büyükşehir belediye",
            "Sayıştay denetim raporu: Erzurum Büyükşehir Belediyesi'nin diğer belediye şirketlerinden ERKONUT A.Ş.",
            "https://www.sayistay.gov.tr/reports/download/5pokdBAgDW-erzurum-buyuksehir-belediyesi-ertansa-as"),
    InHouse("ulaşımpark ulaştırma hizmetleri", "kocaeli büyükşehir belediye",
            "Sayıştay 2023 denetim raporu: Kocaeli Büyükşehir Belediyesi tarafından 2016'da kurulan şirket (%99,99 belediye)",
            "https://sayistay.gov.tr/reports/download/peYMqJOYd9-ulasimpark-ulastirma-hizmetleri-ticaret-anonim-sirketi"),
)


def in_house(idare: str | None, yuklenici_key: str | None) -> InHouse | None:
    if not idare or not yuklenici_key:
        return None
    name = _fold(idare)
    for e in IN_HOUSE:
        if yuklenici_key.startswith(e.name_key_prefix) and name.startswith(e.owner_prefix):
            return e
    return None


def record_rule(idare: str | None, title: str | None, yuklenici_key: str | None) -> dict | None:
    """Record-level structural result: {"id", "text", "effects", ...} or None."""
    b = marka_belirli(idare, title)
    if b:
        return {"id": "marka-belirli", "text": MARKA_BELIRLI_TEXT, "marka_belirli": True,
                "effects": [NO_COMPETITION_POINTS]}
    h = in_house(idare, yuklenici_key)
    if h:
        return {"id": "belediye-sirketi", "text": IN_HOUSE_TEXT.format(kaynak=h.source), "belediye_sirketi": True,
                "kaynak_url": h.source_url, "effects": [NO_REPEAT_AND_SINGLE_POINTS]}
    return None


# ---------------------------------------------------------------------------------------------- M5h (2026-11-22)
# Peer categories: a narrow class of orders whose single-bid / price pattern has a structural cause gets its own
# peer group, so p is computed among like tenders. Points are NOT zeroed; the flags stay and ln(1/p) does the rest.
SAGLIK_MARKET = "saglik_market"
MEB_TASIMA = "meb_tasima"
CATEGORY_LABELS = {
    SAGLIK_MARKET: "DMO sağlık ve ilaç",
    MEB_TASIMA: "MEB taşımalı eğitim / araç kiralama",
}


def _sole_source_health(t: str) -> bool:
    """DMO health orders with a sole-source cause: Sağlık Market, J-coded drug lists, "ilaç" and enteral products.
    Consumables (tıbbi sarf A/B grubu, gloves) are left out: they usually have several suppliers."""
    import re
    if "sağlık market" in t or "enteral" in t or re.search(r"(?<![a-z0-9])j\d{4}(?![a-z0-9])", t):
        return True
    return "ilaç" in t and "ilaç haznesi" not in t


def _school_transport(t: str) -> bool:
    """`t` = folded işin adı + konu of a Milli Eğitim idare. Student transport: "taşımalı", a taşıma merkezi, or
    taşıma together with students / the school year. Meal transport and building moves don't count."""
    if "yemek" in t or "gıda" in t:
        return False
    if "taşımalı" in t or "taşıma merkez" in t:
        return True
    if "taşınması" in t and "öğrenci" in t:
        return True
    return "taşıma" in t and any(w in t for w in ("öğrenci", "öğretim yılı", "eğitim", "2026-2027", "2026/2027"))


def peer_category(idare: str | None, title: str | None) -> str | None:
    """`saglik_market`: DMO idare and a sole-source health title (Sağlık Market, J-code drug lists, ilaç, enteral). `meb_tasima`: Milli Eğitim idare and school transport in the işin adı + konu
    (`title` may carry both). Anything else None."""
    if not idare or not title:
        return None
    name, t = _fold(idare), _fold(title)
    if name.startswith(DMO_PREFIX) and _sole_source_health(t):
        return SAGLIK_MARKET
    if ("milli eğitim" in name or "millî eğitim" in name) and _school_transport(t):
        return MEB_TASIMA
    return None


def record_rules_meta() -> list[dict]:
    return [
        {"id": "marka-belirli", "match_tr": "İdare Devlet Malzeme Ofisi; işin adında marka/model adı geçiyor",
         "effects": [NO_COMPETITION_POINTS], "reason_tr": MARKA_BELIRLI_TEXT, "added": "2026-11-22"},
        {"id": "belediye-sirketi", "match_tr": "Yüklenici, ihaleyi yapan belediyenin kamuya açık kaynakla doğrulanmış şirketi: "
         + "; ".join(f"{e.name_key_prefix} ({e.source_url})" for e in IN_HOUSE),
         "effects": [NO_REPEAT_AND_SINGLE_POINTS],
         "reason_tr": "Belediyenin kendi şirketine verdiği iş, özel yüklenicilerin tekrar kazanmasıyla veya tek teklifle aynı anlamı taşımaz.",
         "added": "2026-11-22"},
    ]
