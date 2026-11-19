"""Normalized grouping keys for idare and yüklenici names (docs/data-contract.md §3).

Conservative on purpose: no fuzzy matching, no ASCII folding (ş != s, ı != i). A false merge is worse than a
missed one. Person names go through the same function and only lose case, punctuation and extra whitespace.
"""
from __future__ import annotations

import re
import unicodedata

_COMBINING_DOT = "̇"


def turkish_lower(s: str) -> str:
    """Lowercase with the Turkish dotted/dotless rules: İ→i, I→ı (Python's own lower() maps İ to i + U+0307)."""
    s = unicodedata.normalize("NFC", s)
    s = s.replace("İ", "i").replace("I", "ı")
    s = s.lower().replace(_COMBINING_DOT, "")
    return unicodedata.normalize("NFC", s)


def _tokens(s: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat[0] in "LNM" or ch == "&":
            buf.append(ch)
        else:  # whitespace, punctuation, symbols → separator
            if buf:
                out.append("".join(buf))
                buf = []
    if buf:
        out.append("".join(buf))
    return out


# Suffix phrases on tokens (already lowercased, punctuation removed). Longest first.
_PHRASES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("sanayi", "ve", "ticaret"), ("san", "tic")),
    (("san", "ve", "tic"), ("san", "tic")),
    (("limited", "şirketi"), ("ltd",)),
    (("limited", "sirketi"), ("ltd",)),
    (("limited", "şti"), ("ltd",)),
    (("ltd", "şirketi"), ("ltd",)),
    (("ltd", "şti"), ("ltd",)),
    (("anonim", "şirketi"), ("as",)),
    (("a", "ş"), ("as",)),
    (("aş",), ("as",)),
]


def _apply_phrases(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        for pat, rep in _PHRASES:
            n = len(pat)
            # Never rewrite at the very start: a name that *begins* with "AŞ"/"A Ş" is more likely a
            # person ("Aş") than a legal form, and the legal form always follows a name.
            if i > 0 and tuple(tokens[i:i + n]) == pat:
                out.extend(rep)
                i += n
                break
        else:
            out.append(tokens[i])
            i += 1
    return out


def normalize_key(name: str | None) -> str | None:
    """Grouping key for an idare / yüklenici name, or None if nothing usable is left."""
    if not name:
        return None
    toks = _tokens(turkish_lower(name))
    toks = _apply_phrases(toks)
    key = " ".join(toks)
    return key or None
