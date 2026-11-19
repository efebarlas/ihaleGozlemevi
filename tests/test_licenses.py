"""Every installed distribution reachable from our requirements must be permissively licensed (SPEC §4.1/§7).

Copyleft (GPL, LGPL, AGPL, MPL, EPL, CDDL, SSPL, EUPL) is a hard stop. Offline: reads importlib.metadata only.
"""
import re
from importlib import metadata

import pytest

ROOT = "ihale"
ROOT_EXTRAS = {"dev"}  # extras of our own project that we use (pytest)
FORBIDDEN = re.compile(
    r"(?i)(?<![A-Za-z])(?:A|L)?GPL(?![A-Za-z])|\bMPL\b|\bEPL\b|\bCDDL\b|\bSSPL\b|\bEUPL\b"
    r"|GNU (?:Lesser |Affero )?General Public|Mozilla Public|Eclipse Public|Common Development and Distribution"
    r"|European Union Public"
)
ALLOWED_EXPRESSIONS = {"PSF-2.0", "MIT-CMU", "MIT-0", "Unlicense"}  # explicitly fine


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_req(req: str):
    spec, _, marker = req.partition(";")
    name = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec).group(1)
    extras = set(re.findall(r"[A-Za-z0-9._-]+", (re.search(r"\[([^\]]*)\]", spec) or [None, ""])[1]))
    return _norm(name), extras, marker.strip()


def _reachable():
    """name -> distribution, walking Requires-Dist recursively (only extras actually requested)."""
    seen: dict[str, metadata.Distribution] = {}
    todo = [(_norm(ROOT), ROOT_EXTRAS)]
    wanted_extras: dict[str, set] = {}
    while todo:
        name, extras = todo.pop()
        new = extras - wanted_extras.get(name, set())
        if name in seen and not new:
            continue
        wanted_extras.setdefault(name, set()).update(extras)
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue  # not installed here (e.g. a platform-only dependency)
        seen[name] = dist
        for req in dist.requires or []:
            rname, rextras, marker = _parse_req(req)
            m = re.findall(r"extra\s*==\s*['\"]([^'\"]+)['\"]", marker)
            if m and not (set(_norm(x) for x in m) & set(_norm(x) for x in wanted_extras[name])):
                continue  # extra we do not use
            todo.append((rname, rextras))
    return seen


def _license_strings(dist):
    md = dist.metadata
    out = []
    for key in ("License-Expression", "License"):
        v = md.get(key)
        if v:
            out.append(v if len(v) < 200 else v[:200])  # a License field may hold the full text; head is enough
    out += [c for c in (md.get_all("Classifier") or []) if c.startswith("License ::")]
    return out


def test_reachable_includes_our_direct_dependencies():
    names = set(_reachable())
    assert {"ihale", "ihalent", "pdfplumber", "pypdf"} <= names


def test_requests_and_certifi_are_gone():
    names = set(_reachable())
    assert "requests" not in names and "certifi" not in names


def test_no_copyleft_licenses():
    bad = []
    for name, dist in sorted(_reachable().items()):
        if name == "ihale":
            continue
        for lic in _license_strings(dist):
            if lic in ALLOWED_EXPRESSIONS:
                continue
            if FORBIDDEN.search(lic):
                bad.append(f"{name}: {lic}")
    assert not bad, "copyleft/forbidden licenses in the dependency tree:\n" + "\n".join(bad)


def test_forbidden_regex_catches_the_obvious():
    for s in ("GPL-3.0", "LGPL-2.1-or-later", "AGPL-3.0", "MPL-2.0", "Mozilla Public License 2.0 (MPL 2.0)",
              "EPL-2.0", "CDDL-1.0", "SSPL-1.0", "EUPL-1.2", "License :: OSI Approved :: GNU General Public License v3 (GPLv3)"):
        assert FORBIDDEN.search(s), s
    for s in ("MIT", "BSD-3-Clause", "Apache-2.0", "PSF-2.0", "ISC", "MIT-CMU", "MIT-0", "Unlicense",
              "License :: OSI Approved :: MIT License"):
        assert not FORBIDDEN.search(s), s
