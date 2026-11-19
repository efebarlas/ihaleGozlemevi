"""Parser for EKAP "sonuç ilanları" bulletins (mal; the frame is shared by hizmet/yapım).

Approach (see docs/bulletin-layout.md §5): work on word coordinates, not text lines.

1. Crop every page body (between the header rule at top≈73 and the footer rule at top≈793).
2. Group words into rows. Each row is split at the colon column (x≈242) into a
   label part (left), a colon flag and a value part (right).
3. Join all pages' rows, then cut records at the ``SONUÇ İLANI`` marker.
4. Inside a record, rows are classified as group heading (``1- İhalenin``), label start
   (``a) Tarihi :``), label continuation, or value-only. Labels printed vertically centred
   between value lines are re-attached geometrically.
5. Fields are keyed by (group, label text), never by the ``a)``/``d)`` letters.

Confidence (docs/data-contract.md §1): >= CONFIDENT only when the label was found in its
proper group *and* the value matched its expected shape. Empty value after the colon:
``None`` with confidence 1.0. Label not found / shape mismatch: ``None``, low confidence.
The parser never raises on a bad record.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pdfplumber

from .model import CONFIDENT, Money, Record

log = logging.getLogger(__name__)

BODY_TOP = 74.0       # header rule at ~73
BODY_BOTTOM = 792.0   # footer rule at ~793
COLON_LO = 239.0      # colon sits at x0≈242
VALUE_X0 = 245.5      # values start at x0≈248
ROW_TOL = 2.6         # words whose vertical centres differ by less belong to one row
CENTRED_GAP = 13.0   # label-to-previous-row pitch is ~14.5; wrapped value lines are ~11.5 apart
OK = 0.95             # confidence for "label in right group and shape matched"
LOW = 0.3

_MARKER = "SONUÇ İLANI"
_END = "Kamuoyuna saygıyla duyurulur"

_RE_SEQ = re.compile(r"^\d+$")
_RE_NUMBERED = re.compile(r"^(\d+)\.\s+(\d{4}/\d+(?:-\d+)?)\s*(.*)$")
_RE_IKN = re.compile(r"^\d{4}/\d+(?:-\d+)?$")
_RE_HEAD = re.compile(r"^\d+\s*-\s*(\S.*)$")
_RE_LETTER = re.compile(r"^[a-zçğıöşü]\)\s*(.*)$")
_RE_SECTION = re.compile(r"^([AB])\s*-\s*4734")
_RE_FOOTER = re.compile(r"kik\.gov\.tr\s*(\d+)")
_NUM = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_RE_MONEY = re.compile(rf"^({_NUM})\s*([A-Za-z]{{2,4}})(?:\s*\(\s*({_NUM})\s*([A-Za-z]{{2,4}})\s*\))?$")
_RE_DATE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
_RE_INT = re.compile(r"^\d+$")


def _norm(s: str) -> str:
    """Case/punctuation-insensitive Turkish-aware key (for matching only)."""
    s = s.replace("İ", "i").replace("I", "ı").lower()
    return re.sub(r"[\W_]+", "", s)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class _Row:
    page: int        # source page number (footer number, else pdf index + 1)
    top: float
    left: str
    colon: bool
    right: str

    @property
    def full(self) -> str:
        return _clean(f"{self.left} {self.right}")


# ---------------------------------------------------------------- extraction

def _page_rows(page, pdf_index: int) -> list[_Row]:
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    page_no = pdf_index + 1
    body = []
    foot = []
    for w in words:
        if w["top"] >= BODY_BOTTOM:
            foot.append(w)
        elif w["top"] > BODY_TOP:
            body.append(w)
    if foot:
        foot.sort(key=lambda w: w["x0"])
        m = _RE_FOOTER.search(" ".join(w["text"] for w in foot))
        if m:
            page_no = int(m.group(1))
    body.sort(key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"]))
    groups: list[list[dict]] = []
    ys: list[float] = []
    for w in body:
        y = (w["top"] + w["bottom"]) / 2
        if groups and abs(y - ys[-1]) <= ROW_TOL:
            groups[-1].append(w)
            ys[-1] = (ys[-1] * (len(groups[-1]) - 1) + y) / len(groups[-1])
        else:
            groups.append([w])
            ys.append(y)
    rows = []
    for g, y in zip(groups, ys):
        g.sort(key=lambda w: w["x0"])
        left, right, colon = [], [], False
        for w in g:
            if w["x0"] >= VALUE_X0:
                right.append(w["text"])
            elif w["x0"] >= COLON_LO and w["text"] == ":":
                colon = True
            elif w["x0"] >= COLON_LO:
                right.append(w["text"])  # unexpected word in the colon band: treat as value
            else:
                left.append(w["text"])
        rows.append(_Row(page_no, y, " ".join(left), colon, " ".join(right)))
    return rows


def _extract_rows(pdf_path: Path) -> list[_Row]:
    rows: list[_Row] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                rows.extend(_page_rows(page, i))
            except Exception as e:  # pragma: no cover - defensive
                log.warning("page %d: row extraction failed: %s", i + 1, e)
            page.flush_cache()
    return rows


# -------------------------------------------------------------- value shapes

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
    t = _clean(text)
    return t or None


_PARSERS = {"money": _money, "date": _date, "int": _int, "text": _text}

# (group, normalised label) -> (attribute, shape)
_FIELD_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("ikn", _norm("İhale kayıt numarası")): ("ikn", "ikn"),
    ("ihale", _norm("Tarihi")): ("ihale_tarihi", "date"),
    ("ihale", _norm("Türü")): ("ihale_turu", "text"),
    ("ihale", _norm("Usulü")): ("ihale_usulu", "text"),
    ("ihale", _norm("Yaklaşık Maliyeti")): ("yaklasik_maliyet", "money"),
    ("ihale", _norm("Sözleşmeye Esas Kısımlarının Yaklaşık Maliyeti")): ("esas_kisim_yaklasik_maliyet", "money"),
    ("konu", _norm("Adı")): ("konu", "text"),
    ("teklif", _norm("Toplam Teklif Sayısı")): ("toplam_teklif", "int"),
    ("teklif", _norm("Toplam Geçerli Teklif Sayısı")): ("gecerli_teklif", "int"),
    ("sozlesme", _norm("Tarihi")): ("sozlesme_tarihi", "date"),
    ("sozlesme", _norm("Bedeli")): ("sozlesme_bedeli", "money"),
    ("sozlesme", _norm("Süresi")): ("sozlesme_suresi", "text"),
    ("sozlesme", _norm("Yüklenicisi")): ("yuklenici", "text"),
    ("sozlesme", _norm("Yüklenici")): ("yuklenici", "text"),
    ("sozlesme", _norm("Yüklenicinin uyruğu")): ("yuklenici_uyrugu", "text"),
    ("sozlesme", _norm("Yüklenicinin adresi")): ("yuklenici_adresi", "text"),
}
# Fields every record is expected to carry; others (esas kısım, uyruk) are layout-dependent.
_REQUIRED = (
    "ikn", "ihale_tarihi", "ihale_turu", "ihale_usulu", "yaklasik_maliyet", "konu",
    "toplam_teklif", "gecerli_teklif", "sozlesme_tarihi", "sozlesme_bedeli",
    "sozlesme_suresi", "yuklenici", "yuklenici_adresi",
)

_GROUPS = (
    ("ihalenin", "ihale"),
    ("ihalekonusu", "konu"),
    ("teklifler", "teklif"),
    ("sözleşmenin", "sozlesme"),
)


def _group_of(heading: str) -> str | None:
    n = _norm(heading)
    for prefix, g in _GROUPS:
        if n.startswith(prefix):
            return g
    return None


# ---------------------------------------------------------------- one record

def _split_title_idare(r0: str, lines: list[str]) -> tuple[str | None, str | None, bool]:
    """Numbered title (+wrap), the plain duplicate, then the idare block.

    Returns (title, idare, matched). `matched` is False when the duplicate could not be
    located, in which case title/idare are best guesses.
    """
    n = len(lines)
    for a in range(0, n):
        numbered = _clean(" ".join([r0] + lines[:a]))
        target = _norm(numbered)
        if not target:
            continue
        for b in range(a + 1, n):  # b < n: the idare block must be non-empty
            if _norm(" ".join(lines[a:b])) == target:
                return numbered, _clean(" ".join(lines[b:])), True
            if len(_norm(" ".join(lines[a:b]))) > len(target):
                break
    # fallback: keep the numbered line, assume the idare is the last line(s)
    if n >= 2:
        return _clean(r0) or None, _clean(lines[-1]) or None, False
    return _clean(r0) or None, None, False


def _parse_record(rows: list[_Row], rec: Record, numbered_ikn: str | None, tail_complete: bool) -> None:
    conf = rec.confidence
    warn = rec.warnings
    if not tail_complete:
        warn.append("kayıt 'Kamuoyuna saygıyla duyurulur.' ile bitmiyor (kesik kayıt)")

    # --- header block: numbered title, title again, idare, up to the ikn row
    ikn_idx = next((k for k, r in enumerate(rows) if _norm(r.left).startswith(_norm("İhale kayıt numarası"))), None)
    head_rows = rows[: ikn_idx if ikn_idx is not None else 0]
    if ikn_idx is None:
        warn.append("'İhale kayıt numarası' etiketi bulunamadı")
        ikn_idx = 0
        head_rows = []
    if head_rows:
        m = _RE_NUMBERED.match(head_rows[0].full)
        if m:
            seq_in_title, ikn_in_title, r0 = int(m.group(1)), m.group(2), m.group(3)
            if seq_in_title != rec.seq:
                warn.append(f"başlık satırındaki sıra no ({seq_in_title}) ile bölüm sırası ({rec.seq}) farklı")
            lines = [r.full for r in head_rows[1:] if r.full]
            title, idare, matched = _split_title_idare(r0, lines)
            rec.title = title
            rec.idare = idare
            conf["title"] = OK if (title and matched) else (0.5 if title else 0.0)
            conf["idare"] = OK if (idare and matched) else (0.5 if idare else 0.0)
            if not matched:
                warn.append("başlık tekrarı eşleşmedi; idare adı tahmini")
            numbered_ikn = ikn_in_title
        else:
            warn.append("numaralı başlık satırı çözümlenemedi")
            conf["title"] = 0.0
            conf["idare"] = 0.0
    else:
        conf["title"] = 0.0
        conf["idare"] = 0.0
        warn.append("başlık/idare bloğu bulunamadı")

    # --- classify rows after (and including) the ikn row
    body = rows[ikn_idx:] if rows else []
    kinds: list[str] = []
    for r in body:
        if r.colon and _norm(r.left).startswith(_norm("İhale kayıt numarası")):
            kinds.append("label")
        elif r.left and not r.colon and not r.right and _RE_HEAD.match(r.left):
            kinds.append("head")
        elif r.left and _RE_LETTER.match(r.left):
            kinds.append("label")
        elif r.left:
            kinds.append("lcont")
        elif r.right:
            kinds.append("value")
        else:
            kinds.append("empty")

    # --- re-attach value rows when the label is printed between them (vertically centred)
    owner_override: dict[int, int] = {}
    for k, kind in enumerate(kinds):
        if kind != "label" or k == 0:
            continue
        # Label rows are ~14.5pt apart from the previous row; a value-only row closer than
        # CENTRED_GAP above means the label is vertically centred inside a multi-line cell.
        below = 0
        j = k + 1
        while (j < len(body) and kinds[j] == "value" and body[j].page == body[k].page
               and body[j].top - body[j - 1].top <= CENTRED_GAP):
            below += 1
            j += 1
        j = k - 1
        taken = 0
        prev_top = body[k].top
        while (j > 0 and kinds[j] == "value" and j not in owner_override
               and body[j].page == body[k].page and prev_top - body[j].top < CENTRED_GAP
               and taken < max(below, 1)):
            owner_override[j] = k
            taken += 1
            prev_top = body[j].top
            j -= 1

    # --- build fields
    group = "ikn"
    fields: list[dict] = []  # {group, label_parts, parts: [(row_idx, text)], row}
    cur = None
    owner_of_row: dict[int, dict] = {}
    for k, (r, kind) in enumerate(zip(body, kinds)):
        if kind == "head":
            m = _RE_HEAD.match(r.left)
            g = _group_of(m.group(1)) if m else None
            group = g or "?"
            cur = None
        elif kind == "label":
            label = r.left if group == "ikn" and k == 0 else (_RE_LETTER.match(r.left).group(1))
            cur = {"group": group, "label": [label], "parts": [], "row": k, "colon": r.colon}
            if r.right:
                cur["parts"].append((k, r.right))
            fields.append(cur)
            owner_of_row[k] = cur
        elif kind == "lcont":
            if cur is not None:
                cur["label"].append(r.left)
                if r.right:
                    cur["parts"].append((k, r.right))
        elif kind == "value":
            if k in owner_override:
                continue  # attached below
            if cur is not None:
                cur["parts"].append((k, r.right))
    for j, k in owner_override.items():
        owner_of_row[k]["parts"].append((j, body[j].right))

    seen: set[str] = set()
    found: dict[str, tuple[str, str | None, bool]] = {}  # attr -> (shape, raw value text, centred)
    for f in fields:
        key = (f["group"], _norm(" ".join(f["label"])))
        spec = _FIELD_MAP.get(key)
        if not spec:
            continue
        attr, shape = spec
        if attr in seen:
            warn.append(f"{attr}: etiket birden fazla kez görüldü; ilki kullanıldı")
            continue
        seen.add(attr)
        raw = _clean(" ".join(t for _, t in sorted(f["parts"])))
        found[attr] = (shape, raw, any(owner_override.get(j) == f["row"] for j, _ in f["parts"]))

    for attr, (shape, raw, centred) in found.items():
        if attr == "ikn":
            if not raw:
                setattr(rec, "ikn", None)
                conf["ikn"] = 1.0
            elif _RE_IKN.match(raw):
                rec.ikn = raw
                conf["ikn"] = OK
                if numbered_ikn and numbered_ikn != raw:
                    conf["ikn"] = 0.5
                    warn.append(f"ikn: başlıktaki ({numbered_ikn}) ile etiketteki ({raw}) farklı")
            else:
                rec.ikn = None
                conf["ikn"] = LOW
                warn.append(f"ikn: beklenmeyen biçim {raw!r}")
            continue
        if not raw:
            setattr(rec, attr, None)
            conf[attr] = 1.0  # known empty
            continue
        val = _PARSERS[shape](raw)
        if val is None:
            setattr(rec, attr, None)
            conf[attr] = LOW
            warn.append(f"{attr}: beklenmeyen biçim {raw!r}")
        else:
            setattr(rec, attr, val)
            conf[attr] = OK
    if rec.ikn is None and "ikn" not in conf and numbered_ikn:
        rec.ikn = numbered_ikn
        conf["ikn"] = 0.5
        warn.append("ikn etiketten değil başlık satırından alındı")
    for attr in _REQUIRED:
        if attr not in found and attr not in conf:
            conf[attr] = 0.0
            warn.append(f"{attr}: etiket bulunamadı")
    # optional, layout-dependent fields: only reported when present (already in `found`)


# ----------------------------------------------------------------- top level

def _is_page_heading(text: str) -> bool:
    return bool(_RE_SECTION.match(text)) or text.startswith(("1. İHALE SONUÇLARININ", "1.1. "))


def parse_rows(rows: list[_Row], bulletin_date: date, bulletin_type: str, source_file: str) -> list[Record]:
    """Cut the joined row stream into records and parse each one."""
    n = len(rows)
    marker_idx = [k for k, r in enumerate(rows) if r.full == _MARKER]
    # section at each row index
    section_at = []
    cur_section = None
    for r in rows:
        m = _RE_SECTION.match(r.full)
        if m:
            cur_section = m.group(1)
        section_at.append(cur_section)

    starts = []  # index of the seq row (or the marker row when no seq row precedes it)
    for mi in marker_idx:
        starts.append(mi - 1 if mi > 0 and _RE_SEQ.match(rows[mi - 1].full) else mi)

    records: list[Record] = []
    prev_seq = None
    implied_section = "A"
    for n_i, (mi, s) in enumerate(zip(marker_idx, starts)):
        limit = starts[n_i + 1] if n_i + 1 < len(starts) else n
        for k in range(mi + 1, limit):  # a section heading cannot be inside a record
            if _is_page_heading(rows[k].full):
                limit = k
                break
        end = None
        for k in range(mi + 1, limit):
            if rows[k].full.startswith(_END):
                end = k
                break
        complete = end is not None
        last = end if end is not None else limit - 1
        body = rows[mi + 1 : (end if end is not None else limit)]
        seq = int(rows[s].full) if s != mi else 0
        section = section_at[s]
        extra_warn = []
        if section is None:
            # no heading seen yet (e.g. excerpt): infer from restarts of the running number
            if prev_seq is not None and seq <= prev_seq and seq == 1:
                implied_section = "B" if implied_section == "A" else implied_section
            section = implied_section
            extra_warn.append("bölüm başlığı görülmedi; bölüm sıra numarasından tahmin edildi")
        prev_seq = seq
        rec = Record(
            bulletin_date=bulletin_date,
            bulletin_type=bulletin_type,
            source_file=source_file,
            section=section,
            seq=seq,
            page_start=rows[s].page,
            page_end=rows[last].page if last >= 0 else rows[s].page,
        )
        rec.warnings.extend(extra_warn)
        if s == mi:
            rec.warnings.append("sıra numarası bulunamadı")
        try:
            _parse_record(body, rec, None, complete)
        except Exception as e:  # never raise on a single bad record
            rec.warnings.append(f"kayıt çözümlenemedi: {e!r}")
            for name in list(rec.confidence):
                rec.confidence[name] = min(rec.confidence[name], LOW)
        # honesty: a record with warnings about structure must not claim certainty elsewhere
        records.append(rec)
    return records


def parse_bulletin(pdf_path: Path, bulletin_date: date, bulletin_type: str = "mal") -> list[Record]:
    """Parse a *_SONUC.pdf bulletin into one Record per SONUÇ İLANI, in document order."""
    pdf_path = Path(pdf_path)
    rows = _extract_rows(pdf_path)
    return parse_rows(rows, bulletin_date, bulletin_type, pdf_path.name)
