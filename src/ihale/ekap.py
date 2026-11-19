"""Polite EKAP bulletin downloader (plain HTTP, ASP.NET WebForms postback).

Politeness is enforced here, not by convention:
  * RateLimiter: >= MIN_INTERVAL seconds between ANY two EKAP requests, across processes
    (shared timestamp file under the data dir, guarded by an OS file lock).
  * Hard cap of MAX_REQUESTS_PER_RUN requests per EkapClient (process run).
  * Strictly sequential; honest User-Agent; no retries.
  * Blocking (403/429, CAPTCHA/challenge, login wall) raises BlockedError. Never retry or work around.

Bulletin knowledge (from the 2022 code): files are named BULTEN_{ddmmyyyy}_{TYPE}.zip and the zip holds
BULTEN_{ddmmyyyy}_{TYPE}.pdf and BULTEN_{ddmmyyyy}_{TYPE}_SONUC.pdf (results). See docs/bulletin-layout.md.
"""
from __future__ import annotations

import io
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

import ssl
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from . import config

BASE_URL = "https://ekap.kik.gov.tr"
FORM_URL = f"{BASE_URL}/EKAP/Ilan/BultenIndirme.aspx"
MIN_INTERVAL = 10.0
MAX_REQUESTS_PER_RUN = 20
TIMEOUT = (15, 120)  # connect, read

TYPE_CODES = {"mal": "1", "yapim": "2", "hizmet": "3", "danismanlik": "4"}
TYPE_FIELD = "ctl00$ContentPlaceHolder1$ddlstBxIhaleTur"
DATE_FIELD = "ctl00$ContentPlaceHolder1$etBultenTarihi$EkapTakvimTextBox_etBultenTarihi"
BUTTON_FIELD = "ctl00$ContentPlaceHolder1$btnYukle"


# ---------------------------------------------------------------- errors
class EkapError(Exception):
    """Base class."""


class BlockedError(EkapError):
    """HARD STOP: EKAP is blocking us (403/429, CAPTCHA/challenge, login wall). Do not retry."""


class NoBulletinError(EkapError):
    """EKAP says there is no bulletin for that date/type (weekend, holiday, not published yet)."""


class FormChangedError(EkapError):
    """The form page no longer looks like what we expect (control names changed?)."""


class UnexpectedResponseError(EkapError):
    """Response was neither a zip, a no-bulletin notice, nor an obvious block."""


class BulletinMismatchError(EkapError):
    """EKAP served a different bulletin than requested (a malformed request makes it quietly serve today's)."""


class RequestBudgetExceeded(EkapError):
    """Per-run request cap reached."""


# ---------------------------------------------------------------- rate limiter
class _FileLock:
    """Tiny cross-process lock on a file (msvcrt on Windows, fcntl elsewhere)."""

    def __init__(self, path: Path):
        self.path = path
        self.fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a+b")
        if sys.platform == "win32":
            import msvcrt

            self.fh.seek(0)
            while True:
                try:
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.2)
        else:
            import fcntl

            fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        try:
            if sys.platform == "win32":
                import msvcrt

                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.fh, fcntl.LOCK_UN)
        finally:
            self.fh.close()


