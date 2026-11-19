import json
from datetime import date

import pytest

from ihale import aliases
from ihale.export import export_all
from ihale.pipeline import flag_all
from ihale.store import Store

from rec_helpers import rec


@pytest.mark.parametrize("name,key,parent", [
    ("DEVLET HAVA MEYDANLARI İŞLETMESİ GENEL MÜDÜRLÜĞÜ ANTALYA HAVALİMANI", "dhmi", "DHMİ"),
    ("devlet hava meydanları işletmesi genel müdürlüğü", "dhmi", "DHMİ"),
    ("DEVLET MALZEME OFİSİ GENEL MÜDÜRLÜĞÜ I NOLU SATIN ALMA ŞUBESİ", "dmo", "DMO"),
    ("TCDD 5. BÖLGE MÜDÜRLÜĞÜ", "tcdd", "TCDD"),
    ("TÜRKİYE CUMHURİYETİ DEVLET DEMİRYOLLARI İŞLETMESİ GENEL MÜDÜRLÜĞÜ", "tcdd", "TCDD"),
    ("DEVLET SU İŞLERİ GENEL MÜDÜRLÜĞÜ 12. BÖLGE", "dsi", "DSİ"),
    ("DSİ 5. BÖLGE MÜDÜRLÜĞÜ", "dsi", "DSİ"),
    ("KARAYOLLARI 5. BÖLGE MÜDÜRLÜĞÜ", "karayollari", "Karayolları"),
    ("TÜRKİYE ELEKTRİK İLETİM A.Ş. GENEL MÜDÜRLÜĞÜ", "teias", "TEİAŞ"),
    ("PTT A.Ş. ANKARA BÖLGE MÜDÜRLÜĞÜ", "ptt", "PTT"),
    ("PTT", "ptt", "PTT"),
    ("ORMAN GENEL MÜDÜRLÜĞÜ KONYA BÖLGE", "ogm", "OGM"),
    ("TÜRKİYE ŞEKER FABRİKALARI A.Ş. ERZURUM ŞEKER FABRİKASI", "turksec", "Türkşeker"),
    ("ELEKTRİK ÜRETİM A.Ş. GENEL MÜDÜRLÜĞÜ", "euas", "EÜAŞ"),
])
def test_alias_match(name, key, parent):
    assert aliases.parent_of(name) == {"key": key, "name": parent}


@pytest.mark.parametrize("name", [
    "ANTALYA BÜYÜKŞEHİR BELEDİYESİ", "PTTX LTD", "DSİMLİ KURUM", "T.C. KARAYOLLARI", "İZMİR DEVLET MALZEME OFİSİ",
    "ORMAN BÖLGE MÜDÜRLÜĞÜ", "", None])
def test_no_alias(name):
    assert aliases.parent_of(name) is None


def test_every_entry_has_a_reason_and_unique_keys_per_name():
    assert all(a.reason and a.key and a.name for a in aliases.ALIASES)
    assert {a.key for a in aliases.ALIASES} == {"dhmi", "dmo", "tcdd", "dsi", "karayollari", "teias", "ptt", "ogm",
                                                "turksec", "euas"}


def test_export_has_parent_on_every_record_and_table_in_meta():
    D = date(2026, 11, 18)
    r1 = rec(1, ikn="2026/1", idare="DEVLET HAVA MEYDANLARI İŞLETMESİ GENEL MÜDÜRLÜĞÜ SAMSUN", yuklenici="A Ltd. Şti.")
    r2 = rec(2, ikn="2026/2", idare="KONYA BELEDİYESİ", yuklenici="B Ltd. Şti.")
    s = Store()
    s.replace_day(D, "mal", [r1, r2])
    flag_all(s)
    out = export_all(s)
    day = json.loads((out / "days" / "2026-11-18.json").read_text(encoding="utf-8"))
    assert day["tenders"][0]["idare"]["parent"] == {"key": "dhmi", "name": "DHMİ"}
    assert day["tenders"][1]["idare"]["parent"] is None
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert {"prefix", "key", "name", "reason"} == set(meta["parent_aliases"][0])


def test_aliases_do_not_change_scoring_or_peers():
    from ihale.flags import compute_flags_full
    from ihale.store import StoredRecord
    recs = [rec(i, ikn=f"2026/{i}", idare=f"DSİ {i}. BÖLGE", yuklenici=f"F{i}", toplam=1, gecerli=1) for i in range(1, 8)]
    res, _ = compute_flags_full([StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)])
    assert res[1].idare_stats["records"] == 1          # still separate idares: no clustering in the peer logic
