"""Parser for EKAP "sonuç ilanları" bulletins: a thin adapter over ihalent (MIT, SPEC §4.1).

``ihalent.bulletin`` reads the PDF's two-column form into ``BulletinNotice`` objects
(``ikn``, ``section``, ``page``, ``title``, ``authority`` and ``(part, label, value)``
fields). This module maps each notice to our :class:`~ihale.model.Record`.

What the adapter adds on top of ihalent (each is a shortfall for our use):

* **Source page numbers.** ihalent drops the page footer and reports PDF indexes. We read the
  footer number (``Kamu İhale Kurumu – www.kik.gov.tr <n>``) so an excerpt reports the same
  pages as the full PDF; without a footer the PDF index + 1 is used.
* **Printed ``seq`` and ``page_end``.** ihalent keeps neither the printed running number nor
  where a notice ends. A light pass over the same word list recovers both.
* **Money.** ihalent's ``Award`` drops EUR/USD and dual figures. Money is parsed here from the raw
  field text (exact kuruş + currency; dual figure in ``Money.alt``).
* **Section mapping.** ihalent ``"4734"`` → ``"A"``; ``"istisna"`` / ``"kapsam-disi"`` → ``"B"``.
  The heading found in the pass above (``A- 4734`` / ``B- 4734``) wins when both exist and a
  disagreement is reported as a warning.
* **Rejected notices.** ihalent rejects a notice it cannot read with confidence
  (``BulletinRead.rejected``). Each one still becomes a Record (so the day's count stays honest)
  with whatever is recoverable (printed seq, section, pages, ikn from the header line), confidence
  below ``CONFIDENT`` and a warning carrying ihalent's reason.
* **Contractor address (4f / 3e)** (M5a). ihalent drops that row on purpose, so it is recovered here from the same word
  list: the value cell of the "Yüklenicinin adresi" label (a block of right-column lines, cut by line spacing like
  ihalent's own cells, continued across a page break until ``Kamuoyuna saygıyla duyurulur.``), joined with single
  spaces. ``yuklenici_il`` is the trailing ``İlçe/İl`` token when it is one of the 81 provinces. PRIVACY (SPEC §6.1):
  the address is stored in the DB and ``raw_fields`` only and must never reach an export or the site.
* **Downloaders (3a)**: ``Record.downloaders`` from ihalent's field "Dokümanı EKAP üzerinden e-imza kullanarak indiren
  sayısı" (long layout only; absent in the short layout, then None with no confidence entry).

Confidence (docs/data-contract.md §1): ≥ CONFIDENT only when ihalent produced the value (label found
in the right part of the form) and the value matches its expected shape. Empty value after the colon:
``None`` with confidence 1.0. A required label ihalent did not produce: ``None`` with confidence 0.0.
The parser never raises on a single bad notice.

``raw_fields`` carries ihalent's ``(part, label, value)`` triples verbatim, in order.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from ihalent import bulletin as ib

from .model import Money, Record
from .keys import turkish_lower
from .peers import PROVINCES

log = logging.getLogger(__name__)

OK = 0.95
LOW = 0.3

_RE_SEQ = re.compile(r"^\d+$")
_RE_SECTION = re.compile(r"^([AB])\s*-\s*4734")
_RE_FOOTER = re.compile(r"kik\.gov\.tr\s*(\d+)")
_RE_HEADER_IKN = re.compile(r"^\d+\.\s+(\d{4}/\d+(?:-\d+)?)\b")
_RE_IKN = re.compile(r"^\d{4}/\d+(?:-\d+)?$")
_NUM = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_RE_MONEY = re.compile(rf"^({_NUM})\s*([A-Za-z]{{2,4}})(?:\s*\(\s*({_NUM})\s*([A-Za-z]{{2,4}})\s*\))?$")
_RE_DATE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
_RE_INT = re.compile(r"^\d+$")
# the bulletin itself says there is no estimate: "- TRY", "... yaklaşık maliyeti bulunmamaktadır."
_RE_NO_AMOUNT = re.compile(r"bulunmamakta|^-+(\s*[A-Za-z]{2,4})?$", re.IGNORECASE)
_RE_ADDRESS_TAIL = re.compile(r"\S+/\S+$")
_HEADINGS = ("A- 4734", "B- 4734", "1. İHALE SONUÇ", "1.1. ", "1. İSTİSNA", "2. KAPSAM", "2.1. ", "1. KAPSAM")

_SECTION_MAP = {"4734": "A", "istisna": "B", "kapsam-disi": "B"}


# ----------------------------------------------------------------- value shapes

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _money(text: str) -> Money | None:
    m = _RE_MONEY.match(_clean(text))
    if not m:
        return None

    def kurus(s: str) -> int:
        return int(s.replace(".", "").replace(",", ""))

    alt = Money(kurus(m.group(3)), m.group(4)) if m.group(3) else None
    return Money(kurus(m.group(1)), m.group(2), alt)


def _date(text: str) -> date | None:
    m = _RE_DATE.match(_clean(text))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _int(text: str) -> int | None:
    t = _clean(text)
    return int(t) if _RE_INT.match(t) else None


def _text(text: str) -> str | None:
    return _clean(text) or None


def _ikn(text: str) -> str | None:
    t = _clean(text)
    return t if _RE_IKN.match(t) else None


_PARSERS = {"money": _money, "date": _date, "int": _int, "text": _text, "ikn": _ikn}

# attribute -> (part, label as printed (ihalent matches it folded), shape)
_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("ikn", "0", "İhale kayıt numarası", "ikn"),
    ("ihale_tarihi", "1", "Tarihi", "date"),
    ("ihale_turu", "1", "Türü", "text"),
    ("ihale_usulu", "1", "Usulü", "text"),
    ("yaklasik_maliyet", "1", "Yaklaşık Maliyeti", "money"),
    ("konu", "2", "Adı", "text"),
    ("toplam_teklif", "3", "Toplam Teklif Sayısı", "int"),
    ("gecerli_teklif", "3", "Toplam Geçerli Teklif Sayısı", "int"),
    ("sozlesme_tarihi", "4", "Tarihi", "date"),
    ("sozlesme_bedeli", "4", "Bedeli", "money"),
    ("sozlesme_suresi", "4", "Süresi", "text"),
)
_REQUIRED = tuple(f[0] for f in _FIELDS) + ("yuklenici",)


def _set(rec: Record, attr: str, raw: str | None, shape: str) -> None:
    """Assign one field from ihalent's raw value and score it (see module docstring)."""
    conf, warn = rec.confidence, rec.warnings
    if raw is None:  # label not produced by ihalent
        setattr(rec, attr, None)
        conf[attr] = 0.0
        warn.append(f"{attr}: etiket bulunamadı")
        return
    raw = _clean(raw)
    if not raw:
        setattr(rec, attr, None)
        conf[attr] = 1.0  # known empty
        return
    if shape == "money" and _RE_NO_AMOUNT.search(raw):
        setattr(rec, attr, None)
        conf[attr] = 1.0
        warn.append(f"{attr}: bülten tutar vermiyor ({raw!r})")
        return
    val = _PARSERS[shape](raw)
    if val is None:
        setattr(rec, attr, None)
        conf[attr] = LOW
        warn.append(f"{attr}: beklenmeyen biçim {raw!r}")
    else:
        setattr(rec, attr, val)
        conf[attr] = OK


