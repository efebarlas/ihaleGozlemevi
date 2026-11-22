"""İdare type and province classifier: the seam (SPEC §11). Taxonomy and tie-breaks: docs/idare-taxonomy.md.

Implementations behind one interface `classify(name, impl) -> Classification(turu, il, confidence, source)`:
  * keywords  coded rules over the name (the taxonomy's tie-break order)
  * table     lookup in data/idare_table.jsonl by normalized idare key (built once by a build session)
  * hybrid    the table when its confidence >= 0.9, else keywords
  * table_first  the table whenever the key is present (any confidence), keywords only on a table miss

Which implementation feeds the peer groups is config (`IHALE_PEER_CLASSIFIER`): `legacy` (default; today's peer rules in
peers.py, unchanged), `keywords`, `table` or `hybrid`. Promotion is decided on scripts/eval_classify.py numbers.
Shadow mode: every flag run logs keyword-vs-table disagreements to <data>/logs/classify-shadow-<date>.jsonl.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import config
from .keys import normalize_key, turkish_lower

TURU: dict[str, str] = {
    "buyuksehir_belediyesi": "Büyükşehir belediyesi",
    "belediye": "Belediye",
    "belediye_sirketi": "Belediye şirketi / bağlı kuruluşu",
    "il_ozel_idaresi": "İl özel idaresi",
    "valilik_kaymakamlik": "Valilik / kaymakamlık",
    "saglik": "Hastane / sağlık",
    "universite": "Üniversite",
    "meb_okul": "MEB / okul",
    "karayollari": "Karayolları",
    "dsi": "DSİ",
    "dmo": "DMO",
    "tcdd": "TCDD",
    "enerji_kit": "Enerji KİT",
    "diger_kit": "Diğer KİT / kamu şirketi",
    "tsk_guvenlik": "TSK / jandarma / emniyet",
    "adalet": "Adalet / cezaevi",
    "bakanlik_tasra": "Bakanlık taşra teşkilatı",
    "merkezi_idare": "Merkezi idare",
    "diger": "Diğer",
}

# Plural noun phrases for peer-group labels, e.g. "Antalya'daki belediyeler (mal, açık)".
TURU_PLURAL: dict[str, str] = {
    "buyuksehir_belediyesi": "büyükşehir belediyeleri", "belediye": "belediyeler",
    "belediye_sirketi": "belediye şirketleri", "il_ozel_idaresi": "il özel idareleri",
    "valilik_kaymakamlik": "valilik ve kaymakamlıklar", "saglik": "sağlık idareleri",
    "universite": "üniversiteler", "meb_okul": "milli eğitim idareleri", "karayollari": "karayolları idareleri",
    "dsi": "DSİ idareleri", "dmo": "DMO birimleri", "tcdd": "TCDD birimleri", "enerji_kit": "enerji KİT'leri",
    "diger_kit": "diğer KİT'ler", "tsk_guvenlik": "güvenlik idareleri", "adalet": "adalet idareleri",
    "bakanlik_tasra": "bakanlık taşra birimleri", "merkezi_idare": "merkezi idareler", "diger": "diğer idareler",
}

IMPLEMENTATIONS = ("keywords", "table", "hybrid", "table_first")
PEER_CLASSIFIERS = ("legacy",) + IMPLEMENTATIONS
HYBRID_MIN_CONFIDENCE = 0.9
PEER_ENV = "IHALE_PEER_CLASSIFIER"
TABLE_ENV = "IHALE_IDARE_TABLE"


@dataclass(frozen=True)
class Classification:
    turu: str | None          # a code from TURU, or None when the implementation has no answer (table miss)
    il: str | None            # one of the 81 provinces, or None
    confidence: float
    source: str               # "keywords" | "table" | "table:miss" | "hybrid:table" | "hybrid:keywords"


# ---------------------------------------------------------------- keywords
# (turu, confidence, predicate) in tie-break order (docs/idare-taxonomy.md). `s` is the Turkish-lowercased name.
def _starts(*prefixes):
    return lambda s: any(s.startswith(p) for p in prefixes)


def _has(*words):
    return lambda s: any(w in s for w in words)


def _tokens(s: str) -> set[str]:
    from .keys import _tokens as toks
    return set(toks(s))


_COMPANY = ("a.ş", "a. ş", "anonim", "şirketi", "ltd", "limited")


def _is_belediye_sirketi(s: str) -> bool:
    if "su ve kanalizasyon idaresi" in s:
        return True
    return ("belediye" in s or "büyükşehir" in s) and any(c in s for c in _COMPANY)


def _is_saglik(s: str) -> bool:
    if "sağlık bakanlığı" in s and not ("il sağlık" in s or "hastane" in s):
        return False
    return _has("hastane", "sağlık müdürlüğü", "halk sağlığı", "ağız ve diş", "toplum sağlığı", "aile sağlığı",
                "sağlık merkezi", "devlet hastanesi", "sağlık")(s)


RULES: list[tuple[str, float, callable]] = [
    ("dmo", 0.95, _starts("devlet malzeme ofisi")),
    ("tcdd", 0.95, lambda s: s.startswith("tcdd") or s.startswith("türkiye cumhuriyeti devlet demiryolları")),
    ("dsi", 0.95, lambda s: s.startswith("devlet su işleri") or "dsi" in _tokens(s)),
    ("karayollari", 0.9, _has("karayolları")),
    ("enerji_kit", 0.9, _starts("elektrik üretim", "türkiye elektrik iletim", "botaş", "boru hatları ile petrol",
                                 "türkiye petrolleri", "tpao", "türkiye kömür işletmeleri", "türkiye taşkömürü",
                                 "türkiye elektrik ticaret", "eüaş", "teiaş")),
    ("diger_kit", 0.9, _starts("ptt", "devlet hava meydanları işletmesi", "türkiye şeker fabrikaları",
                                "türkiye radyo", "trt", "türk hava yolları", "çay işletmeleri", "toprak mahsulleri",
                                "makina ve kimya endüstrisi", "türkiye denizcilik işletmeleri", "tigem",
                                "türkiye tarım işletmeleri", "tüvasaş", "tülomsaş", "türkiye halk bankası")),
    ("universite", 0.9, _has("üniversite")),
    ("belediye_sirketi", 0.85, _is_belediye_sirketi),
    ("buyuksehir_belediyesi", 0.9, _has("büyükşehir belediye")),
    ("belediye", 0.9, _has("belediye")),
    ("il_ozel_idaresi", 0.9, _has("il özel idare")),
    ("valilik_kaymakamlik", 0.8, _has("valiliği", "kaymakamlığı")),
    ("saglik", 0.85, _is_saglik),
    ("meb_okul", 0.85, _has("milli eğitim", "millî eğitim", "okulu", "okul müdürlüğü", "lisesi", "anaokulu",
                             "ilkokulu", "ortaokulu", "halk eğitim", "rehberlik", "eğitim uygulama")),
    ("adalet", 0.85, _has("ceza infaz", "cezaevi", "adliye", "adalet", "tutukevi", "başsavcılığı", "hakimler")),
    ("tsk_guvenlik", 0.85, _has("jandarma", "emniyet", "polis", "komutanlığı", "askeri", "askerlik", "tugay",
                                 "kolordu", "savunma", "sahil güvenlik", "tabur", "garnizon", "kuvvetleri")),
    ("bakanlik_tasra", 0.6, lambda s: "müdürlüğü" in s and bool(_tokens(s) & {"il", "ilçe", "bölge", "şube"})),
    ("merkezi_idare", 0.5, _has("bakanlığı", "genel müdürlüğü", "başkanlığı", "kurumu", "cumhurbaşkanlığı",
                                 "büyük millet", "müsteşarlığı", "kurulu")),
]
FALLBACK_CONFIDENCE = 0.3


def _il(name: str) -> str | None:
    from .peers import _legacy_il_of
    return _legacy_il_of(name)


def classify_keywords(name: str | None) -> Classification:
    if not name or not name.strip():
        return Classification("diger", None, FALLBACK_CONFIDENCE, "keywords")
    s = " ".join(turkish_lower(name).split())
    for turu, conf, pred in RULES:
        if pred(s):
            return Classification(turu, _il(name), conf, "keywords")
    return Classification("diger", _il(name), FALLBACK_CONFIDENCE, "keywords")


# ---------------------------------------------------------------- table
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def table_path() -> Path:
    override = os.environ.get(TABLE_ENV)
    return Path(override) if override else repo_root() / "data" / "idare_table.jsonl"


def load_table(path: Path | None = None) -> dict[str, dict]:
    """key → row. Missing file → empty table. Later lines for the same key win."""
    p = Path(path) if path else table_path()
    rows: dict[str, dict] = {}
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        key = row.get("key") or normalize_key(row.get("name"))
        if key:
            rows[key] = row
    return rows


_TABLE: dict | None = None
_TABLE_ID: tuple | None = None


def _table() -> dict[str, dict]:
    global _TABLE, _TABLE_ID
    p = table_path()
    try:
        ident = (str(p), p.stat().st_mtime_ns)
    except OSError:
        ident = (str(p), None)
    if _TABLE is None or ident != _TABLE_ID:
        _TABLE, _TABLE_ID = load_table(p), ident
        _cached.cache_clear()
    return _TABLE


def classify_table(name: str | None) -> Classification:
    row = _table().get(normalize_key(name) or "")
    if row is None:
        return Classification(None, None, 0.0, "table:miss")
    turu = row.get("turu")
    if turu not in TURU:
        return Classification(None, None, 0.0, "table:miss")
    return Classification(turu, row.get("il"), float(row.get("confidence", 0.0)), "table")


def classify_hybrid(name: str | None) -> Classification:
    t = classify_table(name)
    if t.turu is not None and t.confidence >= HYBRID_MIN_CONFIDENCE:
        return Classification(t.turu, t.il, t.confidence, "hybrid:table")
    k = classify_keywords(name)
    return Classification(k.turu, k.il, k.confidence, "hybrid:keywords")


TABLE_FIRST_MIN_CONFIDENCE = 0.7     # below this a table row is only a guess and must not move a record


def classify_table_first(name: str | None) -> Classification:
    """The table whenever the key is present with confidence >= 0.7; keywords on a miss or a low-confidence row
    (source `table_first:keywords_lowconf`), so a weak table guess cannot move a record on or off Bugün."""
    t = classify_table(name)
    if t.turu is not None and t.confidence >= TABLE_FIRST_MIN_CONFIDENCE:
        return Classification(t.turu, t.il, t.confidence, "table_first:table")
    k = classify_keywords(name)
    source = "table_first:keywords" if t.turu is None else "table_first:keywords_lowconf"
    return Classification(k.turu, k.il, k.confidence, source)


_IMPL = {"keywords": classify_keywords, "table": classify_table, "hybrid": classify_hybrid,
         "table_first": classify_table_first}


@lru_cache(maxsize=65536)
def _cached(name: str | None, impl: str) -> Classification:
    return _IMPL[impl](name)


def classify(name: str | None, impl: str = "keywords") -> Classification:
    if impl not in _IMPL:
        raise ValueError(f"unknown classifier {impl!r}; expected one of {IMPLEMENTATIONS}")
    _table()                      # refresh when the table file changed (clears the cache)
    return _cached(name, impl)


def peer_classifier() -> str:
    """The implementation feeding the peer groups: $IHALE_PEER_CLASSIFIER, default `table_first`.

    Promoted 2026-11-22 after the SPEC §11 evaluation (table 97.5% vs keywords 89.0% turu on 200 independent
    hand labels) and three shadow runs (261 stable disagreements, 3% table misses -> keywords). `legacy` stays
    selectable for comparison."""
    v = (os.environ.get(PEER_ENV) or "table_first").strip().lower()
    if v not in PEER_CLASSIFIERS:
        raise ValueError(f"{PEER_ENV}={v!r}; expected one of {PEER_CLASSIFIERS}")
    return v


# ---------------------------------------------------------------- shadow mode
def shadow_log_path(day) -> Path:
    return config.data_dir() / "logs" / f"classify-shadow-{day.isoformat()}.jsonl"


def new_names_path() -> Path:
    return config.data_dir() / "logs" / "classify-new-names.txt"


def shadow_log(names, day) -> Path:
    """Compute keywords and table for every distinct idare name and log the disagreements (turu or il).

    Names missing from the table are not disagreements; they are counted in the summary line. The file for `day` is
    rewritten by each run (a flag run is a full recompute).
    """
    names = sorted({n for n in names if n})
    lines, in_table, disagree, missing = [], 0, 0, []
    for n in names:
        k, t = classify(n, "keywords"), classify(n, "table")
        if t.turu is None:
            missing.append(n)
            continue
        in_table += 1
        if (k.turu, k.il) != (t.turu, t.il):
            disagree += 1
            lines.append({"idare": n, "key": normalize_key(n),
                          "keywords": {"turu": k.turu, "il": k.il, "confidence": k.confidence},
                          "table": {"turu": t.turu, "il": t.il, "confidence": t.confidence},
                          "turu_differs": k.turu != t.turu, "il_differs": k.il != t.il})
    lines.append({"summary": {"date": day.isoformat(), "names": len(names), "in_table": in_table,
                              "disagreements": disagree, "misses": len(missing),
                              "miss_rate": round(len(missing) / len(names), 4) if names else 0.0,
                              "peer_classifier": peer_classifier()}})
    p = shadow_log_path(day)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")
    os.replace(tmp, p)
    _remember_new_names(missing)
    return p


def _remember_new_names(missing: list[str]) -> None:
    """Accumulate unique names that are not in the table (one per line), so a build session can extend it."""
    f = new_names_path()
    try:
        known = set(f.read_text(encoding="utf-8").splitlines())
    except OSError:
        known = set()
    clean = lambda n: " ".join(n.split())  # one line per name
    fresh = sorted({clean(n) for n in missing} - known)
    if fresh:
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a", encoding="utf-8", newline=chr(10)) as fh:
            fh.write("".join(n + chr(10) for n in fresh))
