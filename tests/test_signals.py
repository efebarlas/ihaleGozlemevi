"""M5b rule-anchored signals: idare_stats.usul_signal, indicators.pazarlik_21b and downloader_bid_ratio (indicators only)."""
import json
from datetime import date

import pytest

from ihale.export import export_all
from ihale.flags import compute_flags_full
from ihale.pipeline import flag_all
from ihale.store import Store, StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)
SAGLIK = "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ"


def full(recs):
    res, _ = compute_flags_full([StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)])
    return [res[i + 1] for i in range(len(recs))]


def mk(i, usul="Açık", idare=SAGLIK, bedel=100.0, toplam=3, gecerli=3, type_="mal"):
    r = rec(i, type_=type_, ikn=f"2026/{i}", idare=idare, yuklenici=f"F{i} Ltd. Şti.", bedel=bedel, maliyet=bedel * 2,
            toplam=toplam, gecerli=gecerli)
    r.ihale_usulu = usul
    return r


def peers_of(n, usul="Açık", start=1000, bedel=100.0):
    return [mk(start + i, usul=usul, idare=f"MUĞLA İL SAĞLIK MÜDÜRLÜĞÜ {i}", bedel=bedel) for i in range(n)]


# ---------------------------------------------------------------- indicators.pazarlik_21b
@pytest.mark.parametrize("usul,expected", [
    ("Pazarlık (MD 21 B)", True), ("Açık", False), ("Pazarlık (MD 21 F)", False), ("4734 / 3-g", False)])
def test_pazarlik_21b_indicator(usul, expected):
    (a,) = full([mk(1, usul=usul)])
    assert a.indicators["pazarlik_21b"] is expected


def test_pazarlik_21b_none_when_usul_unreadable():
    r = mk(1)
    r.confidence["ihale_usulu"] = 0.2
    (a,) = full([r])
    assert a.indicators["pazarlik_21b"] is None


# ---------------------------------------------------------------- downloader_bid_ratio
def test_downloader_ratio_is_none_when_the_field_is_missing():
    r = mk(1)
    assert not hasattr(r, "downloaders") or r.downloaders is None
    (a,) = full([r])
    assert a.indicators["downloader_bid_ratio"] is None                    # before the parser stores downloaders


def test_downloader_ratio_when_the_field_exists():
    r = mk(1, toplam=4, gecerli=2)
    object.__setattr__(r, "downloaders", 12) if not hasattr(type(r), "__slots__") else None
    r.downloaders = 12
    (a,) = full([r])
    assert a.indicators["downloader_bid_ratio"] == 3.0                     # 12 downloaders / 4 bids


@pytest.mark.parametrize("dl,conf,toplam,expected", [
    (10, 1.0, 5, 2.0), (0, 1.0, 5, 0.0), (None, 1.0, 5, None), (10, 0.3, 5, None), (-1, 1.0, 5, None),
    (10, 1.0, None, None)])
def test_downloader_ratio_guards(dl, conf, toplam, expected):
    r = mk(1, toplam=toplam if toplam else 3)
    if toplam is None:
        r.toplam_teklif = None
    r.downloaders = dl
    r.confidence["downloaders"] = conf
    (a,) = full([r])
    assert a.indicators["downloader_bid_ratio"] == expected


def test_downloader_ratio_zero_bids_is_none():
    r = mk(1)
    r.toplam_teklif = 0
    r.downloaders = 3
    (a,) = full([r])
    assert a.indicators["downloader_bid_ratio"] is None