# ------------------------------------------------------------ one notice → Record

def _fill_from_notice(rec: Record, n: ib.BulletinNotice) -> None:
    rec.raw_fields = [(p, lab, val) for p, lab, val in n.fields]
    for attr, part, label, shape in _FIELDS:
        _set(rec, attr, n.value(part, label), shape)
    # esas kısımların yaklaşık maliyeti: only on lot (kısmi) notices, so absence is normal
    esas = next((v for p, lab, v in n.fields if p == "1" and ib._fold(lab).startswith("sozlesmeye esas")), None)
    if esas is not None:
        _set(rec, "esas_kisim_yaklasik_maliyet", esas, "money")
    winner = n.value("4", "Yüklenicisi")
    if winner is None:
        winner = n.value("4", "Yüklenici")
    _set(rec, "yuklenici", winner, "text")
    uyruk = n.value("4", "Yüklenicinin uyruğu")
    if uyruk is not None:
        _set(rec, "yuklenici_uyrugu", uyruk, "text")
    dl = next((v for p, lab, v in n.fields if p == "3" and ib._fold(lab).startswith("dokumani")), None)
    if dl is not None:  # long layout only; the short layout has no such row
        _set(rec, "downloaders", dl, "int")
    # header block (ihalent only fills it when the title repeat was found)
    rec.title = n.title
    rec.idare = n.authority
    for attr, val in (("title", n.title), ("idare", n.authority)):
        if val:
            rec.confidence[attr] = OK
        else:
            rec.confidence[attr] = 0.0
            rec.warnings.append(f"{attr}: başlık bloğu çözümlenemedi")
    # ikn: ihalent already rejects a notice whose header ikn differs from the form's


# ------------------------------------------------------------------- PDF pass

