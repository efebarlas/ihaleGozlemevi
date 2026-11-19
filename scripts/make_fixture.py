"""Cut tests/fixtures/mal_sonuc_excerpt.pdf out of a full *_MAL_SONUC.pdf (dev tool, not used by tests).

usage: python scripts/make_fixture.py <BULTEN_..._MAL_SONUC.pdf>
Page selection documented in docs/bulletin-layout.md.
"""
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

PAGES = [17, 18, 19, 20, 21, 22, 84, 85, 203, 204, 205, 257]  # 1-based, from 2026-11-18 MAL_SONUC
r = PdfReader(sys.argv[1])
w = PdfWriter()
for n in PAGES:
    w.add_page(r.pages[n - 1])
w.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
for p in w.pages:
    p.compress_content_streams()
out = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "mal_sonuc_excerpt.pdf"
with open(out, "wb") as f:
    w.write(f)
print(out, out.stat().st_size)
