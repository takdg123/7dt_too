import json
from datetime import datetime, timezone

import pytest

from trigger import listener, request

ECLAIRS = "gcn.notices.svom.voevent.eclairs"
MXT = "gcn.notices.svom.voevent.mxt"
GW = "igwn.gwalert"
# The ECLAIRs fixture position (RA 50.4, Dec +10.0) is 44 deg up in full darkness at this time.
NOV_NIGHT = datetime(2026, 11, 15, 3, 0, tzinfo=timezone.utc)
JAN_NIGHT = datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)


class FakeSMTP:
    sent = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, *a):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def env(monkeypatch, tmp_path):
    FakeSMTP.sent = []
    monkeypatch.setattr(request.smtplib, "SMTP", FakeSMTP)
    dotenv = tmp_path / ".env"
    dotenv.write_text("SDT_MAIL=bot@example.org\nSDT_PASSWORD=x\nSDT_SENDER=bot@example.org\n")
    monkeypatch.setattr(request, "MAIL_ENV_PATH", str(dotenv))
    monkeypatch.setenv("TRIGGER_LOG", str(tmp_path / "decisions.jsonl"))
    monkeypatch.delenv("TRIGGER_LIVE", raising=False)
    monkeypatch.setenv("TRIGGER_OPERATOR_EMAILS", "ops@example.org")
    return tmp_path


def log_lines(env):
    return [json.loads(line) for line in (env / "decisions.jsonl").read_text().splitlines()]


def test_shadow_mode_logs_auto_and_sends_nothing(env, fixture_bytes):
    record = listener.handle(ECLAIRS, fixture_bytes("svom_eclairs_wakeup.xml"), now=NOV_NIGHT)
    assert (record["mode"], record["decision"]["action"], record["effect"]) == ("shadow", "auto", "would-submit")
    assert record["payload"]["target"] == "sbYYMMDDnn"
    assert log_lines(env) == [record]
    assert FakeSMTP.sent == []


def test_live_mode_submits_auto(env, fixture_bytes, monkeypatch):
    monkeypatch.setenv("TRIGGER_LIVE", "1")
    record = listener.handle(ECLAIRS, fixture_bytes("svom_eclairs_wakeup.xml"), now=NOV_NIGHT)
    assert record["effect"] == "submitted"
    assert [m["To"] for m in FakeSMTP.sent] == ["7dt.observation.alert@gmail.com"]


def test_repeated_notice_is_a_duplicate_and_submitted_once(env, fixture_bytes, monkeypatch):
    monkeypatch.setenv("TRIGGER_LIVE", "1")
    value = fixture_bytes("svom_eclairs_wakeup.xml")
    first = listener.handle(ECLAIRS, value, now=NOV_NIGHT)
    second = listener.handle(ECLAIRS, value, now=NOV_NIGHT)
    assert (first["status"], second["status"]) == ("decided", "duplicate")
    assert len(FakeSMTP.sent) == 1
    assert [r["status"] for r in log_lines(env)] == ["decided", "duplicate"]


def test_mxt_after_eclairs_is_decided_but_not_resubmitted(env, fixture_bytes, monkeypatch):
    monkeypatch.setenv("TRIGGER_LIVE", "1")
    eclairs = fixture_bytes("svom_eclairs_wakeup.xml")
    mxt = eclairs.replace(b"_eclairs-wakeup", b"_mxt-initial_qf1")
    listener.handle(ECLAIRS, eclairs, now=NOV_NIGHT)
    record = listener.handle(MXT, mxt, now=NOV_NIGHT)
    assert (record["status"], record["decision"]["action"], record["effect"]) == ("decided", "auto", "already-submitted")
    assert len(FakeSMTP.sent) == 1


def test_gw_is_operator_and_notified_only_live(env, fixture_bytes, monkeypatch):
    shadow = listener.handle(GW, fixture_bytes("gw_initial.json"), now=JAN_NIGHT)
    assert (shadow["decision"]["action"], shadow["decision"]["tier"], shadow["effect"]) == \
        ("operator", "go-deep", "would-notify")
    assert FakeSMTP.sent == []
    monkeypatch.setenv("TRIGGER_LIVE", "1")
    update = json.loads(fixture_bytes("gw_initial.json"))
    update["alert_type"] = "UPDATE"
    live = listener.handle(GW, json.dumps(update).encode(), now=JAN_NIGHT)
    assert live["effect"] == "notified"
    assert [m["To"] for m in FakeSMTP.sent] == ["ops@example.org"]


def test_ignored_and_malformed_notices_are_logged(env, fixture_bytes):
    assert listener.handle(ECLAIRS, fixture_bytes("svom_grm_trigger.xml"))["status"] == "skipped"
    assert listener.handle(ECLAIRS, b"<VOEvent")["status"] == "error"
    assert [r["status"] for r in log_lines(env)] == ["skipped", "error"]


def test_missing_credentials_exit_2(monkeypatch, capsys):
    monkeypatch.delenv("GCN_CLIENT_ID", raising=False)
    monkeypatch.delenv("GCN_CLIENT_SECRET", raising=False)
    assert listener.main([]) == 2
    assert "GCN_CLIENT_ID" in capsys.readouterr().err
