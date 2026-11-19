import json
import random
from datetime import date

from ihale import config
from ihale.oracle import QUESTION, build_candidates, select_pairs, write_candidates
from ihale.store import Store

from rec_helpers import rec

TEK, DIGER, BEDEL, REP, IDARE = ("tek_teklif", "diger_teklifler_elendi", "bedel_orani", "tekrarlayan_eslesik",
                                 "idare_orani")
POINTS = {TEK: 2.0, DIGER: 3.0, BEDEL: 2.0, REP: 2.5, IDARE: 2.2}


def T(i, parts, bedel=100.0, ikn=None, cur="TRY", score=None):
    """Day-export tender dict with the rarity-weighted shape (score float, score_parts as objects)."""
    sp = [{"code": p, "points": POINTS[p], "p": 0.1, "p_group": "acik"} for p in parts]
    return {"id": f"2026-11-18-mal-A-{i}", "ikn": ikn or f"2026/{i}",
            "score": sum(POINTS[p] for p in parts) if score is None else score,
            "score_parts": sp, "sozlesme_bedeli": {"amount": bedel, "currency": cur}}


def pair_ids(pairs):
    return [(a["id"], b["id"]) for a, b in pairs]


def test_single_swap_preferred_over_equal_score_and_bigger_bedel():
    swap_a, swap_b = T(1, [TEK], 10), T(2, [BEDEL], 10)                 # one swap, 2.0 vs 2.0
    multi_a, multi_b = T(3, [DIGER], 1000), T(4, [TEK, BEDEL], 1000)    # 3.0 vs 4.0, two parts differ
    pairs = select_pairs([multi_a, multi_b, swap_a, swap_b])
    assert pair_ids(pairs) == [(swap_a["id"], swap_b["id"]), (multi_a["id"], multi_b["id"])]


def test_closer_scores_preferred_when_no_swap():
    x = T(1, [TEK, IDARE], 100, score=3.0)
    y = T(2, [DIGER], 100, score=3.0)
    z = T(3, [TEK, IDARE, BEDEL], 9000, score=3.8)
    pairs = select_pairs([z, y, x])
    assert pair_ids(pairs) == [(x["id"], y["id"])]            # z stays unused despite its bedel


def test_higher_bedel_breaks_ties():
    lo = (T(1, [TEK], 10), T(2, [BEDEL], 10))
    hi = (T(3, [TEK], 500), T(4, [BEDEL], 500))
    assert select_pairs([*lo, *hi])[0][0]["id"] == hi[0]["id"]


def test_each_record_used_at_most_once_and_max_five():
    ts = [T(i, [TEK] if i % 2 else [BEDEL], bedel=float(i)) for i in range(1, 41)]
    pairs = select_pairs(ts)
    flat = [t["id"] for p in pairs for t in p]
    assert len(pairs) == 5 and len(flat) == len(set(flat)) == 10


def test_pairs_need_different_parts_and_scores_within_one_point():
    assert select_pairs([T(1, [TEK]), T(2, [TEK]), T(3, [TEK])]) == []                         # same parts
    assert select_pairs([T(1, [TEK], score=2.0), T(2, [DIGER], score=3.01)]) == []             # gap 1.01
    assert len(select_pairs([T(1, [TEK], score=2.0), T(2, [DIGER], score=3.0)])) == 1          # gap 1.0


def test_score_band_is_2_to_4_5():
    inside = [T(10, [TEK], score=2.0), T(11, [BEDEL], score=2.0), T(12, [DIGER], score=4.5)]
    outside = [T(1, [TEK], score=1.99), T(2, [DIGER], score=4.51), T(3, [], score=0.0), T(4, [IDARE], score=6.0)]
    used = {t["id"] for p in select_pairs(outside + inside) for t in p}
    assert used and used <= {t["id"] for t in inside}
    assert select_pairs(outside) == []


def test_one_record_per_ikn():
    lots = [T(1, [TEK], 10, ikn="2026/7"), T(2, [BEDEL], 20, ikn="2026/7")]           # same tender
    assert select_pairs(lots) == []
    rep = select_pairs(lots + [T(3, [DIGER], 5, ikn="2026/8")])
    assert len(rep) == 1 and "2026-11-18-mal-A-2" in (rep[0][0]["id"], rep[0][1]["id"])     # higher-bedel lot kept