# ---------------------------------------------------------------- idare_stats.usul_signal
def test_usul_signal_shares_peer_and_ratio():
    own = ([mk(i, usul="Pazarlık (MD 21 B)", bedel=300.0) for i in range(3)] + [mk(10 + i, usul="Açık", bedel=100.0)
                                                                                  for i in range(2)]
           + [mk(20, usul="Pazarlık (MD 21 F)", bedel=100.0)])                    # 6 awards: 21/b 3, other 1, açık 2
    peers = peers_of(30, usul="Açık") + peers_of(10, usul="Pazarlık (MD 21 B)", start=2000)   # 40 peers: 25% 21/b
    sig = full(own + peers)[0].idare_stats["usul_signal"]
    assert sig["type"] == "mal" and sig["window"] == "all" and sig["n"] == 6
    assert sig["peer_n"] == 40 and sig["peer_label"] == "Türkiye'deki sağlık idareleri (mal)"
    assert sig["pazarlik_21b"]["awards"] == {"idare": 0.5, "peer": 0.25, "ratio": 2.0}
    assert sig["pazarlik"]["awards"] == {"idare": 0.6667, "peer": 0.25, "ratio": 2.6667}
    # TRY basis: idare 21/b = 900 of 1200, peers 21/b = 1000 of 4000
    assert sig["pazarlik_21b"]["try"]["idare"] == pytest.approx(900 / 1200, abs=1e-4)
    assert sig["pazarlik_21b"]["try"]["peer"] == 0.25


def test_usul_signal_needs_5_awards_for_the_idare_and_30_for_the_peer_group():
    own4 = [mk(i, usul="Pazarlık (MD 21 B)") for i in range(4)]
    sig = full(own4 + peers_of(40))[0].idare_stats["usul_signal"]
    assert sig["n"] == 4 and sig["pazarlik_21b"]["awards"] == {"idare": None, "peer": 0.0, "ratio": None}
    own5 = [mk(i, usul="Pazarlık (MD 21 B)") for i in range(5)]
    sig = full(own5 + peers_of(29))[0].idare_stats["usul_signal"]
    assert sig["peer_n"] is None and sig["pazarlik_21b"]["awards"]["idare"] == 1.0
    assert sig["pazarlik_21b"]["awards"]["peer"] is None and sig["pazarlik_21b"]["awards"]["ratio"] is None
    sig = full(own5 + peers_of(30))[0].idare_stats["usul_signal"]
    assert sig["peer_n"] == 30 and sig["pazarlik_21b"]["awards"]["peer"] == 0.0
    assert sig["pazarlik_21b"]["awards"]["ratio"] is None                      # peer share 0 → no ratio


def test_usul_signal_is_per_bulletin_type():
    own = [mk(i, usul="Pazarlık (MD 21 B)") for i in range(5)] + [mk(50 + i, type_="hizmet") for i in range(5)]
    peers = peers_of(30) + [mk(2000 + i, type_="hizmet", idare=f"MUĞLA İL SAĞLIK MÜDÜRLÜĞÜ H{i}") for i in range(30)]
    out = full(own + peers)
    assert out[0].idare_stats["usul_signal"]["type"] == "mal"
    assert out[0].idare_stats["usul_signal"]["pazarlik_21b"]["awards"]["idare"] == 1.0
    assert out[5].idare_stats["usul_signal"]["type"] == "hizmet"
    assert out[5].idare_stats["usul_signal"]["pazarlik_21b"]["awards"]["idare"] == 0.0


def test_signals_add_no_score_points():
    base = [mk(i, usul="Pazarlık (MD 21 B)") for i in range(8)] + peers_of(40)
    with_signal = full(base)
    assert all(not any(p["code"] in ("pazarlik_21b", "usul_signal", "downloader_bid_ratio")
                       for p in r.score_parts) for r in with_signal)


# ---------------------------------------------------------------- export and privacy
def test_signals_reach_the_export_and_the_address_never_does():
    r = mk(1, usul="Pazarlık (MD 21 B)")
    r.yuklenici_adresi = "GİZLİ MAH. ÖRNEK SK. NO:7 KONYA"
    r.downloaders = 9                    # the store has no column for it yet: persistence comes with the parser builder
    s = Store()
    s.replace_day(D, "mal", [r] + [mk(2 + i) for i in range(5)])
    flag_all(s)
    out = export_all(s)
    day = json.loads((out / "days" / "2026-11-18.json").read_text(encoding="utf-8"))
    t = day["tenders"][0]
    assert t["indicators"]["pazarlik_21b"] is True and "downloader_bid_ratio" in t["indicators"]
    assert "usul_signal" in t["idare_stats"]
    blob = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*.json"))
    assert "GİZLİ MAH" not in blob and "yuklenici_adresi" not in blob and "adres" not in " ".join(
        k for tender in day["tenders"] for k in tender)
