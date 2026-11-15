import json
from datetime import datetime, timezone

import pytest

from trigger.model import NoticeKind, Stream
from trigger.parse import ParseError, parse, parse_notice

GW = "igwn.gwalert"
EP = "gcn.notices.einstein_probe.wxt.alert"
ICECUBE = "gcn.notices.icecube.gold_bronze_track_alerts"
ECLAIRS = "gcn.notices.svom.voevent.eclairs"
MXT = "gcn.notices.svom.voevent.mxt"


def gw_variant(fixture_bytes, **top):
    d = json.loads(fixture_bytes("gw_initial.json"))
    event = top.pop("event", {})
    d.update(top)
    if event is None:
        d["event"] = None
    else:
        d["event"].update(event)
    return json.dumps(d).encode()


def test_gw_initial(fixture_bytes):
    notice = parse_notice(GW, fixture_bytes("gw_initial.json"))
    a = notice.alert
    assert (a.stream, a.source, a.event_id, a.kind) == (Stream.GW, "LVK", "S260115a", NoticeKind.INITIAL)
    assert a.event_time == datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)
    assert a.far_per_year == pytest.approx(1e-9 * 3.15576e7)
    assert a.p_ns_merger == pytest.approx(0.95)
    assert a.p_astro == pytest.approx(0.95)
    assert (a.has_ns, a.has_remnant, a.significant) == (0.99, 0.9, True)
    assert a.area90_deg2 == pytest.approx(90.4, rel=0.05)   # Gaussian sigma 2.5 deg: 2 pi sigma^2 ln 10
    assert a.distance_mpc == 100.0
    assert notice.prob_table.prob.sum() == pytest.approx(0.9, abs=0.01)


def test_gw_earlywarning_is_preliminary(fixture_bytes):
    assert parse(GW, gw_variant(fixture_bytes, alert_type="EARLYWARNING")).kind is NoticeKind.PRELIMINARY


def test_gw_retraction(fixture_bytes):
    a = parse(GW, gw_variant(fixture_bytes, alert_type="RETRACTION", event=None))
    assert (a.kind, a.event_id) == (NoticeKind.RETRACTION, "S260115a")
    assert a.event_time == datetime(2026, 1, 15, 3, 5, tzinfo=timezone.utc)


@pytest.mark.parametrize("change", [
    {"event": {"group": "Burst"}},
    {"event": {"search": "MDC"}},
    {"superevent_id": "MS260115a"},
    {"superevent_id": "TS260115a"},
], ids=["burst", "mdc", "mock", "test"])
def test_gw_ignored(fixture_bytes, change):
    assert parse(GW, gw_variant(fixture_bytes, **change)) is None


def test_gw_mock_allowed_for_replay(fixture_bytes):
    assert parse(GW, gw_variant(fixture_bytes, superevent_id="MS260115a"), allow_test=True).event_id == "MS260115a"


def test_ep(fixture_bytes):
    a = parse(EP, fixture_bytes("ep_wxt_alert.json"))
    assert (a.stream, a.source, a.event_id, a.kind) == (Stream.EP, "EP/WXT", "01708973486", NoticeKind.INITIAL)
    assert a.event_time == datetime(2024, 3, 1, 21, 46, 5, 130000, tzinfo=timezone.utc)
    assert (a.ra_deg, a.dec_deg, a.error_radius_deg) == (120.0, 40.0, 0.02)


def test_ep_ellipse_uses_semi_major(fixture_bytes):
    d = json.loads(fixture_bytes("ep_wxt_alert.json"))
    d.update(id="EP260115a", ra_dec_error=[0.05, 0.03, 40.0])
    a = parse(EP, json.dumps(d).encode())
    assert (a.event_id, a.error_radius_deg) == ("EP260115a", 0.05)


