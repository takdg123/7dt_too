from datetime import datetime, timezone

import astropy.units as u
import pytest
from astropy.coordinates import AltAz, SkyCoord, get_body
from astropy.time import Time

from trigger import sky
from trigger.parse import parse_notice

NIGHT = datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)    # local midnight at El Sauce
NOON = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


def zenith_ra(when):
    return Time(when).sidereal_time("apparent", longitude=sky.EL_SAUCE.lon).deg


def test_point_at_zenith_at_night_is_observable_now():
    assert sky.visibility_point(zenith_ra(NIGHT), -30.47, NIGHT) == sky.Visibility(0.0, 1.0)


def test_far_northern_point_is_never_observable():
    assert sky.visibility_point(0.0, 80.0, NIGHT) == sky.Visibility(None, 0.0)


def test_point_near_the_sun_is_never_observable():
    assert sky.visibility_point(zenith_ra(NOON), -21.0, NOON) == sky.Visibility(None, 0.0)


def test_point_at_noon_waits_for_night_and_altitude():
    ra = (zenith_ra(NOON) + 180.0) % 360.0
    vis = sky.visibility_point(ra, -30.0, NOON)
    assert 5.0 < vis.hours_until_observable < 24.0
    when = Time(NOON) + vis.hours_until_observable * u.hour
    frame = AltAz(obstime=when, location=sky.EL_SAUCE)
    assert get_body("sun", when, sky.EL_SAUCE).transform_to(frame).alt.deg < -18.0
    assert SkyCoord(ra * u.deg, -30.0 * u.deg).transform_to(frame).alt.deg > 30.0
    earlier = Time(NOON) + (vis.hours_until_observable - 1 / 6) * u.hour
    frame = AltAz(obstime=earlier, location=sky.EL_SAUCE)
    sun_dark = get_body("sun", earlier, sky.EL_SAUCE).transform_to(frame).alt.deg < -18.0
    target_up = SkyCoord(ra * u.deg, -30.0 * u.deg).transform_to(frame).alt.deg > 30.0
    assert not (sun_dark and target_up)


def test_map_visibility(fixture_bytes):
    table = parse_notice("igwn.gwalert", fixture_bytes("gw_initial.json")).prob_table
    up = sky.visibility_map(table, NIGHT)
    assert up.hours_until_observable == 0.0
    assert up.observable_fraction == pytest.approx(1.0)
    north = sky.ProbTable(table.ra_deg, table.dec_deg * 0 + 80.0, table.prob)
    assert sky.visibility_map(north, NIGHT) == sky.Visibility(None, 0.0)
