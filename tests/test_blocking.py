import pytest

from ihale import ekap


def classify(status=200, body=b"", ctype="text/html", **kw):
    return ekap.classify_response(status, ctype, body, **kw)


@pytest.mark.parametrize("status", [403, 429])
def test_http_block_codes(status):
    with pytest.raises(ekap.BlockedError):
        classify(status, b"nope")


@pytest.mark.parametrize("body", [
    "<html>Please complete the CAPTCHA</html>",
    "<title>Just a moment...</title><div id=cf-challenge>",
    "<h1>Access Denied</h1>",
    "Erişim engellendi",
])
def test_challenge_pages_are_block(body):
    with pytest.raises(ekap.BlockedError):
        classify(200, body.encode("utf-8"))
    with pytest.raises(ekap.BlockedError):
        classify(200, body.encode("utf-8"), is_form_get=True)


def test_login_wall_on_form_get():
    body = "<html><form><input type=password name=p /> Giriş Yap</form></html>"
    with pytest.raises(ekap.BlockedError):
        classify(200, body.encode("utf-8"), is_form_get=True)


def test_block_is_distinct_from_no_bulletin():
    assert not issubclass(ekap.BlockedError, ekap.NoBulletinError)
    assert not issubclass(ekap.NoBulletinError, ekap.BlockedError)


def test_no_bulletin_notice():
    body = "<script>alert('Bülten bulunamadı');</script>".encode("utf-8")
    assert classify(200, body) == "no_bulletin"


def test_zip_detected_even_with_html_content_type():
    # EKAP really answers with Content-Type: text/html and a zip body
    assert classify(200, b"PK\x03\x04rest", ctype="text/html") == "zip"


def test_real_form_page_is_form_and_not_block(form_html):
    assert classify(200, form_html.encode("utf-8"), is_form_get=True) == "form"


def test_unknown_html_post_is_unexpected_not_silent():
    with pytest.raises(ekap.UnexpectedResponseError):
        classify(200, b"<html>hello</html>")


def test_form_page_returned_for_post_is_not_a_bulletin(form_html):
    # the form page itself contains client-side alert() strings; they must not look like a notice
    with pytest.raises(ekap.UnexpectedResponseError):
        classify(200, form_html.encode("utf-8"))


def test_client_stops_on_403_without_retry(tmp_path):
    class Resp:
        status_code = 403
        headers = {}
        encoding = "utf-8"
        content = b"forbidden"

    class Sess:
        headers = {}
        calls = 0

        def request(self, *a, **k):
            Sess.calls += 1
            return Resp()

    rl = ekap.RateLimiter(tmp_path / "t.txt", clock=lambda: 1e9, sleep=lambda s: None)
    c = ekap.EkapClient(limiter=rl, session=Sess())
    with pytest.raises(ekap.BlockedError):
        c.load_form()
    assert Sess.calls == 1


def test_real_no_bulletin_response_fixture():
    # captured live: POST for a Sunday (15.11.2026) returns a normal page with this message
    from conftest import FIXTURES

    body = (FIXTURES / "no_bulletin_response.html").read_bytes()
    assert 'yayımlanmamıştır' in body.decode('utf-8')
    assert classify(200, body) == "no_bulletin"
