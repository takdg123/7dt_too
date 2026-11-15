import json
import re
from datetime import datetime, timezone

import pytest

from trigger import request
from trigger.model import Action, Alert, NoticeKind, Stream, Visibility
from trigger.rules import decide

T0 = datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)
FORM_KEYS = {"requester", "target", "ra", "dec", "exposure", "imageCount", "obsmode", "comments",
             "abortObservation", "priority", "gain", "binning", "obsStartTime", "radius",
             "selectedFilters", "selectedTelNumber"}
# The validation regex the web form applies to sexagesimal input (TargetForm.js).
FORM_SEXAGESIMAL = re.compile(r"^-?\d{1,2}:\d{2}:\d{2}(\.\d+)?$")


class FakeSMTP:
    sent = []
    opened = 0

    def __init__(self, host, port, timeout=None):
        FakeSMTP.opened += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch, tmp_path):
    FakeSMTP.sent, FakeSMTP.opened = [], 0
    monkeypatch.setattr(request.smtplib, "SMTP", FakeSMTP)
    env = tmp_path / ".env"
    env.write_text("SDT_MAIL=bot@example.org\nSDT_PASSWORD=x\nSDT_SENDER=bot@example.org\n")
    monkeypatch.setattr(request, "MAIL_ENV_PATH", str(env))
    monkeypatch.delenv("TRIGGER_LIVE", raising=False)
    return FakeSMTP


def grb_alert():
    return Alert(Stream.GRB, "SVOM/MXT", "sb26011501", NoticeKind.INITIAL, T0, 50.4488, -10.0041, 0.05)


def nu_alert():
    return Alert(Stream.NEUTRINO, "IceCube Gold", "IceCube-260115A", NoticeKind.UPDATE, T0, 345.82, 9.01,
                 0.5, area90_deg2=0.79, p_astro=0.6)


def test_grb_payload_matches_the_form(monkeypatch):
    monkeypatch.setenv("TRIGGER_REQUESTER", "too-bot@example.org")
    decision = decide(grb_alert(), Visibility(0.0, 1.0))
    p = request.to_form_payload(grb_alert(), decision)
    assert set(p) == FORM_KEYS
    assert (p["ra"], p["dec"]) == ("03:21:47.71", "-10:00:14.8")
    assert FORM_SEXAGESIMAL.match(p["ra"]) and FORM_SEXAGESIMAL.match(p["dec"])
    assert p["requester"] == "too-bot@example.org"
    assert p["target"] == "sb26011501"
    assert (p["obsmode"], p["selectedFilters"], p["selectedTelNumber"]) == ("Deep", ["r"], 10)
    assert (p["exposure"], p["imageCount"]) == (60.0, 10)
    assert (p["abortObservation"], p["priority"], p["gain"], p["binning"], p["radius"], p["obsStartTime"]) == \
        (True, 100, 2750, 1, 0, "")
    assert p["comments"].startswith("[auto-trigger] grb-single-field: error 0.05 deg <= 0.4 deg")


def test_positive_dec_has_no_plus_sign():
    alert = nu_alert()
    p = request.to_form_payload(alert, decide(alert, Visibility(0.0, 1.0)))
    assert p["dec"] == "09:00:36.0"
    assert p["abortObservation"] is False


@pytest.mark.parametrize("ra_deg", [0.0, 359.99999, 180.0])
def test_ra_stays_within_the_forms_hour_range(ra_deg):
    alert = Alert(Stream.GRB, "SVOM/MXT", "sb1", NoticeKind.INITIAL, T0, ra_deg, -30.0, 0.05)
    ra = request.to_form_payload(alert, decide(alert, Visibility(0.0, 1.0)))["ra"]
    assert FORM_SEXAGESIMAL.match(ra) and int(ra.split(":")[0]) <= 23


def test_submit_refuses_in_shadow_mode(smtp):
    payload = request.to_form_payload(grb_alert(), decide(grb_alert(), Visibility(0.0, 1.0)))
    with pytest.raises(request.NotLive):
        request.submit(payload)
    assert smtp.opened == 0


def test_submit_in_live_mode_sends_what_send_email_sends(smtp, monkeypatch):
    monkeypatch.setenv("TRIGGER_LIVE", "1")
    payload = request.to_form_payload(grb_alert(), decide(grb_alert(), Visibility(0.0, 1.0)))
    request.submit(payload)
    (msg,) = smtp.sent
    assert msg["Subject"] == "[Automated] 7DT ToO Observation Request"
    assert msg["To"] == "7dt.observation.alert@gmail.com"
    (attachment,) = list(msg.iter_attachments())
    assert attachment.get_content_type() == "application/json"
    data = json.loads(attachment.get_content())
    assert (data["singleExposure"], data["exposure"], data["is_Too"], data["is_rapidToo"]) == (60.0, 600.0, True, True)
    assert "- Filters: r" in msg.get_body().get_content()


def test_notify_operators_is_a_no_op_without_recipients(smtp, monkeypatch):
    monkeypatch.setenv("TRIGGER_LIVE", "1")
    monkeypatch.delenv("TRIGGER_OPERATOR_EMAILS", raising=False)
    request.notify_operators(grb_alert(), decide(grb_alert(), Visibility(6.0, 1.0)))
    assert smtp.opened == 0


def test_notify_operators_mails_the_list(smtp, monkeypatch):
    monkeypatch.setenv("TRIGGER_LIVE", "1")
    monkeypatch.setenv("TRIGGER_OPERATOR_EMAILS", "a@example.org, b@example.org")
    decision = decide(grb_alert(), Visibility(6.0, 1.0))
    assert decision.action is Action.OPERATOR
    request.notify_operators(grb_alert(), decision)
    (msg,) = smtp.sent
    assert msg["To"] == "a@example.org, b@example.org"
    assert "grb-late-field" in msg["Subject"]
