"""M5c: IMCO-style idare scorecard (computation, peers, guards, export)."""
import json
from datetime import date

from rec_helpers import rec

from ihale import scorecard
from ihale.scorecard import compute
from ihale.store import StoredRecord

D = date(2026, 11, 18)


def build(specs):
    """specs: [(idare, type, n_awards, single_share, usul)] -> stored records (one ikn per award)."""
    out, i = [], 0
    for idare, typ, n, single, usul in specs:
        for k in range(n):
            i += 1
            tek = k < round(n * single)
            r = rec(i, day=D, type_=typ, ikn=f"2026/{i}", idare=idare, yuklenici=f"Firma {i} Limited Şirketi",
                    toplam=1 if tek else 3, gecerli=1 if tek else 3)
            r.ihale_usulu = usul
            out.append(StoredRecord(id=i, record=r))
    return out


def peers_(n_idares, typ="mal", usul="Açık", n=10):
    """n_idares idares with a spread of single-bid shares 0..1."""
    return [(f"KURUM {j} BAŞKANLIĞI", typ, n, j / max(1, n_idares - 1), usul) for j in range(n_idares)]


def test_percentile_midrank_and_ties():
    assert scorecard._percentile(0.5, [0.1, 0.5, 0.5, 0.9]) == 50.0
    assert scorecard._percentile(0.0, [0.0, 0.0]) == 50.0
    assert scorecard._percentile(1.0, [0.1, 0.2]) == 100.0


def test_eligibility_needs_ten_awards():
    sc = compute(build(peers_(35) + [("KÜÇÜK İDARE", "mal", 9, 0.0, "Açık")]))
    assert not any("küçük idare" in k for k in sc)           # 9 awards: no scorecard
    sc = compute(build(peers_(35) + [("ONLU İDARE", "mal", 10, 0.0, "Açık")]))
    assert any("onlu" in k for k in sc)


def test_peer_group_needs_30_idares_else_no_percentile():
    few = compute(build(peers_(20)))
    c = next(iter(few.values()))["mal"]["sub"]["competition"]["components"]["tek_gecerli"]
    assert c["percentile"] is None and c["peer"] is None and c["value"] is not None    # value shown, never zero
    many = compute(build(peers_(40)))
    top = max(many.items(), key=lambda kv: kv[1]["mal"]["sub"]["competition"]["components"]["tek_gecerli"]["value"])
    c = top[1]["mal"]["sub"]["competition"]["components"]["tek_gecerli"]
    assert c["peer"]["idares"] == 39 and c["percentile"] > 95 and "mal" in c["peer"]["label"]


def test_two_of_three_rule_and_null_components():
    # all awards unreadable-usul: rule_compliance has no components -> only two sub-indices remain
    specs = peers_(35)
    stored = build(specs)
    for s in stored:
        s.record.ihale_usulu = None
        s.record.confidence["ihale_usulu"] = 0.0
    sc = compute(stored)
    card = next(iter(sc.values()))["mal"]
    assert card["sub"]["rule_compliance"]["index"] is None
    assert all(v is None for v in card["sub"]["rule_compliance"]["components"].values())
    assert card["index"] is not None                               # competition + transparency exist


def test_index_none_with_only_one_subindex():
    stored = build(peers_(35))
    for s in stored:
        s.record.ihale_usulu = None
        s.record.confidence["ihale_usulu"] = 0.0
        s.record.confidence["gecerli_teklif"] = 0.0           # competition gone too
        s.record.confidence["toplam_teklif"] = 0.0
    card = next(iter(compute(stored).values()))["mal"]
    assert card["index"] is None


def test_types_are_separate():
    specs = peers_(35, "mal") + [("KURUM 1 BAŞKANLIĞI", "hizmet", 10, 1.0, "Açık")]
    sc = compute(build(specs))
    mal_only = [v for v in sc.values() if set(v) == {"mal"}]
    both = next(v for k, v in sc.items() if "kurum 1 " in k)
    assert set(both) == {"mal", "hizmet"} and both["hizmet"]["sub"]["competition"]["components"]["tek_gecerli"]["peer"] is None
    assert len(mal_only) == 34


def test_structural_istisna_never_raises_rule_compliance():
    stored = build([("ESAS KURUM", "mal", 10, 0.0, "4734 / 3-e")])
    raw = compute(stored)
    comp = next(iter(raw.values()))["mal"]["sub"]["rule_compliance"]["components"]["istisna"]
    assert comp["value"] == 1.0                                   # istisna, not explained
    for s in stored:
        s.structural = {"id": "istisna-3e"}
    comp = next(iter(compute(stored).values()))["mal"]["sub"]["rule_compliance"]["components"]["istisna"]
    assert comp["value"] == 0.0                                   # structurally explained: excluded from the value


def test_component_minimum_of_five():
    stored = build([("AZ İKN", "mal", 10, 0.0, "Açık")])
    for s in stored[:6]:
        s.record.confidence["gecerli_teklif"] = 0.0
        s.record.confidence["toplam_teklif"] = 0.0
    card = next(iter(compute(stored).values()))["mal"]
    assert card["sub"]["competition"]["components"]["tek_gecerli"] is None     # only 4 awards can tell


def test_low_sample_flag_and_no_yuklenici_in_card():
    sc = compute(build(peers_(35, n=12)))
    card = next(iter(sc.values()))["mal"]
    assert card["low_sample"] is True
    assert "firma" not in json.dumps(sc, ensure_ascii=False).lower()


def test_export_carries_scorecard_per_idare(tmp_path):
    from ihale.dosyalar import build as build_dossiers
    stored = build(peers_(35))
    build_dossiers(stored, tmp_path)
    files = list((tmp_path / "idare").glob("*.json"))
    assert len(files) == 35
    d = json.loads(files[0].read_text(encoding="utf-8"))
    assert set(d["scorecard"]["mal"]) >= {"n", "index", "sub", "low_sample"}
    assert set(d["scorecard"]["mal"]["sub"]) == {"competition", "transparency", "rule_compliance"}
    again = json.dumps(scorecard.compute(stored), sort_keys=True)
    assert again == json.dumps(scorecard.compute(stored), sort_keys=True)       # deterministic