def _words_and_pages(pdf_path: Path) -> tuple[list[ib.Word], dict[int, int]]:
    """Same word list as ``ihalent.bulletin.words_from_pdf``, plus {pdf page -> printed page}."""
    import pdfplumber

    words: list[ib.Word] = []
    pages: dict[int, int] = {}
    with pdfplumber.open(str(pdf_path)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            low, high = page.height * ib.HEADER_FRACTION, page.height * ib.FOOTER_FRACTION
            foot: list[dict] = []
            for w in page.extract_words(x_tolerance=1.5):
                if low < w["top"] < high:
                    words.append(ib.Word(number, w["x0"], w["top"], w["bottom"], w["text"]))
                elif w["top"] >= high:
                    foot.append(w)
            foot.sort(key=lambda w: w["x0"])
            m = _RE_FOOTER.search(" ".join(w["text"] for w in foot))
            pages[number] = int(m.group(1)) if m else number
            page.flush_cache()
    return words, pages


def _scan(words: list[ib.Word], pages: dict[int, int]) -> list[dict]:
    """Per ``SONUÇ İLANI``: printed seq, A/B heading, source pages and the header's ikn."""
    lines = ib.lines_from_words(words)
    colon_x = ib.colon_column(lines)
    left_limit = (colon_x - ib.COLON_TOLERANCE) if colon_x is not None else None
    out: list[dict] = []
    section: str | None = None
    cur: dict | None = None
    for i, line in enumerate(lines):
        t = line.text
        m = _RE_SECTION.match(t)
        if m:
            section = m.group(1)
        if t.upper() == "SONUÇ İLANI":
            prev = lines[i - 1] if i else None
            has_seq = prev is not None and _RE_SEQ.match(prev.text) is not None
            first = prev if has_seq else line
            cur = {
                "seq": int(prev.text) if has_seq else None,
                "section": section,
                "page_start": pages.get(first.page, first.page),
                "page_end": pages.get(line.page, line.page),
                "ikn": None,
                "open": True,
                "lines": [],
            }
            out.append(cur)
        elif cur is not None and cur["open"]:
            if t.startswith("Kamuoyuna saygıyla"):
                cur["page_end"] = pages.get(line.page, line.page)
                cur["open"] = False
            elif t.upper().startswith(_HEADINGS):
                continue
            else:
                cur["page_end"] = pages.get(line.page, line.page)
                cur["lines"].append(line)
                if cur["ikn"] is None:
                    h = _RE_HEADER_IKN.match(t)
                    if h:
                        cur["ikn"] = h.group(1)
    for rec in out:
        rec["address"] = _address_from_lines(rec.pop("lines"), left_limit)
    return out


def _split_line(line, left_limit: float) -> tuple[str, str, bool]:
    """(left label text, right value text, has colon) of one layout line."""
    left = [w.text for w in line.words if w.x0 < left_limit]
    right = [w.text for w in line.words if w.x0 >= left_limit]
    colon = bool(right) and right[0] == ":"
    return " ".join(left), " ".join(right[1:] if colon else right), colon


def _address_from_lines(lines, left_limit: float | None) -> str | None:
    """The value cell of "Yüklenicinin adresi": None when the label is absent, "" when it is empty.

    The cell is the label line's right-column text plus value-only lines (no label text) directly above or below it,
    at most CELL_GAP apart on the same page, and below it also across a page break up to the record end."""
    if left_limit is None:
        return None
    parts = [_split_line(ln, left_limit) for ln in lines]
    idx = next((k for k, (left, _, colon) in enumerate(parts)
                if colon and "yuklenicinin adresi" in ib._fold(left)), None)
    if idx is None:
        return None
    cell = [parts[idx][1]]
    # value lines printed above the label (label vertically centred in a multi-line cell)
    k, prev = idx - 1, lines[idx]
    while (k >= 0 and not parts[k][0] and parts[k][1] and lines[k].page == prev.page
           and prev.top - lines[k].top <= ib.CELL_GAP):
        cell.insert(0, parts[k][1])
        prev, k = lines[k], k - 1
    # value lines below it; a new page may continue the cell (the gap check only applies within a page)
    k, prev = idx + 1, lines[idx]
    while k < len(lines) and not parts[k][0] and parts[k][1]:
        if lines[k].page == prev.page and lines[k].top - prev.top > ib.CELL_GAP:
            break
        cell.append(parts[k][1])
        prev, k = lines[k], k + 1
    return _clean(" ".join(cell))


def _province_of(address: str) -> str | None:
    """The province in the trailing ``İlçe/İl`` token, canonical spelling, else None."""
    toks = address.split()
    token = toks[-1] if toks else ""
    if "/" not in token:
        return None
    last = turkish_lower(token.rsplit("/", 1)[1])
    return next((p for p in PROVINCES if turkish_lower(p) == last), None)


# ----------------------------------------------------------------- top level

def _fill_address(rec: Record, address: str | None) -> None:
    """yuklenici_adresi / yuklenici_il from the recovered cell (see module docstring)."""
    conf, warn = rec.confidence, rec.warnings
    if address is None:
        rec.yuklenici_adresi = rec.yuklenici_il = None
        conf["yuklenici_adresi"] = conf["yuklenici_il"] = 0.0
        warn.append("yuklenici_adresi: etiket bulunamadı")
        return
    if not address:
        rec.yuklenici_adresi = rec.yuklenici_il = None
        conf["yuklenici_adresi"] = conf["yuklenici_il"] = 1.0  # known empty
        return
    rec.yuklenici_adresi = address
    shaped = bool(_RE_ADDRESS_TAIL.search(address))        # ends with the printed "İlçe/İl"
    conf["yuklenici_adresi"] = OK if shaped else 0.5
    if not shaped:
        warn.append(f"yuklenici_adresi: sonunda İlçe/İl yok ({address[-40:]!r})")
    il = _province_of(address)
    rec.yuklenici_il = il
    conf["yuklenici_il"] = OK if (il and shaped) else 0.3
    if not il:
        warn.append(f"yuklenici_il: sondaki belirteç bir il değil ({address[-30:]!r})")


def parse_words(
    words: list[ib.Word], pages: dict[int, int], bulletin_date: date, bulletin_type: str, source_file: str
) -> tuple[list[Record], ib.BulletinRead]:
    read = ib.read_words(words, source=source_file)
    meta = _scan(words, pages)
    rejected = {r.position: r for r in read.rejected}
    notices = iter(read.notices)
    records: list[Record] = []
    prev_section = "A"
    for pos, info in enumerate(meta, start=1):
        rej = rejected.get(pos)
        notice = None if rej else next(notices, None)
        section = _SECTION_MAP.get(notice.section) if notice else None
        warn: list[str] = []
        if info["section"] and section and info["section"] != section:
            warn.append(f"bölüm: ihalent {notice.section!r}, başlık {info['section']!r}")
        section = info["section"] or section or prev_section
        prev_section = section
        rec = Record(
            bulletin_date=bulletin_date,
            bulletin_type=bulletin_type,
            source_file=source_file,
            section=section,
            seq=info["seq"] if info["seq"] is not None else 0,
            page_start=info["page_start"],
            page_end=info["page_end"],
        )
        rec.warnings.extend(warn)
        if info["open"]:
            rec.warnings.append("kayıt 'Kamuoyuna saygıyla duyurulur.' ile bitmiyor (kesik kayıt)")
        if info["seq"] is None:
            rec.warnings.append("sıra numarası bulunamadı")
        try:
            _fill_address(rec, info.get("address"))
            if notice is not None:
                _fill_from_notice(rec, notice)
                if rec.yuklenici_adresi:
                    rec.raw_fields.append(("4", "Yüklenicinin adresi", rec.yuklenici_adresi))
            else:
                reason = rej.reason if rej else "ihalent bu ilanı okumadı"
                rec.warnings.append(f"ihalent ilanı reddetti: {reason}")
                for name in _REQUIRED + ("title", "idare"):
                    rec.confidence[name] = 0.0
                if info["ikn"]:
                    rec.ikn = info["ikn"]
                    rec.confidence["ikn"] = 0.5  # from the header line only: never confident
        except Exception as e:  # never raise on a single bad notice
            rec.warnings.append(f"kayıt çözümlenemedi: {e!r}")
            for name in list(rec.confidence):
                rec.confidence[name] = min(rec.confidence[name], LOW)
        records.append(rec)
    if len(records) != len(read.notices) + len(read.rejected):
        log.warning("%s: %d SONUÇ İLANI markers but ihalent counted %d notices + %d rejected",
                    source_file, len(records), len(read.notices), len(read.rejected))
    return records, read


def parse_bulletin_read(pdf_path: Path, bulletin_date: date, bulletin_type: str = "mal"):
    """Like :func:`parse_bulletin` but also returns ihalent's ``BulletinRead`` (complete/missing/rejected)."""
    pdf_path = Path(pdf_path)
    words, pages = _words_and_pages(pdf_path)
    return parse_words(words, pages, bulletin_date, bulletin_type, pdf_path.name)


def parse_bulletin(pdf_path: Path, bulletin_date: date, bulletin_type: str = "mal") -> list[Record]:
    """Parse a *_SONUC.pdf into one Record per SONUÇ İLANI, in document order."""
    return parse_bulletin_read(pdf_path, bulletin_date, bulletin_type)[0]
