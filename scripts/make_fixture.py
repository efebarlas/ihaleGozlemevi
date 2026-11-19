"""Cut a small excerpt fixture out of a full *_SONUC.pdf (dev tool, not used by tests).

usage: python scripts/make_fixture.py <mal|hizmet|yapim> <BULTEN_..._SONUC.pdf>
Writes tests/fixtures/<type>_sonuc_excerpt.pdf. Page selection (1-based pages of the 2026-11-18 bulletins)
is documented in docs/bulletin-layout.md.
"""
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

PAGES = {
    "mal": [17, 18, 19, 20, 21, 22, 84, 85, 203, 204, 205, 257],
    "hizmet": [5, 6, 7, 9, 10, 16, 17, 51, 52, 53, 54, 55],
    "yapim": [4, 5, 6, 7, 27, 28, 29, 30, 31, 44, 45, 46],
}
kind, src = sys.argv[1], sys.argv[2]
r = PdfReader(src)
w = PdfWriter()
for n in PAGES[kind]:
    w.add_page(r.pages[n - 1])
w.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
for p in w.pages:
    p.compress_content_streams()
out = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / f"{kind}_sonuc_excerpt.pdf"
with open(out, "wb") as f:
    w.write(f)
print(out, out.stat().st_size)
