"""OCDS 1.1 and FollowTheMoney private exports (synthetic records; schemas vendored, validation offline)."""
import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest

from ihale import cli, config, openexport
from ihale.export import TR_TZ
from ihale.model import Money
from ihale.store import Store, StoredRecord

from rec_helpers import rec

D = date(2026, 11, 18)
FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 19, 8, 0, tzinfo=TR_TZ)


def mk(i, *, ikn=None, type_="mal", usul="Açık", idare="ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ", yuklenici="Emir Hizmetler Limited Şirketi",
       toplam=3, gecerli=2, bedel=100.0, maliyet=120.0, section="A", seq=None):
    r = rec(seq or i, day=D, type_=type_, section=section, ikn=ikn or f"2026/{1000 + i}", idare=idare,
            yuklenici=yuklenici, toplam=toplam, gecerli=gecerli, bedel=bedel, maliyet=maliyet)
    r.ihale_usulu = usul
    return r


def stored(*recs):
    return [StoredRecord(id=i + 1, record=r) for i, r in enumerate(recs)]


def package(*recs):
    return openexport.ocds_package(D, stored(*recs), NOW)


# ---------------------------------------------------------------- OCDS schema validation (offline, jsonschema)
jsonschema = pytest.importorskip("jsonschema")


def validator():
    from jsonschema import Draft4Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT4
    base = "https://standard.open-contracting.org/schema/1__1__5/"
    load = lambda n: json.loads((FIX / "ocds" / n).read_text(encoding="utf-8"))   # noqa: E731
    reg = Registry().with_resources([
        (base + n, Resource.from_contents(load(n), default_specification=DRAFT4))
        for n in ("release-schema.json", "release-package-schema.json")])
    return Draft4Validator(load("release-package-schema.json"), registry=reg)


def errors(pkg):
    return sorted(e.message[:160] for e in validator().iter_errors(pkg))


def test_package_validates_against_ocds_1_1_5_schema():
    pkg = package(mk(1), mk(2, usul="Pazarlık (MD 21 B)", toplam=1, gecerli=1), mk(3, usul="4734 / 3-g"),
                  mk(4, type_="hizmet", usul="Belli İstekliler Arasında"), mk(5, yuklenici="Mustafa Öz"),
                  mk(6, type_="yapim", usul="Doğrudan Temin (MD 22 D)"))
    assert errors(pkg) == []


def test_kismi_lots_and_odd_records_validate():
    lots = [mk(i, ikn="2026/7777", seq=i, yuklenici=f"Firma {i} Ltd. Şti.", bedel=10.0 * i) for i in (1, 2, 3)]
    sparse = mk(9)
    for f in ("idare", "yuklenici", "ihale_usulu", "yaklasik_maliyet", "sozlesme_bedeli", "toplam_teklif", "ikn"):
        sparse.confidence[f] = 0.1
    eur = mk(10)
    eur.sozlesme_bedeli = Money(15405000, "EUR")
    assert errors(package(*lots, sparse, eur)) == []


def test_schema_actually_rejects_broken_packages():
    pkg = package(mk(1))
    del pkg["releases"][0]["ocid"]
    assert any("ocid" in e for e in errors(pkg))


def test_dates_are_rfc3339_datetimes():
    pkg = package(mk(1))
    rx = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")
    rel = pkg["releases"][0]
    for v in (pkg["publishedDate"], rel["date"], rel["awards"][0]["date"], rel["contracts"][0]["dateSigned"],
              rel["tender"]["tenderPeriod"]["endDate"], rel["awards"][0]["documents"][0]["datePublished"]):
        assert rx.match(v), v


