"""KVKK (SPEC §6.1): the contractor address (and its province) is stored in the DB / raw_fields only.
Nothing under export/ or the built site may carry it."""
from datetime import date

from ihale import config, pipeline
from ihale.export import export_all
from ihale.sitegen import build
from ihale.store import Store

from rec_helpers import rec

ADDRESS = "Gizli Mahallesi 4711 Sokak No: 7 İç Kapı No: 3 Çankaya / Ankara Çankaya/Ankara"


def _records():
    out = []
    for seq, (yuk, il) in enumerate([("Emir Limited Şirketi", "Ankara"), ("Mehmet Kaya", "İzmir")], start=1):
        r = rec(seq, ikn=f"2026/{seq}", yuklenici=yuk, yuklenici_adresi=ADDRESS if seq == 1 else
                "Sokak Adresi Kişisel 99 Karşıyaka/İzmir", yuklenici_il=il, downloaders=12)
        r.confidence.update({"yuklenici_adresi": 0.95, "yuklenici_il": 0.95, "downloaders": 0.95})
        r.raw_fields = [("4", "Yüklenicinin adresi", r.yuklenici_adresi)]
        out.append(r)
    return out


def test_address_is_stored_but_never_exported_or_built(tmp_path):
    store = Store()
    store.replace_day(date(2026, 11, 18), "mal", _records())
    back = store.all_records()
    assert back[0].record.yuklenici_adresi == ADDRESS and back[0].record.yuklenici_il == "Ankara"
    assert back[0].record.downloaders == 12                      # stored; the site does not show it in M5a
    assert back[0].record.raw_fields == [("4", "Yüklenicinin adresi", ADDRESS)]

    pipeline.flag_all(store)
    out = export_all(store)
    site = tmp_path / "dist"
    build(out, site, split_bulk=False)

    needles = [ADDRESS, "Gizli Mahallesi", "Sokak Adresi Kişisel", "yuklenici_adresi", "yuklenici_il"]
    checked = 0
    for root in (out, site):
        for f in root.rglob("*"):
            if f.is_file():
                data = f.read_bytes()
                text = data.decode("utf-8", errors="replace")
                for n in needles:
                    assert n not in text, f"{n!r} found in {f}"
                checked += 1
    assert checked > 5   # the export and the site really were written
