"""İdare classifier seam: keywords, table, hybrid, peer config, shadow log, eval script (all offline, synthetic files)."""
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

from ihale import classify, peers
from ihale.classify import TURU, Classification
from ihale.keys import normalize_key
from ihale.pipeline import flag_all
from ihale.store import Store

from rec_helpers import rec

D = date(2026, 11, 18)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No real table, legacy peer classifier (these tests predate the table_first promotion);
    tests that need a table or another classifier set their own."""
    monkeypatch.setenv(classify.TABLE_ENV, str(tmp_path / "no-such-table.jsonl"))
    monkeypatch.setenv(classify.PEER_ENV, "legacy")
    classify._cached.cache_clear()


def write_table(tmp_path, monkeypatch, rows):
    p = tmp_path / "table.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setenv(classify.TABLE_ENV, str(p))
    return p


def row(name, turu, il=None, conf=0.95, **extra):
    return {"key": normalize_key(name), "name": name, "turu": turu, "il": il, "confidence": conf, **extra}


# ---------------------------------------------------------------- taxonomy
def test_taxonomy_is_a_closed_list_of_about_twenty():
    assert 18 <= len(TURU) <= 20 and "diger" in TURU
    assert set(classify.TURU_PLURAL) == set(TURU)
    doc = (ROOT / "docs" / "idare-taxonomy.md").read_text(encoding="utf-8")
    for code in TURU:                                   # the doc and the code agree
        assert f"`{code}`" in doc, code


# ---------------------------------------------------------------- keywords
@pytest.mark.parametrize("name,turu,il", [
    ("DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ I NOLU SATIN ALMA ŞUBESİ", "dmo", None),
    ("TCDD 5. BÖLGE MÜDÜRLÜĞÜ", "tcdd", None),
    ("DSİ 12. BÖLGE MÜDÜRLÜĞÜ", "dsi", None),
    ("DEVLET SU İŞLERİ GENEL MÜDÜRLÜĞÜ", "dsi", None),
    ("KARAYOLLARI 14. BÖLGE MÜDÜRLÜĞÜ ERZURUM", "karayollari", "Erzurum"),
    ("ELEKTRİK ÜRETİM A.Ş. GENEL MÜDÜRLÜĞÜ", "enerji_kit", None),
    ("TÜRKİYE ELEKTRİK İLETİM A.Ş. 5. İLETİM TESİS VE İŞLETME GRUP MÜDÜRLÜĞÜ", "enerji_kit", None),
    ("PTT A.Ş. ANKARA BÖLGE MÜDÜRLÜĞÜ", "diger_kit", "Ankara"),
    ("DEVLET HAVA MEYDANLARI İŞLETMESİ GENEL MÜDÜRLÜĞÜ ANTALYA HAVALİMANI", "diger_kit", "Antalya"),
    ("HACETTEPE ÜNİVERSİTESİ HASTANELERİ", "universite", None),
    ("İZMİR BÜYÜKŞEHİR BELEDİYESİ FEN İŞLERİ DAİRE BAŞKANLIĞI", "buyuksehir_belediyesi", "İzmir"),
    ("MANAVGAT BELEDİYE BAŞKANLIĞI", "belediye", None),
    ("ANTALYA BÜYÜKŞEHİR BELEDİYESİ ULAŞIM A.Ş.", "belediye_sirketi", "Antalya"),
    ("ASKİ SU VE KANALİZASYON İDARESİ GENEL MÜDÜRLÜĞÜ", "belediye_sirketi", None),
    ("KONYA İL ÖZEL İDARESİ", "il_ozel_idaresi", "Konya"),
    ("MERSİN VALİLİĞİ İL ÖZEL İDARESİ", "il_ozel_idaresi", "Mersin"),
    ("ŞANLIURFA VALİLİĞİ", "valilik_kaymakamlik", "Şanlıurfa"),
    ("ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ MANAVGAT DEVLET HASTANESİ", "saglik", "Antalya"),
    ("KONYA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜ", "meb_okul", "Konya"),
    ("ATATÜRK ANADOLU LİSESİ MÜDÜRLÜĞÜ", "meb_okul", None),
    ("ÇORUM ELMADAĞ KAPALI CEZA İNFAZ KURUMU", "adalet", "Çorum"),
    ("İSTANBUL ANADOLU ADLİYESİ", "adalet", "İstanbul"),
    ("JANDARMA GENEL KOMUTANLIĞI", "tsk_guvenlik", None),
    ("İSTANBUL EMNİYET MÜDÜRLÜĞÜ", "tsk_guvenlik", "İstanbul"),
    ("VAN İL TARIM VE ORMAN MÜDÜRLÜĞÜ", "bakanlik_tasra", "Van"),
    ("ÇEVRE, ŞEHİRCİLİK VE İKLİM DEĞİŞİKLİĞİ BAKANLIĞI", "merkezi_idare", None),
    ("TÜRKİYE İSTATİSTİK KURUMU", "merkezi_idare", None),
    ("BİLİNMEYEN BİR KURUM", "diger", None),
])
def test_keywords_classification(name, turu, il):
    c = classify.classify_keywords(name)
    assert (c.turu, c.il, c.source) == (turu, il, "keywords")
    assert 0 < c.confidence <= 1


def test_tie_break_rules():
    k = lambda n: classify.classify_keywords(n).turu                       # noqa: E731
    assert k("ANKARA ÜNİVERSİTESİ HASTANESİ") == "universite"              # university before hospital
    assert k("KONYA BÜYÜKŞEHİR BELEDİYESİ A.Ş.") == "belediye_sirketi"     # company before municipality
    assert k("KONYA BELEDİYESİ") == "belediye" and k("KONYA BÜYÜKŞEHİR BELEDİYESİ") == "buyuksehir_belediyesi"
    assert k("ADALET BAKANLIĞI İL SAĞLIK MÜDÜRLÜĞÜ") == "saglik"           # health before adalet
    assert k("DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ") == "dmo"              # named body beats Genel Müdürlüğü
    assert k("KARAYOLLARI GENEL MÜDÜRLÜĞÜ 5. BÖLGE") == "karayollari"
    assert k("TARIM İL MÜDÜRLÜĞÜ") == "bakanlik_tasra" and k("TARIM BAKANLIĞI") == "merkezi_idare"


def test_keywords_province_rules():
    assert classify.classify_keywords("ANKARA İZMİR ORTAK İDARESİ").il is None          # two provinces
    assert classify.classify_keywords("ŞANLIURFA BELEDİYESİ").il == "Şanlıurfa"
    assert classify.classify_keywords("İZMİR BELEDİYESİ").il == "İzmir"
    assert classify.classify_keywords("AYDINLATMA GENEL MÜDÜRLÜĞÜ").il is None
    assert classify.classify_keywords("").turu == "diger" and classify.classify_keywords(None).turu == "diger"


# ---------------------------------------------------------------- table and hybrid
def test_table_lookup_and_miss(tmp_path, monkeypatch):
    write_table(tmp_path, monkeypatch, [row("ANTALYA BÜYÜKŞEHİR BELEDİYESİ", "buyuksehir_belediyesi", "Antalya", 0.97)])
    hit = classify.classify("Antalya  Büyükşehir  Belediyesi!", "table")          # keyed by the normalized key
    assert hit == Classification("buyuksehir_belediyesi", "Antalya", 0.97, "table")
    miss = classify.classify("BAŞKA BİR KURUM", "table")
    assert miss.turu is None and miss.confidence == 0.0 and miss.source == "table:miss"


def test_missing_table_file_is_an_empty_table():
    assert classify.classify("ANTALYA BELEDİYESİ", "table").source == "table:miss"
    assert classify.classify("ANTALYA BELEDİYESİ", "hybrid").source == "hybrid:keywords"


def test_table_row_with_unknown_turu_is_ignored(tmp_path, monkeypatch):
    write_table(tmp_path, monkeypatch, [row("X KURUMU", "uydurma_tur")])
    assert classify.classify("X KURUMU", "table").turu is None


def test_hybrid_trusts_the_table_only_at_0_9(tmp_path, monkeypatch):
    write_table(tmp_path, monkeypatch, [
        row("A BELEDİYESİ", "diger", conf=0.9),                  # boundary: trusted, even against the keywords
        row("B BELEDİYESİ", "diger", conf=0.89),                 # below: keywords win
    ])
    a, b = classify.classify("A BELEDİYESİ", "hybrid"), classify.classify("B BELEDİYESİ", "hybrid")
    assert (a.turu, a.source) == ("diger", "hybrid:table")
    assert (b.turu, b.source) == ("belediye", "hybrid:keywords")
    assert classify.classify("C BELEDİYESİ", "hybrid").source == "hybrid:keywords"       # miss → keywords


def test_table_reload_when_the_file_changes(tmp_path, monkeypatch):
    p = write_table(tmp_path, monkeypatch, [row("X KURUMU", "adalet")])
    assert classify.classify("X KURUMU", "table").turu == "adalet"
    p.write_text(json.dumps(row("X KURUMU", "saglik"), ensure_ascii=False) + "\n", encoding="utf-8")
    import os
    os.utime(p, ns=(1, 2_000_000_000_000_000_000))                    # force a different mtime
    assert classify.classify("X KURUMU", "table").turu == "saglik"


def test_unknown_implementation_rejected():
    with pytest.raises(ValueError):
        classify.classify("X", "agent")


# ---------------------------------------------------------------- peer config
def test_production_default_is_table_first(monkeypatch):
    monkeypatch.delenv(classify.PEER_ENV, raising=False)
    assert classify.peer_classifier() == "table_first"


def test_default_peer_classifier_is_todays_rules():
    assert classify.peer_classifier() == "legacy"          # conftest pins legacy for these tests
    assert peers.idare_turu("ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ") == "sağlık"          # legacy codes, unchanged
    assert peers.idare_turu("KONYA BELEDİYESİ") == "belediye"
    assert peers.idare_turu("TCDD 5. BÖLGE") == "diğer"


def test_peer_classifier_switch(monkeypatch, tmp_path):
    monkeypatch.setenv(classify.PEER_ENV, "keywords")
    assert peers.idare_turu("TCDD 5. BÖLGE") == "tcdd" and peers.il_of("KONYA BELEDİYESİ") == "Konya"
    write_table(tmp_path, monkeypatch, [row("Y KURUMU", "adalet", "Van", 0.99)])
    monkeypatch.setenv(classify.PEER_ENV, "table")
    assert (peers.idare_turu("Y KURUMU"), peers.il_of("Y KURUMU")) == ("adalet", "Van")
    assert peers.idare_turu("UNKNOWN") == "diger"                                 # table miss
    monkeypatch.setenv(classify.PEER_ENV, "hybrid")
    assert peers.idare_turu("Y KURUMU") == "adalet" and peers.idare_turu("KONYA BELEDİYESİ") == "belediye"
    monkeypatch.setenv(classify.PEER_ENV, "bogus")
    with pytest.raises(ValueError):
        classify.peer_classifier()


def test_peer_labels_cover_the_new_taxonomy():
    for code in TURU:
        assert peers.peer_label("turu_il", code, "Konya", "mal")                  # no KeyError for any code


def test_peers_scoring_unchanged_by_default():
    from ihale.flags import compute_flags_full
    from ihale.store import StoredRecord
    recs = [rec(i, ikn=f"2026/{i}", idare=f"ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ {i}", yuklenici=f"F{i}", toplam=1, gecerli=1)
            for i in range(1, 30)]
    res, _ = compute_flags_full([StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)])
    assert res[1].idare_stats["idare_turu"] == "sağlık"


# ---------------------------------------------------------------- shadow mode
def test_shadow_log_records_disagreements_and_summary(tmp_path, monkeypatch, data_dir):
    write_table(tmp_path, monkeypatch, [
        row("ANTALYA BELEDİYESİ", "belediye", "Antalya"),                    # agrees with keywords
        row("KONYA BELEDİYESİ", "belediye_sirketi", "Konya"),                # turu differs
        row("MUĞLA BELEDİYESİ", "belediye", "Aydın"),                        # il differs
    ])
    p = classify.shadow_log(["ANTALYA BELEDİYESİ", "KONYA BELEDİYESİ", "MUĞLA BELEDİYESİ", "NOT IN TABLE", None], D)
    assert p == data_dir / "logs" / "classify-shadow-2026-11-18.jsonl"
    lines = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    *dis, summary = lines
    assert [d["idare"] for d in dis] == ["KONYA BELEDİYESİ", "MUĞLA BELEDİYESİ"]
    assert dis[0]["turu_differs"] and not dis[0]["il_differs"] and dis[1]["il_differs"] and not dis[1]["turu_differs"]
    assert summary["summary"] == {"date": "2026-11-18", "names": 4, "in_table": 3, "disagreements": 2,
                                  "misses": 1, "miss_rate": 0.25, "peer_classifier": "legacy"}
    assert classify.new_names_path().read_text(encoding="utf-8").splitlines() == ["NOT IN TABLE"]


def test_flag_run_writes_the_shadow_log(tmp_path, monkeypatch, data_dir):
    write_table(tmp_path, monkeypatch, [row("KONYA BELEDİYESİ", "belediye_sirketi", "Konya")])
    s = Store()
    s.replace_day(D, "mal", [rec(1, ikn="2026/1", idare="KONYA BELEDİYESİ", yuklenici="A")])
    flag_all(s)
    logs = list((data_dir / "logs").glob("classify-shadow-*.jsonl"))
    assert len(logs) == 1
    assert any('"KONYA BELEDİYESİ"' in x for x in logs[0].read_text(encoding="utf-8").splitlines())


def test_flag_run_survives_a_broken_table(tmp_path, monkeypatch, data_dir):
    p = tmp_path / "bad.jsonl"
    p.write_text("{not json\n", encoding="utf-8")
    monkeypatch.setenv(classify.TABLE_ENV, str(p))
    s = Store()
    s.replace_day(D, "mal", [rec(1, ikn="2026/1")])
    flag_all(s)                                                            # logs the failure, does not raise


# ---------------------------------------------------------------- eval script
def load_eval():
    spec = importlib.util.spec_from_file_location("eval_classify", ROOT / "scripts" / "eval_classify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LABELS = [
    {"idare": "KONYA BELEDİYESİ", "turu": "belediye", "il": "Konya"},
    {"idare": "TCDD 5. BÖLGE MÜDÜRLÜĞÜ", "turu": "tcdd", "il": None},
    {"idare": "ÖRNEK GAYRİ KURUM", "turu": "adalet", "il": "Van"},              # keywords will say diger / null
    {"idare": "ANTALYA ÜNİVERSİTESİ HASTANESİ", "turu": "universite", "il": "Antalya"},
]


def test_evaluate_numbers_and_coverage(tmp_path, monkeypatch):
    write_table(tmp_path, monkeypatch, [
        row("ÖRNEK GAYRİ KURUM", "adalet", "Van", 0.95, turu_run1="adalet", turu_run2="adalet"),
        row("KONYA BELEDİYESİ", "belediye_sirketi", "Konya", 0.5, turu_run1="belediye", turu_run2="belediye_sirketi"),
    ])
    ev = load_eval()
    kw = ev.evaluate(LABELS, "keywords")
    assert (kw["n"], kw["covered"], kw["turu_correct"], kw["il_correct"]) == (4, 4, 3, 3)
    tb = ev.evaluate(LABELS, "table")
    assert (tb["covered"], tb["turu_correct"], tb["il_correct"]) == (2, 1, 2)         # table covers 2 of 4
    hy = ev.evaluate(LABELS, "hybrid")
    assert (hy["covered"], hy["turu_correct"], hy["il_correct"]) == (4, 4, 4)         # table @0.95 + keywords elsewhere
    assert kw["confusion"][("adalet", "diger")] == 1
    assert [w["idare"] for w in kw["wrong"]] == ["ÖRNEK GAYRİ KURUM"]


def test_self_consistency():
    ev = load_eval()
    rows = [{"turu_run1": "a", "turu_run2": "a", "il_run1": "Van", "il_run2": "Van"},
            {"turu_run1": "a", "turu_run2": "b", "il_run1": None, "il_run2": "Van"},
            {"turu_run1": "x"}]
    assert ev.self_consistency(rows) == {"rows": 2, "turu_agree": 1, "il_rows": 2, "il_agree": 1}
    assert ev.self_consistency([{"turu": "a"}]) is None


def test_eval_main_prints_report(tmp_path, monkeypatch, capsys):
    labels = tmp_path / "labels.jsonl"
    labels.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in LABELS), encoding="utf-8")
    table = write_table(tmp_path, monkeypatch, [row("ÖRNEK GAYRİ KURUM", "adalet", "Van", 0.95,
                                                    turu_run1="adalet", turu_run2="adalet")])
    ev = load_eval()
    assert ev.main(["--labels", str(labels), "--table", str(table)]) == 0
    out = capsys.readouterr().out
    assert "4 labeled idares" in out and "keywords" in out and "hybrid" in out
    assert "Confusion (turu), keywords" in out and "adalet" in out and "turu: 1/1 agree" in out
    assert ev.main(["--labels", str(tmp_path / "missing.jsonl")]) == 2


def test_eval_without_two_runs_says_so(tmp_path, monkeypatch, capsys):
    labels = tmp_path / "labels.jsonl"
    labels.write_text(json.dumps(LABELS[0], ensure_ascii=False) + "\n", encoding="utf-8")
    ev = load_eval()
    assert ev.main(["--labels", str(labels)]) == 0                         # no table file at all
    assert "no turu_run1/turu_run2" in capsys.readouterr().out


# ---------------------------------------------------------------- table_first, new-names log
def test_table_first_uses_any_confidence_table_row(tmp_path, monkeypatch):
    write_table(tmp_path, monkeypatch, [row("A BELEDİYESİ", "diger", "Van", 0.2)])
    a = classify.classify("A BELEDİYESİ", "table_first")
    assert (a.turu, a.il, a.confidence, a.source) == ("diger", "Van", 0.2, "table_first:table")   # unlike hybrid
    assert classify.classify("A BELEDİYESİ", "hybrid").source == "hybrid:keywords"
    miss = classify.classify("KONYA BELEDİYESİ", "table_first")
    assert (miss.turu, miss.source) == ("belediye", "table_first:keywords")
    assert "table_first" in classify.PEER_CLASSIFIERS and "table_first" in classify.IMPLEMENTATIONS


def test_table_first_as_peer_classifier(tmp_path, monkeypatch):
    write_table(tmp_path, monkeypatch, [row("Y KURUMU", "adalet", "Van", 0.3)])
    monkeypatch.setenv(classify.PEER_ENV, "table_first")
    assert (peers.idare_turu("Y KURUMU"), peers.il_of("Y KURUMU")) == ("adalet", "Van")
    assert peers.idare_turu("KONYA BELEDİYESİ") == "belediye"


def test_new_names_accumulate_unique_across_runs(tmp_path, monkeypatch, data_dir):
    write_table(tmp_path, monkeypatch, [row("IN TABLE", "adalet")])
    classify.shadow_log(["IN TABLE", "Z NEW", "A NEW"], D)
    classify.shadow_log(["Z NEW", "B NEW", "IN TABLE"], date(2026, 11, 19))
    lines = classify.new_names_path().read_text(encoding="utf-8").splitlines()
    assert lines == ["A NEW", "Z NEW", "B NEW"] and len(lines) == len(set(lines))


def test_miss_rate_without_a_table(data_dir):
    p = classify.shadow_log(["A", "B"], D)
    summary = json.loads(p.read_text(encoding="utf-8").splitlines()[-1])["summary"]
    assert summary["misses"] == 2 and summary["miss_rate"] == 1.0 and summary["in_table"] == 0


def test_eval_scores_table_first(tmp_path, monkeypatch):
    write_table(tmp_path, monkeypatch, [row("KONYA BELEDİYESİ", "belediye", "Konya", 0.4),
                                        row("ÖRNEK GAYRİ KURUM", "adalet", "Van", 0.95)])
    ev = load_eval()
    tf = ev.evaluate(LABELS, "table_first")
    assert (tf["covered"], tf["turu_correct"], tf["il_correct"]) == (4, 4, 4)
    hy = ev.evaluate(LABELS, "hybrid")
    assert hy["turu_correct"] == 4
    import io
    buf = io.StringIO()
    ev.report(LABELS, [], out=lambda s="": buf.write(s + "\n"))
    assert "table_first" in buf.getvalue()