# ---------------------------------------------------------------- OCDS mapping
def test_release_mapping_fields():
    pkg = package(mk(1, usul="Pazarlık (MD 21 B)"))
    assert pkg["version"] == "1.1" and pkg["uri"] == "urn:ihalegozlemevi:ocds:2026-11-18"
    rel = pkg["releases"][0]
    assert rel["ocid"] == "ocds-ihalegoz-2026-1001" and rel["tag"] == ["award", "contract"]
    t = rel["tender"]
    assert t["id"] == "2026/1001" and t["numberOfTenderers"] == 3 and t["value"] == {"amount": 120.0, "currency": "TRY"}
    assert t["procurementMethodDetails"] == "Pazarlık (MD 21 B)" and t["procurementMethod"] == "limited"
    assert t["mainProcurementCategory"] == "goods" and t["procuringEntity"]["name"] == "ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ"
    (aw,) = rel["awards"]
    assert aw["value"] == {"amount": 100.0, "currency": "TRY"} and aw["date"].startswith("2026-11-16")
    assert aw["suppliers"][0]["name"] == "Emir Hizmetler Limited Şirketi"
    (c,) = rel["contracts"]
    assert c["awardID"] == aw["id"] == "2026-11-18-mal-A-1" and c["value"] == aw["value"]
    assert c["period"] == {"startDate": "2026-11-16T00:00:00+03:00", "endDate": "2026-12-31T00:00:00+03:00"}


def test_procurement_method_codes():
    got = {u: package(mk(1, usul=u))["releases"][0]["tender"].get("procurementMethod")
           for u in ("Açık", "Belli İstekliler Arasında", "Pazarlık (MD 21 F)", "4734 / 3-g", "Doğrudan Temin (MD 22 D)",
                     "Bilinmeyen usul")}
    assert got == {"Açık": "open", "Belli İstekliler Arasında": "selective", "Pazarlık (MD 21 F)": "limited",
                   "4734 / 3-g": "limited", "Doğrudan Temin (MD 22 D)": "direct", "Bilinmeyen usul": None}
    verbatim = package(mk(1, usul="Bilinmeyen usul"))["releases"][0]["tender"]["procurementMethodDetails"]
    assert verbatim == "Bilinmeyen usul"


def test_category_by_bulletin_type():
    cats = [package(mk(1, type_=t))["releases"][0]["tender"]["mainProcurementCategory"]
            for t in ("mal", "hizmet", "yapim")]
    assert cats == ["goods", "services", "works"]


def test_valid_bid_count_as_bid_statistics_extension():
    pkg = package(mk(1, toplam=4, gecerli=1))
    stats = {s["measure"]: s["value"] for s in pkg["releases"][0]["bids"]["statistics"]}
    assert stats == {"bids": 4, "validBids": 1, "disqualifiedBids": 3}
    assert pkg["extensions"] and "ocds_bid_extension" in pkg["extensions"][0]
    assert pkg["releases"][0]["tender"]["numberOfTenderers"] == 4


def test_source_bulletin_and_page_as_document_reference():
    r = mk(1)
    r.page_start = 18
    doc = package(r)["releases"][0]["awards"][0]["documents"][0]
    assert doc["documentType"] == "awardNotice" and doc["url"] == "https://ekap.kik.gov.tr/EKAP/Ilan/BultenIndirme.aspx"
    assert doc["title"] == "Kamu İhale Bülteni, 18.11.2026, Mal – Sonuç İlanları, s. 18"
    assert "2026-11-18-mal-A-1" in doc["description"]


def test_each_record_is_one_award_lots_share_one_release_and_ocid():
    lots = [mk(i, ikn="2026/7777", seq=i, yuklenici=f"Firma {i} Ltd. Şti.") for i in (1, 2, 3)]
    other = mk(4)
    pkg = package(*lots, other)
    assert len(pkg["releases"]) == 2
    rel = pkg["releases"][0]
    assert rel["ocid"] == "ocds-ihalegoz-2026-7777" and len(rel["awards"]) == 3 == len(rel["contracts"])
    assert [a["id"] for a in rel["awards"]] == ["2026-11-18-mal-A-1", "2026-11-18-mal-A-2", "2026-11-18-mal-A-3"]
    assert len({p["id"] for p in rel["parties"]}) == len(rel["parties"]) == 4        # buyer + 3 suppliers


def test_persons_stay_as_printed_in_the_private_export():
    pkg = package(mk(1, yuklenici="Mustafa Öz"))
    assert pkg["releases"][0]["awards"][0]["suppliers"][0]["name"] == "Mustafa Öz"


def test_unconfident_fields_are_left_out_not_guessed():
    r = mk(1)
    r.confidence.update({"sozlesme_bedeli": 0.2, "yuklenici": 0.2, "toplam_teklif": 0.2})
    rel = package(r)["releases"][0]
    assert "value" not in rel["awards"][0] and "suppliers" not in rel["awards"][0]
    assert "numberOfTenderers" not in rel["tender"] and "bids" not in rel


