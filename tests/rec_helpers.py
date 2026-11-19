"""Synthetic Record factory for the M2 tests (no parser involved)."""
from datetime import date

from ihale.model import Money, Record

TRY = "TRY"


def money(amount: float, cur: str = TRY, alt: Money | None = None) -> Money:
    return Money(round(amount * 100), cur, alt)


def rec(seq=1, *, day=date(2026, 11, 18), type_="mal", section="A", ikn="2026/1", idare="ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ",
        yuklenici="Emir Sosyal Hizmetler Limited Şirketi", bedel=100.0, maliyet=200.0, esas=None,
        toplam=3, gecerli=3, conf=None, **kw) -> Record:
    r = Record(bulletin_date=day, bulletin_type=type_, source_file="BULTEN_18112026_MAL_SONUC.pdf",
               section=section, seq=seq, page_start=18, page_end=19, ikn=ikn, title="İŞİN ADI", konu="İşin adı",
               idare=idare, yuklenici=yuklenici, ihale_usulu="Açık", ihale_turu="Mal alımı",
               ihale_tarihi=date(2026, 10, 21), sozlesme_tarihi=date(2026, 11, 16),
               sozlesme_suresi="16.11.2026 - 31.12.2026",
               yaklasik_maliyet=money(maliyet) if maliyet is not None else None,
               esas_kisim_yaklasik_maliyet=money(esas) if esas is not None else None,
               sozlesme_bedeli=money(bedel) if bedel is not None else None,
               toplam_teklif=toplam, gecerli_teklif=gecerli, **kw)
    names = ["ikn", "title", "konu", "idare", "yuklenici", "ihale_usulu", "ihale_turu", "ihale_tarihi",
             "sozlesme_tarihi", "sozlesme_suresi", "yaklasik_maliyet", "esas_kisim_yaklasik_maliyet",
             "sozlesme_bedeli", "toplam_teklif", "gecerli_teklif"]
    r.confidence = {n: 1.0 for n in names}
    r.confidence.update(conf or {})
    return r
