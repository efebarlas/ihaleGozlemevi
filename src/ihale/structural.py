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
        id="dmo-3g",
        prefix="DEVLET MALZEME OFİSİ",
        usul_turu="istisna_3g",
        effects=(NO_SINGLE_BID_POINTS, OWN_PEER_GROUP),
        reason_tr=("Devlet Malzeme Ofisi merkezî alım kurumudur; 4734/3-g kapsamındaki seri, markaya özgü "
                   "alımlarında tek teklif yapısı gereğidir."),
        match_tr="İdare adı «DEVLET MALZEME OFİSİ» ile başlar ve usul 4734/3-g'dir",
        added="2026-11-19",
    ),
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
    return [r.as_meta() for r in RULES]
