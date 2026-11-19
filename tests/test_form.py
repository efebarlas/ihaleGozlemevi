from datetime import date

import pytest

from ihale import ekap


def test_hidden_fields_extracted(form_html):
    info = ekap.parse_form(form_html)
    for name in ("__VIEWSTATE", "__EVENTVALIDATION", "__PIT", "__PITC"):
        assert name in info.hidden
    assert info.hidden["__EVENTVALIDATION"].startswith("/wEd")


def test_form_controls_present(form_html):
    info = ekap.parse_form(form_html)
    assert ekap.TYPE_FIELD in info.names
    assert ekap.DATE_FIELD in info.names
    options = dict(info.selects[ekap.TYPE_FIELD])
    assert options["1"] == "Mal" and options["2"] == "Yapım"
    assert options["3"] == "Hizmet" and options["4"] == "Danışmanlık"


def test_postback_payload(form_html):
    info = ekap.parse_form(form_html)
    data = ekap.build_postback(info, "hizmet", date(2026, 11, 18))
    assert data[ekap.TYPE_FIELD] == "3"
    assert data[ekap.DATE_FIELD] == "18.11.2026"
    assert data["__EVENTTARGET"] == "ctl00$ContentPlaceHolder1$btnYukle"
    assert data["__EVENTARGUMENT"] == ""
    assert data["__EVENTVALIDATION"] == info.hidden["__EVENTVALIDATION"]


def test_changed_form_detected(form_html):
    with pytest.raises(ekap.FormChangedError):
        ekap.parse_form(form_html.replace("ddlstBxIhaleTur", "ddlRenamed"))
    with pytest.raises(ekap.FormChangedError):
        ekap.parse_form(form_html.replace("__VIEWSTATE", "__VS"))
