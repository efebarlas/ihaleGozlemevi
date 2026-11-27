"""M5-audit guard tests: invariants of the shown flag numbers.

1. Property-style cross-check: seeded random tenders (multi-notice İKNs, own-lot esas, kalem shape, zero/missing/
   doubtful/other-currency money, odd bid counts, a year of dates) are flagged by the real pipeline, then
   scripts/audit_flags.py re-derives every shown number independently. Any disagreement fails.
2. Named invariants, each on a minimal case.
Known open bugs (reported to the spec owner, fix not yet approved) are strict xfails: they fail CI once fixed, so the
marker gets removed together with the fix.
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from ihale import config, pipeline
from ihale.flags import compute_flags
from ihale.model import Money
from ihale.store import Store, StoredRecord
from rec_helpers import money, rec

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_flags  # noqa: E402

MISMATCH_KEYS = ("tek_teklif", "diger_teklifler_elendi", "diger_teklifler_elendi_number", "bedel_orani_value",
                 "bedel_orani_flag", "bedel_orani_text", "bedel_orani_text_scope", "tekrarlayan_flag",
                 "tekrarlayan_number", "repeat_suffix_ikn", "ratio_from_zero_or_missing", "currency_scored",
                 "gecerli_gt_toplam")
IDARES = ["ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ", "KONYA BÜYÜKŞEHİR BELEDİYESİ", "DEVLET MALZEME OFİSİ"]
FIRMS = [f"Firma {c} Limited Şirketi" for c in "ABCDE"]


def random_records(seed: int) -> dict:
    rnd = random.Random(seed)
    start = date(2025, 11, 1)
    days = sorted({start + timedelta(days=rnd.randrange(0, 400)) for _ in range(8)})
    out: dict = {}
    for n in range(rnd.randint(25, 45)):                     # tenders
        ikn = f"2026/{1000 + n}"
        d = rnd.choice(days)
        t = rnd.choice(["mal", "hizmet"])
        idare = rnd.choice(IDARES)
        ym = rnd.choice([1000.0, 5000.0, 20_000.0, 0.0, None])
        shape = rnd.choice(["single", "lots_own_esas", "kalem", "ikn_sum"])
        notices = 1 if shape == "single" else rnd.randint(2, 5)
        toplam = rnd.choice([5, 9, 12]) if shape == "kalem" else rnd.choice([1, 1, 2, 3, 5, 9, None])
        for k in range(notices):
            esas = None
            if shape == "lots_own_esas" and ym:
                esas = ym / notices
            elif shape == "kalem":
                esas = ym
            est = esas or ym or 1000.0
            bedel = rnd.choice([est * rnd.uniform(0.02, 1.3), est * 0.98, est, None])   # zero bedel: strict xfail below
            if shape == "kalem" and rnd.random() < 0.7:
                bedel = est * rnd.uniform(0.01, 0.05)        # per-supplier share of a whole-tender YM
            r = rec(0, day=d, type_=t, ikn=ikn, idare=idare, yuklenici=rnd.choice(FIRMS),
                    bedel=None if bedel is None else round(bedel, 2), maliyet=ym, esas=esas, toplam=toplam,
                    gecerli=None if toplam is None else rnd.randint(1, toplam))
            if esas is not None:
                r.confidence["esas_kisim_yaklasik_maliyet"] = 1.0
            if rnd.random() < 0.08:
                r.sozlesme_bedeli = Money(r.sozlesme_bedeli.kurus, "EUR") if r.sozlesme_bedeli else None
            if rnd.random() < 0.08:
                r.confidence[rnd.choice(["yaklasik_maliyet", "sozlesme_bedeli", "toplam_teklif", "yuklenici"])] = 0.4
            out.setdefault((d, t), []).append(r)
    for recs in out.values():
        for i, r in enumerate(recs, 1):
            r.seq = i
    return out


@pytest.mark.parametrize("seed", range(12))
def test_independent_checker_agrees_with_pipeline_on_random_tenders(seed):
    for (d, t), recs in random_records(seed).items():
        Store().replace_day(d, t, recs)
    pipeline.flag_all()
    res = audit_flags.audit(audit_flags.load(config.db_path()))
    bad = {k: v[:3] for k, v in res["findings"].items() if k in MISMATCH_KEYS}
    assert not bad, bad


def run(*recs):
    out = compute_flags([StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)])
    return [out[i + 1] for i in range(len(recs))]


def codes(a):
    return {f["code"] for f in a.flags}


def test_ratio_uses_the_matched_estimate_and_bedel():
    (a,) = run(rec(1, bedel=98.0, maliyet=100.0))
    assert a.indicators["bedel_orani"] == 0.98
    own = [rec(i, ikn="2026/5", bedel=b, maliyet=1000.0, esas=e, yuklenici=f"F{i}") for i, (b, e) in
           enumerate([(99.0, 100.0), (50.0, 400.0)], 1)]
    for r in own:
        r.confidence["esas_kisim_yaklasik_maliyet"] = 1.0
    x, y = run(*own)
    assert x.indicators["bedel_orani"] == 0.99 and y.indicators["bedel_orani"] == 0.125


@pytest.mark.parametrize("kw", [dict(maliyet=0.0), dict(maliyet=None), dict(bedel=None),
                                dict(conf={"yaklasik_maliyet": 0.4}), dict(conf={"sozlesme_bedeli": 0.4})])
def test_no_ratio_from_zero_missing_or_doubtful_values(kw):
    (a,) = run(rec(1, **{"bedel": 99.0, "maliyet": 100.0, **kw}))
    assert a.indicators["bedel_orani"] is None and "bedel_orani" not in codes(a)


def test_no_ratio_across_currencies():
    r = rec(1, bedel=99.0, maliyet=100.0)
    r.sozlesme_bedeli = money(99.0, "EUR")
    (a,) = run(r)
    assert a.indicators["bedel_orani"] is None and "bedel_orani" not in a.score_parts


def test_repeat_win_counts_ikns_not_notices():
    d = date(2026, 11, 18)
    # one supplier, one idare: 3 kalem/lot notices of ONE İKN + 1 other İKN = 2 wins, below the cut of 3
    same = [rec(i, day=d, ikn="2026/50", bedel=10.0 * i) for i in (1, 2, 3)] + [rec(4, day=d, ikn="2026/51")]
    assert all("tekrarlayan_yuklenici" not in codes(a) for a in run(*same))
    three = same + [rec(5, day=d, ikn="2026/52")]
    shown = [f for a in run(*three) for f in a.flags if f["code"] == "tekrarlayan_yuklenici"]
    assert shown and {f["value"] for f in shown} == {3}


def test_single_bid_flags_follow_printed_counts_only():
    t, e, none, odd = run(rec(1, ikn="2026/61", toplam=1, gecerli=1), rec(2, ikn="2026/62", toplam=4, gecerli=1),
                          rec(3, ikn="2026/63", toplam=4, gecerli=2), rec(4, ikn="2026/64", toplam=None, gecerli=1))
    assert codes(t) >= {"tek_teklif"} and "diger_teklifler_elendi" not in codes(t)
    assert "diger_teklifler_elendi" in codes(e) and next(f for f in e.flags if f["code"] == "diger_teklifler_elendi")["value"] == 4
    assert not codes(none) & {"tek_teklif", "diger_teklifler_elendi"}
    assert not codes(odd) & {"tek_teklif", "diger_teklifler_elendi"}       # unread count -> nothing claimed


def test_shown_percent_is_the_floored_ratio():
    (a,) = run(rec(1, bedel=99.99, maliyet=100.0))
    assert a.flags[0]["text"].endswith("%99'u")
    (b,) = run(rec(1, bedel=100.06, maliyet=100.0))
    assert "(%100,06)" in b.flags[0]["text"]


# ---------------------------------------------------------------- known open bugs (strict xfail)
@pytest.mark.xfail(strict=True, reason="M5-audit finding: notices of one İKN printing different YMs (no esas) are "
                                       "summed against one notice's YM; fix (rule B) awaits the spec owner")
def test_differing_yms_in_one_ikn_compare_own_bedel_with_own_ym():
    lots = [rec(i, ikn="2026/70", bedel=b, maliyet=m, yuklenici=f"F{i}") for i, (b, m) in
            enumerate([(17_500.0, 20_764.5), (17_500.0, 17_816.1), (16_300.0, 17_816.1)], 1)]
    res = run(*lots)
    assert [round(a.indicators["bedel_orani"], 3) for a in res] == [0.843, 0.982, 0.915]
    assert ["bedel_orani" in codes(a) for a in res] == [False, True, False]


@pytest.mark.xfail(strict=True, reason="M5-audit finding: a zero sözleşme bedeli still yields a ratio (%0, and a 0 "
                                       "share inside an İKN sum); 0 live cases; rule change awaits the spec owner")
def test_zero_bedel_gives_no_ratio():
    (a,) = run(rec(1, bedel=0.0, maliyet=100.0))
    assert a.indicators["bedel_orani"] is None
