import io
import zipfile
from datetime import date

import pytest

from ihale import config, ekap


def tiny_zip(names=("BULTEN_18112026_MAL.pdf", "BULTEN_18112026_MAL_SONUC.pdf")):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n in names:
            zf.writestr(n, b"%PDF-1.4 fake " + n.encode())
    return buf.getvalue()


def test_data_dir_override_and_non_ascii(data_dir):
    assert config.data_dir() == data_dir.resolve()
    assert "Masaüstü" in str(config.data_dir())
    assert config.bulletins_dir() == config.data_dir() / "bulletins"
    assert config.db_path().name == "ihale.db"


def test_save_zip_layout(data_dir):
    d = ekap.save_zip(config.bulletins_dir(), date(2026, 11, 18), "mal", tiny_zip())
    assert d == data_dir.resolve() / "bulletins" / "2026-11-18"
    assert (d / "MAL.zip").is_file()
    assert (d / "BULTEN_18112026_MAL_SONUC.pdf").read_bytes().startswith(b"%PDF")
    assert not list(d.glob("*.part"))


def test_save_zip_flattens_paths(data_dir):
    d = ekap.save_zip(config.bulletins_dir(), date(2026, 11, 18), "mal", tiny_zip(("../../evil.pdf",)))
    assert (d / "evil.pdf").exists()
    assert not (data_dir / "evil.pdf").exists()


def test_bad_zip_writes_nothing(data_dir):
    with pytest.raises(zipfile.BadZipFile):
        ekap.save_zip(config.bulletins_dir(), date(2026, 11, 18), "mal", b"PKnot a zip")
    assert not (config.bulletins_dir() / "2026-11-18" / "MAL.zip").exists()


def test_fetch_is_read_through_cache(data_dir):
    ekap.save_zip(config.bulletins_dir(), date(2026, 11, 18), "mal", tiny_zip())

    class Boom:
        headers = {}

        def request(self, *a, **k):
            raise AssertionError("must not hit network when cached")

    c = ekap.EkapClient(session=Boom())
    assert c.fetch(date(2026, 11, 18), "mal").name == "2026-11-18"
    assert c.requests_made == 0


def test_fetch_downloads_then_saves(data_dir, form_html, tmp_path):
    payload = tiny_zip()

    class Resp:
        def __init__(self, content, ctype):
            self.status_code, self.content, self.encoding = 200, content, "utf-8"
            self.headers = {"Content-Type": ctype}

    class Sess:
        headers = {}
        seen = []

        def request(self, method, url, **kw):
            Sess.seen.append((method, kw.get("data")))
            if method == "GET":
                return Resp(form_html.encode("utf-8"), "text/html")
            return Resp(payload, "text/html")

    ticks = iter(range(10**6, 10**9, 100))
    rl = ekap.RateLimiter(tmp_path / "rl.txt", clock=lambda: next(ticks), sleep=lambda s: None)
    c = ekap.EkapClient(limiter=rl, session=Sess())
    d = c.fetch(date(2026, 11, 18), "mal")
    assert (d / "MAL.zip").exists()
    assert [m for m, _ in Sess.seen] == ["GET", "POST"]
    assert Sess.seen[1][1][ekap.TYPE_FIELD] == "1"


def test_unknown_type_rejected():
    with pytest.raises(ValueError):
        ekap.EkapClient(session=type("S", (), {"headers": {}})()).fetch(date(2026, 11, 18), "bogus")