class RateLimiter:
    """Guarantees >= min_interval seconds between consecutive requests, across processes.

    State: last-request wall-clock timestamp in `state_file`. `clock`/`sleep` are injectable for tests.
    Call wait() right before sending and mark() right after the response arrives (so long downloads
    also count toward the gap).
    """

    def __init__(self, state_file: Path, min_interval: float = MIN_INTERVAL,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep):
        self.state_file = Path(state_file)
        self.min_interval = min_interval
        self.clock = clock
        self.sleep = sleep
        self._lock = _FileLock(self.state_file.with_suffix(".lock"))

    def _read(self) -> float:
        try:
            return float(self.state_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return 0.0

    def _write(self, t: float) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(repr(t), encoding="utf-8")

    def wait(self) -> None:
        """Block until >= min_interval since the last request, then stamp 'now'."""
        with self._lock:
            while True:
                remaining = self._read() + self.min_interval - self.clock()
                if remaining <= 0:
                    break
                self.sleep(remaining)
            self._write(self.clock())

    def mark(self) -> None:
        """Stamp 'now' (response finished)."""
        with self._lock:
            self._write(self.clock())


# ---------------------------------------------------------------- form parsing
class _FormParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden: dict[str, str] = {}
        self.names: set[str] = set()
        self.buttons: dict[str, str] = {}
        self.selects: dict[str, list[list[str]]] = {}
        self._cur_select: str | None = None
        self._cur_opt: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input":
            if a.get("name"):
                self.names.add(a["name"])
                typ = (a.get("type") or "").lower()
                if typ == "hidden":
                    self.hidden[a["name"]] = a.get("value") or ""
                elif typ in ("submit", "button", "image"):
                    self.buttons[a["name"]] = a.get("value") or ""
        elif tag == "select" and a.get("name"):
            self.names.add(a["name"])
            self._cur_select = a["name"]
            self.selects[self._cur_select] = []
        elif tag == "option" and self._cur_select:
            self._cur_opt = [a.get("value", ""), ""]
            self.selects[self._cur_select].append(self._cur_opt)

    def handle_data(self, data):
        if self._cur_opt is not None:
            self._cur_opt[1] += data

    def handle_endtag(self, tag):
        if tag == "option":
            self._cur_opt = None
        elif tag == "select":
            self._cur_select = None


@dataclass
class FormInfo:
    hidden: dict[str, str]
    selects: dict[str, list[tuple[str, str]]]
    names: set[str]
    buttons: dict[str, str]


def parse_form(html: str) -> FormInfo:
    """Extract hidden fields and verify the controls we post are still there."""
    p = _FormParser()
    p.feed(html)
    for needed in (TYPE_FIELD, DATE_FIELD):
        if needed not in p.names:
            raise FormChangedError(f"form control missing: {needed}")
    # The "Bülten İndir" button is a link: href="javascript:__doPostBack('<BUTTON_FIELD>','')"
    if BUTTON_FIELD not in html.replace("&#39;", "'"):
        raise FormChangedError(f"postback target missing: {BUTTON_FIELD}")
    if "__VIEWSTATE" not in p.hidden:
        raise FormChangedError("__VIEWSTATE missing")
    codes = {v for v, _ in p.selects.get(TYPE_FIELD, [])}
    if not set(TYPE_CODES.values()) <= codes:
        raise FormChangedError(f"type select options changed: {sorted(codes)}")
    return FormInfo(hidden=p.hidden, names=p.names, buttons=p.buttons,
                    selects={k: [(v, t) for v, t in opts] for k, opts in p.selects.items()})


def build_postback(info: FormInfo, type_: str, day: date) -> dict[str, str]:
    data = dict(info.hidden)
    data[TYPE_FIELD] = TYPE_CODES[type_]
    data[DATE_FIELD] = day.strftime("%d.%m.%Y")
    # __doPostBack(target, argument) in a plain POST: these two fields are added by JS, not in the HTML
    data["__EVENTTARGET"] = BUTTON_FIELD
    data["__EVENTARGUMENT"] = ""
    return data


# ---------------------------------------------------------------- block / response classification
_BLOCK_PATTERNS = [
    r"captcha", r"cf-challenge", r"challenge-platform", r"just a moment",
    r"attention required", r"access denied", r"are you a robot", r"unusual traffic", r"erişim engellen",
    r"güvenlik doğrulama", r"robot olmad",
]
_LOGIN_PATTERNS = [r"giriş yap", r"kullanıcı adı", r"login\.aspx", r"type=[\"']password"]
# POST answers only; the form page itself contains client-side alert() strings, so they are not markers.
_NO_BULLETIN_PATTERNS = [r"bülten bulunamad", r"bulten bulunamad", r"kayıt bulunamad", r"bülteni yayımlanmam[ıi]şt[ıi]r",
                         r"alert\s*\(['\"][^)]*(bulunamad|bulunmamakta|yayımlan)"]


def classify_response(status: int, content_type: str, body: bytes, *, is_form_get: bool = False) -> str:
    """Return 'zip', 'form', 'no_bulletin'; raise BlockedError / UnexpectedResponseError otherwise."""
    if status in (403, 429):
        raise BlockedError(f"HTTP {status} from EKAP: blocked/rate limited. Stop and escalate.")
    if status in (401, 407, 511):
        raise BlockedError(f"HTTP {status} from EKAP: authentication wall. Stop and escalate.")
    if body[:2] == b"PK" and status < 400:
        return "zip"
    if status >= 400:
        raise UnexpectedResponseError(f"HTTP {status} from EKAP")
    text = body.decode("utf-8", errors="replace")
    low = text.lower()
    for pat in _BLOCK_PATTERNS:
        if re.search(pat, low):
            raise BlockedError(f"challenge/CAPTCHA marker in response ({pat!r}). Stop and escalate.")
    has_form = TYPE_FIELD.lower() in low
    if is_form_get:
        if not has_form:
            for pat in _LOGIN_PATTERNS:
                if re.search(pat, low):
                    raise BlockedError(f"login wall marker ({pat!r}). Stop and escalate.")
            raise UnexpectedResponseError("form page missing expected controls")
        return "form"
    # POST answer that is HTML: holiday alert, or form re-rendered without a file
    for pat in _NO_BULLETIN_PATTERNS:
        if re.search(pat, low):
            return "no_bulletin"
    if not has_form:
        for pat in _LOGIN_PATTERNS:
            if re.search(pat, low):
                raise BlockedError(f"login wall marker ({pat!r}). Stop and escalate.")
    raise UnexpectedResponseError("POST returned HTML that is neither a zip nor a recognised no-bulletin notice")


def check_zip_filename(headers, day: date, type_: str) -> None:
    """Content-Disposition filename must be BULTEN_{ddmmyyyy}_{TYPE}.zip for the requested date and type."""
    cd = next((v for k, v in headers.items() if k.lower() == "content-disposition"), "")
    m = re.search(r"filename=\"?([^\";\s]+)", cd, re.I)
    got = m.group(1) if m else None
    expected = f"BULTEN_{day:%d%m%Y}_{type_.upper()}.zip"
    if got is None or got.upper() != expected.upper():
        raise BulletinMismatchError(f"requested {expected} but EKAP served {got!r}; not saving")


# ---------------------------------------------------------------- storage
def bulletin_paths(root: Path, day: date, type_: str) -> tuple[Path, Path]:
    d = Path(root) / day.isoformat()
    return d, d / f"{type_.upper()}.zip"


def save_zip(root: Path, day: date, type_: str, payload: bytes) -> Path:
    """Write <root>/<yyyy-mm-dd>/<TYPE>.zip and extract beside it. Returns the directory."""
    d, zpath = bulletin_paths(root, day, type_)
    d.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:  # validates before writing anything
        names = zf.namelist()
        tmp = zpath.with_suffix(".zip.part")
        tmp.write_bytes(payload)
        for info in zf.infolist():
            name = Path(info.filename).name  # flatten: no path traversal
            if not name or info.is_dir():
                continue
            (d / name).write_bytes(zf.read(info))
        os.replace(tmp, zpath)  # zip last: its presence means "done"
    return d


# ---------------------------------------------------------------- client
@dataclass
class _Response:
    status_code: int
    headers: dict
    content: bytes
    encoding: str = "utf-8"


def _make_ssl_context() -> ssl.SSLContext:
    """ekap.kik.gov.tr only offers TLS1.2 RSA-kex suites (e.g. AES128-GCM-SHA256), which OpenSSL's
    default security level 2 refuses (SSLV3_ALERT_HANDSHAKE_FAILURE). Drop to level 1; keep cert
    verification on (system trust store)."""
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    return ctx


class _UrllibSession:
    """Minimal stdlib HTTP session (cookies kept, redirects followed, HTTP errors returned not raised).

    Same `.headers` / `.request(method, url, data=dict, timeout=...)` shape the tests inject fakes for."""

    def __init__(self):
        self.headers: dict[str, str] = {}
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar()),
            urllib.request.HTTPSHandler(context=_make_ssl_context()),
        )

    def request(self, method: str, url: str, data: dict | None = None, timeout=None, **_ignored) -> _Response:
        body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, method=method, headers=dict(self.headers))
        if body is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            resp = self._opener.open(req, timeout=max(timeout) if isinstance(timeout, tuple) else timeout)
        except urllib.error.HTTPError as e:  # 4xx/5xx: let classify_response decide
            resp = e
        with resp:
            content = resp.read()
            headers = {k: v for k, v in resp.headers.items()}
            charset = resp.headers.get_content_charset() or "utf-8"
            return _Response(resp.status if hasattr(resp, "status") else resp.code, headers, content, charset)