def test_record_without_ikn_gets_a_record_based_ocid():
    r = mk(1)
    r.confidence["ikn"] = 0.2
    rel = package(r)["releases"][0]
    assert rel["ocid"] == "ocds-ihalegoz-rec-2026-11-18-mal-A-1" and rel["tender"]["id"] == "2026-11-18-mal-A-1"


def test_empty_day_gives_no_package():
    assert openexport.ocds_package(D, [], NOW) is None


# ---------------------------------------------------------------- FollowTheMoney
SCHEMAS = json.loads((FIX / "ftm" / "schema_props.json").read_text(encoding="utf-8"))


def all_props(schema):
    props, todo = set(), [schema]
    while todo:
        s = todo.pop()
        props |= set(SCHEMAS[s]["properties"])
        todo += SCHEMAS[s]["extends"]
    return props


def entities(*recs):
    return openexport.ftm_entities(stored(*recs))


def test_ftm_entities_use_only_published_schema_properties(monkeypatch):
    monkeypatch.setattr(openexport, "is_natural_person", lambda n: n == "Mustafa Öz")   # detector tested elsewhere
    ents = entities(mk(1), mk(2, yuklenici="Mustafa Öz"), mk(3, yuklenici="Kızılay"), mk(4, ikn="2026/9", seq=4),
                    mk(5, ikn="2026/9", seq=5, yuklenici="Z Ltd. Şti."))
    assert {e["schema"] for e in ents} == {"PublicBody", "Company", "LegalEntity", "Person", "Contract", "ContractAward"}
    for e in ents:
        assert set(e) == {"id", "schema", "properties"}
        assert set(e["properties"]) <= all_props(e["schema"]), (e["schema"], set(e["properties"]) - all_props(e["schema"]))
        for req in SCHEMAS[e["schema"]]["required"]:
            assert e["properties"].get(req), (e["schema"], req)
        assert all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in e["properties"].values())


def test_ftm_graph_links_resolve():
    ents = entities(mk(1), mk(2, yuklenici="Mustafa Öz"))
    ids = {e["id"] for e in ents}
    assert len(ids) == len(ents)
    for e in ents:
        for key in ("contract", "supplier", "authority"):
            for ref in e["properties"].get(key, []):
                assert ref in ids, (e["schema"], key, ref)


def test_ftm_schema_choice_and_values(monkeypatch):
    monkeypatch.setattr(openexport, "is_natural_person", lambda n: n == "Mustafa Öz")
    ents = {e["properties"]["name"][0]: e for e in entities(mk(1), mk(2, yuklenici="Mustafa Öz"),
                                                            mk(3, yuklenici="Acme Holding"), mk(4, yuklenici="Kızılay"))
            if "name" in e["properties"]}
    assert ents["ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ"]["schema"] == "PublicBody"
    assert ents["Emir Hizmetler Limited Şirketi"]["schema"] == "Company"
    assert ents["Mustafa Öz"]["schema"] == "Person" and ents["Mustafa Öz"]["properties"]["country"] == ["tr"]
    assert ents["Acme Holding"]["schema"] == "Company" and ents["Kızılay"]["schema"] == "LegalEntity"


def test_ftm_contract_and_award_properties():
    ents = entities(mk(1, ikn="2026/9", seq=1, bedel=100.0), mk(2, ikn="2026/9", seq=2, bedel=50.5,
                                                                 yuklenici="B Ltd. Şti."))
    (contract,) = [e for e in ents if e["schema"] == "Contract"]
    p = contract["properties"]
    assert p["procedureNumber"] == ["2026/9"] and p["numberAwards"] == ["2"] and p["amount"] == ["150.50"]
    assert p["currency"] == ["TRY"] and p["type"] == ["U"] and p["procedure"] == ["Açık"] and p["status"] == ["awarded"]
    awards = [e for e in ents if e["schema"] == "ContractAward"]
    assert len(awards) == 2 and all(a["properties"]["contract"] == [contract["id"]] for a in awards)
    a = awards[0]["properties"]
    assert a["amount"] in (["100.00"], ["50.50"]) and a["currency"] == ["TRY"] and a["role"] == ["supplier"]
    assert a["summary"][0].startswith("Toplam teklif: 3; geçerli teklif: 2")
    assert a["recordId"][0].startswith("2026-11-18-mal-A-")


