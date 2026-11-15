"""The trigger policy: one pure function per alert stream, driven by the THRESHOLDS table.

Thresholds come from the November 2026 survey of Rubin, ZTF, GRANDMA, GECKO, LCO and the
Einstein Probe / IceCube follow-up literature, scaled to 7DT (1.27 deg2 per unit, about
19.5-20 AB in 3 min). Tune numbers here, not in the functions.
"""

from .model import Action, Alert, Decision, NoticeKind, Plan, Stream, Visibility

UNIT_FOV_DEG2 = 1.27
SINGLE_FIELD_RADIUS_DEG = 0.4     # a circle that fits inside one 0.92 x 1.38 deg field

THRESHOLDS = {
    Stream.GRB: {
        "max_error_radius_deg": SINGLE_FIELD_RADIUS_DEG,
        "auto_if_observable_within_h": 1.5,     # afterglows were caught at 0.06-1.6 h by 1 deg2-class networks
        "operator_if_observable_within_h": 12.0,
    },
    Stream.EP: {
        "max_error_radius_deg": SINGLE_FIELD_RADIUS_DEG,
        "auto_if_observable_within_h": 12.0,    # counterparts r > 20, fading > 0.5 mag/day
    },
    Stream.NEUTRINO: {
        "min_p_astro": 0.5,
        "or_max_area_deg2": 10.0,
        "max_area_deg2": 20.0,
        "auto_max_area_deg2": UNIT_FOV_DEG2,    # a single field is all one form request can describe
        "observable_within_h": 24.0,
    },
    Stream.GW: {
        "max_far_per_year": 1.0,
        "min_has_ns": 0.5,
        "max_distance_mpc": 200.0,              # AT2017gfo-like peak reaches 19.5 mag at about 100-130 Mpc
        "go_deep_max_area_deg2": 100.0,
        "go_wide_max_area_deg2": 1000.0,
        "min_observable_fraction": 0.1,
    },
}

PLANS = {
    "grb": Plan("Deep", ("r",), 60.0, 10, 10, (0, 1), "all units on the field, stack for depth"),
    "ep": Plan("Deep", ("r",), 100.0, 6, 10, (0, 1), "stack to about 21.5; second night checks fading"),
    "neutrino": Plan("Deep", ("g", "r"), 100.0, 3, 10, (0, 1, 7), "ZTF/Rubin cadence: nights 0, 1, 7"),
}


def decide(alert: Alert, vis: Visibility) -> Decision:
    """Route by stream. A retraction always yields IGNORE with rule "retraction"."""
    raise NotImplementedError


def decide_grb(alert: Alert, vis: Visibility) -> Decision:
    """AUTO when the error circle fits one field and the field is up within 1.5 h; OPERATOR when it is up
    within 12 h; IGNORE otherwise (too large an error circle, or not observable)."""
    raise NotImplementedError


def decide_ep(alert: Alert, vis: Visibility) -> Decision:
    """AUTO when the WXT circle fits one field and the field is up within 12 h; IGNORE otherwise."""
    raise NotImplementedError


def decide_neutrino(alert: Alert, vis: Visibility) -> Decision:
    """Act only on the update that includes systematics (kind UPDATE); an INITIAL notice is IGNORE with
    rule "neutrino-wait-for-update". Pass when p_astro >= 0.5 or area < 10 deg2, and area <= 20 deg2,
    and observable within 24 h. AUTO when the area fits one field, OPERATOR when it needs tiling."""
    raise NotImplementedError


def decide_gw(alert: Alert, vis: Visibility) -> Decision:
    """Never AUTO: a GW map needs a tiling plan a single form request cannot carry.
    PRELIMINARY is IGNORE ("gw-wait-for-initial"). FAR > 1/yr, has_ns < 0.5 (when known) or the map being
    unobservable is IGNORE. Distance > 200 Mpc or area > 1000 deg2 with a passing FAR and has_ns is
    OPERATOR tier "deliberate". Otherwise OPERATOR tier "go-deep" (area < 100) or "go-wide"."""
    raise NotImplementedError