def test_icecube_initial_and_update(fixture_bytes):
    initial = parse(ICECUBE, fixture_bytes("icecube_bronze_initial.json"))
    update = parse(ICECUBE, fixture_bytes("icecube_bronze_update.json"))
    assert (initial.source, initial.event_id, initial.kind) == ("IceCube Bronze", "IceCube-230416A", NoticeKind.INITIAL)
    assert update.kind is NoticeKind.UPDATE
    assert update.area90_deg2 == pytest.approx(3.14159 * 0.6 ** 2, rel=1e-4)
    assert update.p_astro == pytest.approx(0.34064)


def test_icecube_retraction_and_tense(fixture_bytes):
    d = json.loads(fixture_bytes("icecube_bronze_initial.json"))
    assert parse(ICECUBE, json.dumps(dict(d, alert_type="retraction")).encode()).kind is NoticeKind.RETRACTION
    assert parse(ICECUBE, json.dumps(dict(d, alert_tense="test")).encode()) is None
    assert parse(ICECUBE, json.dumps(dict(d, pipeline="Gold Track Alert")).encode()).source == "IceCube Gold"


def test_svom_eclairs_wakeup(fixture_bytes):
    a = parse(ECLAIRS, fixture_bytes("svom_eclairs_wakeup.xml"))
    assert (a.stream, a.source, a.event_id, a.kind) == (Stream.GRB, "SVOM/ECLAIRs", "sbYYMMDDnn", NoticeKind.INITIAL)
    assert (a.ra_deg, a.dec_deg, a.error_radius_deg, a.p_astro) == (50.4488, 10.0041, 0.2, 0.7)
    assert a.event_time == datetime(2022, 4, 4, 11, 54, 30, 200000, tzinfo=timezone.utc)


def test_svom_mxt(fixture_bytes):
    initial = parse(MXT, fixture_bytes("svom_mxt_initial.xml"))
    update = parse(MXT, fixture_bytes("svom_mxt_update.xml"))
    assert (initial.source, initial.event_id, initial.kind) == ("SVOM/MXT", "sb25020504", NoticeKind.INITIAL)
    assert (initial.ra_deg, initial.dec_deg, initial.error_radius_deg) == (113.498, 32.3892, 0.0356)
    assert update.kind is NoticeKind.UPDATE


def test_svom_catalog_is_initial(fixture_bytes):
    xml = fixture_bytes("svom_eclairs_wakeup.xml").replace(b"_eclairs-wakeup", b"_eclairs-catalog")
    assert parse(ECLAIRS, xml).kind is NoticeKind.INITIAL


@pytest.mark.parametrize("topic,name,old,new", [
    (ECLAIRS, "svom_grm_trigger.xml", b"", b""),
    (ECLAIRS, "svom_eclairs_wakeup.xml", b"_eclairs-wakeup", b"_slewing"),
    (ECLAIRS, "svom_eclairs_wakeup.xml", b"_eclairs-wakeup", b"_not-slewing"),
    (ECLAIRS, "svom_eclairs_wakeup.xml", b'role="observation"', b'role="test"'),
    ("gcn.notices.fermi.gbm.alert", "ep_wxt_alert.json", b"", b""),
    ("gcn.notices.swift.bat.guano", "ep_wxt_alert.json", b"", b""),
], ids=["grm", "slewing", "not-slewing", "test-role", "fermi-topic", "swift-topic"])
def test_ignored_notices(fixture_bytes, topic, name, old, new):
    value = fixture_bytes(name).replace(old, new) if old else fixture_bytes(name)
    assert parse(topic, value) is None


@pytest.mark.parametrize("topic,value", [
    (EP, b"{not json"),
    (EP, b'{"id": "x", "trigger_time": "2024-03-01T00:00:00Z", "ra": 400, "dec": 0, "ra_dec_error": 0.1}'),
    (ICECUBE, b'{"alert_type": "initial", "pipeline": "Gold Track Alert"}'),
    (ECLAIRS, b"<VOEvent"),
], ids=["bad-json", "ra-out-of-range", "missing-keys", "bad-xml"])
def test_malformed_raises_parse_error(topic, value):
    with pytest.raises(ParseError):
        parse(topic, value)
