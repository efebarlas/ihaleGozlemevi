"""Idare comparison runs within the record's usul_turu (like with like), and the > 1 ratio text."""
from datetime import date

import pytest

from ihale.flags import compute_flags, money_tr, percent_tr
from ihale.store import StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)
DMO = "ÖRNEK MERKEZİ ALIM KURUMU"   # a central purchasing body (stand-in for DMO, which is scored like any other idare)
G = "4734 / 3-g"
SUBE = "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ ŞUBE {}"


def run(*recs):
    stored = [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]
    out = compute_flags(stored)
    return [out[s.id] for s in stored]


def mk(i, idare, tek, usul="Açık", day=D):
    r = rec(1, day=day, ikn=f"2026/{i}", idare=idare, yuklenici=f"Firma {i}",
            toplam=1 if tek else 3, gecerli=1 if tek else 3)
    r.ihale_usulu = usul
    return r


def group(n, tek_n, usul, fmt, start):
    return [mk(start + i, fmt.format(i), i < tek_n, usul) for i in range(n)]


def test_dmo_3g_is_not_unusual_against_other_3g_buyers():
    dmo = [mk(i, DMO, True, G) for i in range(6)]                            # DMO: 100% tek, all 3-g
    others_3g = group(25, 25, G, "BAŞKA KURUM {}", 100)                 # other 3-g buyers: also 100% tek
    others_acik = group(40, 4, "Açık", "KONYA BELEDİYESİ {}", 500)           # open tenders: 10% tek
    a = run(*dmo, *others_3g, *others_acik)[0]
    st = a.idare_stats
    assert st["usul_turu"] == "istisna_3g" and st["usul_label"] == "4734/3-g (diğer idareler)"
    assert st["records"] == 6 and st["tek_gecerli_teklif"] == 1.0
    assert st["peer"]["records"] == 25 and st["peer"]["tek_gecerli_teklif"] == 1.0
    assert st["peer"]["label"] == "Türkiye'deki diğer idareler (mal, 4734/3-g (diğer idareler))"
    assert "idare_orani" not in a.part_codes


def test_without_the_procedure_split_the_same_idare_would_stand_out():
    # the same idare with open-tender peers only (no other 3-g awards): no comparison, no idare_orani
    dmo = [mk(i, DMO, True, G) for i in range(6)]
    others_acik = group(40, 4, "Açık", "KONYA BELEDİYESİ {}", 500)
    a = run(*dmo, *others_acik)[0]
    assert a.idare_stats["peer"] is None and "idare_orani" not in a.part_codes


def test_idare_orani_fires_within_the_same_procedure():
    own = [mk(i, DMO, True, G) for i in range(6)]
    peers = group(25, 5, G, "KONYA BELEDİYESİ {}", 100)                      # 20% tek among 3-g peers
    a = run(*own, *peers)[0]
    assert "idare_orani" in a.part_codes


def test_idare_rate_counts_only_awards_of_that_procedure():
    recs = [mk(i, DMO, True, G) for i in range(4)] + [mk(10 + i, DMO, True, "Açık") for i in range(4)]
    out = run(*recs)
    assert out[0].idare_stats["records"] == 4 and out[0].idare_stats["tek_gecerli_teklif"] is None
    assert out[4].idare_stats["usul_turu"] == "acik" and out[4].idare_stats["records"] == 4


def test_fallback_chain_stays_within_the_procedure():
    own = [mk(i, "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ", True, G) for i in range(5)]
    local = group(10, 1, G, SUBE, 100)                                       # 10 local 3-g peers (< 20)
    national = group(15, 3, G, "MUĞLA İL SAĞLIK MÜDÜRLÜĞÜ {}", 300)          # 15 more 3-g nationwide
    noise = group(50, 0, "Açık", SUBE, 700)                                  # lots of open-tender peers: ignored
    st = run(*own, *local, *national, *noise)[0].idare_stats
    assert st["peer"]["records"] == 25 and st["peer"]["label"] == "Türkiye'deki sağlık idareleri (mal, 4734/3-g (diğer idareler))"
    st2 = run(*own, *local, *noise)[0].idare_stats                           # only 10 same-procedure peers
    assert st2["peer"] is None


def test_unknown_procedure_has_no_idare_stats():
    r = mk(1, DMO, True)
    r.confidence["ihale_usulu"] = 0.2
    (a,) = run(r)
    assert a.idare_stats is None and "idare_orani" not in a.part_codes


def test_elenen_peer_still_uses_all_procedures():
    own = mk(1, DMO, False, G)
    peers = [mk(10 + i, f"KONYA BELEDİYESİ {i}", False, "Açık") for i in range(6)]
    assert run(own, *peers)[0].indicators["elenen_orani_peer_n"] == 6


# ---------------------------------------------------------------- ratio > 1 text
def over(bedel, maliyet):
    (a,) = run(rec(1, bedel=bedel, maliyet=maliyet))
    return a.flags[0]["text"]


def test_over_estimate_text_has_excess_and_decimal_comma():
    assert over(4_067_000.0, 3_660_300.0) == "Sözleşme bedeli yaklaşık maliyetin 406.700,00 TRY üzerinde (%111,1)"


def test_over_estimate_one_percent_floored_never_rounded_up():
    assert over(100.99, 100.0).endswith("(%100,9)")


def test_over_estimate_uses_more_decimals_when_one_still_reads_100():
    t = over(1_000_000.50, 1_000_000.0)       # 100,00005 %: four decimals still floor to 100,0000
    assert t.startswith("Sözleşme bedeli yaklaşık maliyetin 0,50 TRY üzerinde (%100,00")
    t2 = over(1_000_100.0, 1_000_000.0)       # 100,01 %
    assert t2.endswith("(%100,01)")


def test_at_or_below_estimate_texts_unchanged():
    assert over(100.0, 100.0) == "Sözleşme bedeli yaklaşık maliyetin %100'ü"
    assert over(98.0, 100.0) == "Sözleşme bedeli yaklaşık maliyetin %98'i"


def test_helpers():
    assert money_tr(40_670_000, "TRY") == "406.700,00 TRY"
    assert money_tr(5, "EUR") == "0,05 EUR" and money_tr(123_456_789, "TRY") == "1.234.567,89 TRY"
    assert percent_tr(1009, 1000) == "100,9" and percent_tr(1111, 1000) == "111,1"
    assert percent_tr(100_001, 100_000) == "100,001"
    assert percent_tr(2, 1) == "200,0"


def test_kismi_over_text_has_excess():
    res = run(rec(1, ikn="2026/9", bedel=60.0, maliyet=100.0, yuklenici="A"),
              rec(2, ikn="2026/9", bedel=50.0, maliyet=100.0, yuklenici="B"))
    assert res[0].flags[0]["text"] == \
        "Bu ihalenin 2 kısmının toplam bedeli yaklaşık maliyetin 10,00 TRY üzerinde (%110,0)"
