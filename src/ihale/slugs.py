"""Turkish-aware ASCII slugs, unique and stable: once issued, a slug never changes (map kept in the data dir)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import config
from .keys import turkish_lower

_ASCII = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"})
MAX_LEN = 80
_TR_ORDER = "abcçdefgğhıijklmnoöprsştuüvyz"
_TR_RANK = {c: i for i, c in enumerate(_TR_ORDER)}


def slugify(text: str) -> str:
    """'ANTALYA İL SAĞLIK MÜDÜRLÜĞÜ' -> 'antalya-il-saglik-mudurlugu' (never empty)."""
    s = turkish_lower(text).translate(_ASCII)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > MAX_LEN:
        s = s[:MAX_LEN].rsplit("-", 1)[0] or s[:MAX_LEN]
    return s or "x"


def tr_sort_key(text: str) -> tuple:
    """Turkish alphabetical order (c < ç, g < ğ, ı < i, o < ö, s < ş, u < ü); digits first, others last."""
    low = turkish_lower(text)
    return tuple((0, 0, ch) if ch.isdigit() else (1, _TR_RANK[ch], ch) if ch in _TR_RANK else (2, 0, ch)
                 for ch in low)


def slugs_path() -> Path:
    return config.data_dir() / "slugs.json"


class SlugMap:
    """kind ('idare' | 'yuklenici') → {key: slug}. Issue-once; persisted by save()."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else slugs_path()
        try:
            self.map: dict[str, dict[str, str]] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.map = {}
        self._dirty = False

    def slug(self, kind: str, key: str) -> str:
        m = self.map.setdefault(kind, {})
        if key in m:
            return m[key]
        base = slugify(key)
        used = set(m.values())
        cand, n = base, 2
        while cand in used:
            cand = f"{base}-{n}"
            n += 1
        m[key] = cand
        self._dirty = True
        return cand

    def issue_all(self, kind: str, keys) -> None:
        """Issue slugs for new keys in sorted order, so a fresh map is deterministic."""
        for k in sorted(keys):
            self.slug(kind, k)

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.map, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        self._dirty = False