class EkapClient:
    def __init__(self, limiter: RateLimiter | None = None, session=None,
                 max_requests: int = MAX_REQUESTS_PER_RUN, form_cache: Path | None = None):
        self.limiter = limiter or RateLimiter(config.data_dir() / "ekap-last-request.txt")
        self.session = session if session is not None else _UrllibSession()
        self.session.headers["User-Agent"] = config.USER_AGENT
        self.max_requests = max_requests
        self.requests_made = 0
        self.form_cache = form_cache  # dev aid: reuse saved form HTML, skip the GET
        self._form: FormInfo | None = None

    def _request(self, method: str, **kw) -> _Response:
        if self.requests_made >= self.max_requests:
            raise RequestBudgetExceeded(f"cap of {self.max_requests} EKAP requests per run reached")
        self.limiter.wait()
        self.requests_made += 1
        try:
            return self.session.request(method, FORM_URL, timeout=TIMEOUT, **kw)
        finally:
            self.limiter.mark()

    def load_form(self) -> FormInfo:
        if self._form is None:
            if self.form_cache and Path(self.form_cache).exists():
                html = Path(self.form_cache).read_text(encoding="utf-8")
            else:
                r = self._request("GET")
                classify_response(r.status_code, r.headers.get("Content-Type", ""), r.content, is_form_get=True)
                html = r.content.decode(r.encoding or "utf-8", errors="replace")
                if self.form_cache:
                    Path(self.form_cache).parent.mkdir(parents=True, exist_ok=True)
                    Path(self.form_cache).write_text(html, encoding="utf-8")
            self._form = parse_form(html)
        return self._form

    def fetch(self, day: date, type_: str, root: Path | None = None, force: bool = False) -> Path:
        """Read-through cache. Returns the bulletin directory. Raises NoBulletinError / BlockedError."""
        if type_ not in TYPE_CODES:
            raise ValueError(f"unknown type {type_!r}; expected one of {sorted(TYPE_CODES)}")
        root = Path(root) if root else config.bulletins_dir()
        d, zpath = bulletin_paths(root, day, type_)
        if zpath.exists() and not force:
            return d
        info = self.load_form()
        r = self._request("POST", data=build_postback(info, type_, day))
        kind = classify_response(r.status_code, r.headers.get("Content-Type", ""), r.content)
        if kind == "no_bulletin":
            raise NoBulletinError(f"no {type_} bulletin for {day:%d.%m.%Y}")
        check_zip_filename(r.headers, day, type_)
        return save_zip(root, day, type_, r.content)


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%d.%m.%Y").date()
