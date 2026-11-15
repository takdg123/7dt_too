from datetime import datetime, timezone

import pytest

from trigger.model import Action, Alert, NoticeKind, Stream, Visibility
from trigger.rules import decide

T0 = datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)
UP_NOW = Visibility(0.0, 1.0)
NEVER = Visibility(None, 0.0)


def up_in(hours, fraction=1.0):
    return Visibility(hours, fraction)


def grb(radius=0.1, kind=NoticeKind.INITIAL):
    return Alert(Stream.GRB, "SVOM/ECLAIRs", "sb26011501", kind, T0, 50.0, 10.0, radius)


def ep(radius=0.05):
    return Alert(Stream.EP, "EP/WXT", "EP260115a", NoticeKind.INITIAL, T0, 50.0, 10.0, radius)


def nu(kind=NoticeKind.UPDATE, area=1.0, p_astro=0.6):
    return Alert(Stream.NEUTRINO, "IceCube Gold", "IceCube-260115A", kind, T0, 50.0, 10.0,
                 area90_deg2=area, p_astro=p_astro)


def gw(kind=NoticeKind.INITIAL, far=0.01, has_ns=0.9, area=50.0, distance=100.0):
    return Alert(Stream.GW, "LVK", "S260115a", kind, T0, area90_deg2=area, distance_mpc=distance,
                 far_per_year=far, has_ns=has_ns)


CASES = [
    ("retraction", grb(kind=NoticeKind.RETRACTION), UP_NOW, Action.IGNORE, "retraction", ""),
    ("gw retraction", gw(kind=NoticeKind.RETRACTION), UP_NOW, Action.IGNORE, "retraction", ""),

    ("grb fits, up now", grb(0.2), UP_NOW, Action.AUTO, "grb-single-field", ""),
    ("grb fits, up at 1.5 h", grb(0.4), up_in(1.5), Action.AUTO, "grb-single-field", ""),
    ("grb fits, up at 6 h", grb(0.2), up_in(6.0), Action.OPERATOR, "grb-late-field", ""),
    ("grb fits, up at 12 h", grb(0.2), up_in(12.0), Action.OPERATOR, "grb-late-field", ""),
    ("grb fits, up at 13 h", grb(0.2), up_in(13.0), Action.IGNORE, "grb-not-observable", ""),
    ("grb fits, never up", grb(0.2), NEVER, Action.IGNORE, "grb-not-observable", ""),
    ("grb too large", grb(0.5), UP_NOW, Action.IGNORE, "grb-error-too-large", ""),

    ("ep fits, up at 11 h", ep(0.05), up_in(11.0), Action.AUTO, "ep-single-field", ""),
    ("ep fits, up at 13 h", ep(0.05), up_in(13.0), Action.IGNORE, "ep-not-observable", ""),
    ("ep fits, never up", ep(0.05), NEVER, Action.IGNORE, "ep-not-observable", ""),
    ("ep too large", ep(0.6), UP_NOW, Action.IGNORE, "ep-error-too-large", ""),

    ("nu initial", nu(NoticeKind.INITIAL), UP_NOW, Action.IGNORE, "neutrino-wait-for-update", ""),
    ("nu one field", nu(area=1.2, p_astro=0.6), up_in(20.0), Action.AUTO, "neutrino-single-field", ""),
    ("nu small area, low p_astro", nu(area=1.0, p_astro=0.1), UP_NOW, Action.AUTO, "neutrino-single-field", ""),
    ("nu tiling", nu(area=15.0, p_astro=0.6), UP_NOW, Action.OPERATOR, "neutrino-tiling", ""),
    ("nu tiling, area < 10, low p", nu(area=8.0, p_astro=0.2), UP_NOW, Action.OPERATOR, "neutrino-tiling", ""),
    ("nu weak", nu(area=12.0, p_astro=0.3), UP_NOW, Action.IGNORE, "neutrino-weak", ""),
    ("nu weak, p unknown", nu(area=12.0, p_astro=None), UP_NOW, Action.IGNORE, "neutrino-weak", ""),
    ("nu area too large", nu(area=25.0, p_astro=0.9), UP_NOW, Action.IGNORE, "neutrino-area-too-large", ""),
    ("nu never up", nu(area=1.0, p_astro=0.9), NEVER, Action.IGNORE, "neutrino-not-observable", ""),
    ("nu up beyond 24 h", nu(area=1.0, p_astro=0.9), up_in(24.5), Action.IGNORE, "neutrino-not-observable", ""),

    ("gw preliminary", gw(NoticeKind.PRELIMINARY), UP_NOW, Action.IGNORE, "gw-wait-for-initial", ""),
    ("gw far too high", gw(far=2.0), UP_NOW, Action.IGNORE, "gw-far-too-high", ""),
    ("gw no ns", gw(has_ns=0.2), UP_NOW, Action.IGNORE, "gw-no-ns", ""),
    ("gw map never up", gw(), NEVER, Action.IGNORE, "gw-not-observable", ""),
    ("gw map barely up", gw(), up_in(2.0, 0.05), Action.IGNORE, "gw-not-observable", ""),
    ("gw far away", gw(distance=300.0), UP_NOW, Action.OPERATOR, "gw-deliberate", "deliberate"),
    ("gw huge area", gw(area=5000.0), UP_NOW, Action.OPERATOR, "gw-deliberate", "deliberate"),
    ("gw go deep", gw(area=50.0), up_in(3.0, 0.5), Action.OPERATOR, "gw-go-deep", "go-deep"),
    ("gw go wide", gw(area=400.0), UP_NOW, Action.OPERATOR, "gw-go-wide", "go-wide"),
    ("gw has_ns unknown", gw(has_ns=None), UP_NOW, Action.OPERATOR, "gw-go-deep", "go-deep"),
    ("gw distance unknown", gw(distance=None, area=150.0), UP_NOW, Action.OPERATOR, "gw-go-wide", "go-wide"),
]


@pytest.mark.parametrize("alert,vis,action,rule,tier", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_decide(alert, vis, action, rule, tier):
    d = decide(alert, vis)
    assert (d.action, d.rule, d.tier) == (action, rule, tier)
    assert d.reasons


def test_auto_and_operator_carry_a_plan_except_gw():
    assert decide(grb(0.1), UP_NOW).plan.filters == ("r",)
    assert decide(nu(area=15.0), UP_NOW).plan.epochs_nights == (0, 1, 7)
    assert decide(gw(), UP_NOW).plan is None


def test_reasons_quote_the_deciding_numbers():
    assert decide(grb(0.05), up_in(0.8)).reasons == ("error 0.05 deg <= 0.4 deg", "observable in 0.8 h")
    assert "FAR 2/yr > 1.0/yr" in decide(gw(far=2.0), UP_NOW).reasons