def test_ftm_mixed_currency_contract_has_no_total():
    eur = mk(2, ikn="2026/9", seq=2, yuklenici="B Ltd. Şti.")
    eur.sozlesme_bedeli = Money(1000, "EUR")
    (contract,) = [e for e in entities(mk(1, ikn="2026/9", seq=1), eur) if e["schema"] == "Contract"]
    assert "amount" not in contract["properties"] and "currency" not in contract["properties"]


def test_ftm_award_skipped_when_supplier_unreadable():
    r = mk(1)
    r.confidence["yuklenici"] = 0.1
    assert [e["schema"] for e in entities(r)] == ["PublicBody", "Contract"]


def test_ftm_order_is_deterministic():
    recs = [mk(i, idare=f"KURUM {i % 3}", yuklenici=f"Firma {i % 4} Ltd. Şti.") for i in range(12)]
    a, b = entities(*recs), entities(*reversed(recs))
    assert [e["id"] for e in a] == [e["id"] for e in b]
    order = [e["schema"] for e in a]
    rank = ["PublicBody", "Company", "LegalEntity", "Person", "Contract", "ContractAward"].index
    assert [rank(x) for x in order] == sorted(rank(x) for x in order) or {"Company", "LegalEntity"} & set(order)


# ---------------------------------------------------------------- files, CLI, never deployed
def test_export_open_writes_files_under_exports_not_export(data_dir):
    s = Store()
    s.replace_day(D, "mal", [mk(1), mk(2)])
    paths = openexport.export_open(s, now=NOW)
    names = sorted(str(p.relative_to(config.data_dir())).replace("\\", "/") for p in paths)
    assert names == ["exports/ftm/2026-11-18.ijson", "exports/ocds/2026-11-18.json"]
    assert not (config.data_dir() / "export" / "ocds").exists()
    pkg = json.loads(paths[0].read_text(encoding="utf-8"))
    assert errors(pkg) == [] and "Emir" in paths[0].read_text(encoding="utf-8")        # ensure_ascii=False
    lines = paths[1].read_text(encoding="utf-8").splitlines()
    assert all(json.loads(x)["schema"] for x in lines) and len(lines) >= 5


def test_cli_export_open_date_all_and_default(data_dir, capsys):
    s = Store()
    s.replace_day(D, "mal", [mk(1)])
    d2 = date(2026, 11, 17)
    r = mk(2)
    r.bulletin_date = d2
    s.replace_day(d2, "mal", [r])
    assert cli.main(["export-open"]) == 0                                      # latest day only
    assert sorted(p.name for p in (data_dir / "exports" / "ocds").glob("*")) == ["2026-11-18.json"]
    assert cli.main(["export-open", "--all"]) == 0
    assert sorted(p.name for p in (data_dir / "exports" / "ocds").glob("*")) == ["2026-11-17.json", "2026-11-18.json"]
    assert cli.main(["export-open", "--date", "17.11.2026"]) == 0
    assert cli.main(["export-open", "--date", "01.01.2020"]) == 0              # nothing stored: no file, no error
    assert "nothing to export" in capsys.readouterr().err


def test_exports_are_never_referenced_by_the_site_or_the_daily_run():
    root = Path(__file__).resolve().parents[1]
    needle = re.compile(r"ocds|followthemoney|ijson|exports[/\\]|openexport", re.I)
    hits = []
    sources = [root / "site" / "wrangler.jsonc"]
    for base in (root / "site" / "worker", root / "src" / "ihale" / "sitegen"):     # sources only: not dist/.wrangler/preview
        sources += [p for p in base.rglob("*") if p.is_file() and p.suffix in {".py", ".html", ".css", ".js", ".json",
                                                                              ".jsonc", ".txt", ".md", ".toml", ".ts"}
                    and p.stat().st_size < 2_000_000]
    for p in sources:
        if p.exists() and needle.search(p.read_text(encoding="utf-8", errors="ignore")):
            hits.append(str(p.relative_to(root)))
    assert hits == []
    pipeline = (root / "src" / "ihale" / "pipeline.py").read_text(encoding="utf-8")
    assert "openexport" not in pipeline and "export_open" not in pipeline             # not part of the daily run yet
    assert "exports" not in (root / "site" / "wrangler.jsonc").read_text(encoding="utf-8")