def test_non_try_bedel_counts_as_zero_for_ranking():
    pairs = select_pairs([T(1, [TEK], 1e9, cur="EUR"), T(2, [BEDEL], 1e9, cur="EUR"),
                          T(3, [TEK], 5), T(4, [BEDEL], 5)])
    assert pairs[0][0]["id"].endswith("3")


def test_deterministic_regardless_of_input_order():
    ts = [T(i, [TEK] if i % 3 else [BEDEL] if i % 2 else [DIGER], bedel=float(i % 7)) for i in range(1, 60)]
    base = select_pairs(ts)
    assert select_pairs(list(reversed(ts))) == base
    shuffled = ts[:]
    random.Random(1).shuffle(shuffled)
    assert select_pairs(shuffled) == base and select_pairs(ts) == base


def test_pair_member_order_is_by_id():
    ((a, b),) = select_pairs([T(9, [TEK]), T(2, [BEDEL])])
    assert a["id"] < b["id"]


def test_build_candidates_shape_and_texts():
    out = build_candidates([T(1, [TEK]), T(2, [BEDEL])], "2026-11-18")
    assert set(out) == {"schema", "date", "generated_at", "pairs", "note"}     # 1 < 3 pairs → note
    p = out["pairs"][0]
    assert set(p) == {"pair_id", "why", "would_change", "question", "a", "b"}
    assert p["pair_id"] == "2026-11-18-1" and p["question"] == QUESTION
    assert p["why"] == "aynı skor (2,00), farklı işaret karışımı: tek_teklif / bedel_orani"
    assert p["would_change"] == "tek_teklif ağırlığı ile bedel_orani ağırlığı arasındaki sıra"
    multi = build_candidates([T(1, [DIGER]), T(2, [TEK, BEDEL])], "2026-11-18")["pairs"][0]
    assert multi["why"] == "skorlar 3,00 ve 4,00, farklı işaret karışımı: diger_teklifler_elendi / tek_teklif + bedel_orani"


def test_fewer_than_three_pairs_has_note_and_zero_case():
    zero = build_candidates([], None)
    assert zero["pairs"] == [] and "0 aday" in zero["note"]
    two = build_candidates([T(1, [TEK]), T(2, [BEDEL]), T(3, [TEK]), T(4, [DIGER])], "2026-11-18")
    assert len(two["pairs"]) == 2 and "note" in two and "2 aday" in two["note"]
    many = build_candidates([T(i, [TEK] if i % 2 else [BEDEL]) for i in range(1, 12)], "2026-11-18")
    assert len(many["pairs"]) == 5 and "note" not in many


def test_write_candidates_end_to_end_local_file_only():
    D = date(2026, 11, 18)
    recs = []
    for i in range(1, 121):      # 120 open-tender records: 8 single-bid, 8 near-estimate, the rest plain
        if i <= 8:
            r = rec(i, ikn=f"2026/{i}", yuklenici=f"F{i}", idare=f"IDARE {i}", toplam=1, gecerli=1)
        elif i <= 16:
            r = rec(i, ikn=f"2026/{i}", yuklenici=f"F{i}", idare=f"IDARE {i}", bedel=99.0, maliyet=100.0)
        else:
            r = rec(i, ikn=f"2026/{i}", yuklenici=f"F{i}", idare=f"IDARE {i}")
        recs.append(r)
    s = Store()
    s.replace_day(D, "mal", recs)
    from ihale.pipeline import flag_all
    flag_all(s)
    path = write_candidates(s)
    assert path == config.data_dir() / "oracle" / "candidates.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["date"] == "2026-11-18" and len(data["pairs"]) == 5 and "note" not in data
    a = data["pairs"][0]["a"]
    assert {"score", "score_parts", "indicators", "source", "idare", "flags"} <= set(a)
    assert 2.0 <= a["score"] <= 4.5 and isinstance(a["score_parts"][0], dict)
    assert not (config.data_dir() / "oracle" / "log.jsonl").exists()
    assert write_candidates(s).read_text(encoding="utf-8").split('"generated_at"')[0] == \
        path.read_text(encoding="utf-8").split('"generated_at"')[0]


def test_empty_store_writes_note():
    path = write_candidates(Store())
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["date"] is None and data["pairs"] == [] and data["note"]
