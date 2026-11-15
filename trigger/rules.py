"""The trigger policy: one pure function per alert stream, driven by the THRESHOLDS table.

Thresholds come from the November 2026 survey of Rubin, ZTF, GRANDMA, GECKO, LCO and the
Einstein Probe / IceCube follow-up literature, scaled to 7DT (1.27 deg2 per unit, about
19.5-20 AB in 3 min). Tune numbers here, not in the functions.
"""

import math

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




def _observable_in(vis: Visibility) -> str:
    if vis.hours_until_observable is None:
        return "not observable in the next 24 h"
    return f"observable in {vis.hours_until_observable:.1f} h"


def _within(vis: Visibility, hours: float) -> bool:
    return vis.hours_until_observable is not None and vis.hours_until_observable <= hours


def _area90(alert: Alert) -> float:
    if alert.area90_deg2 is not None:
        return alert.area90_deg2
    return math.pi * alert.error_radius_deg ** 2


def decide(alert: Alert, vis: Visibility) -> Decision:
    """Route by stream. A retraction always yields IGNORE with rule "retraction"."""
    if alert.kind is NoticeKind.RETRACTION:
        return Decision(Action.IGNORE, "retraction", (f"{alert.source} retracted {alert.event_id}",))
    return DECIDERS[alert.stream](alert, vis)


def decide_grb(alert: Alert, vis: Visibility) -> Decision:
    """AUTO when the error circle fits one field and the field is up within 1.5 h; OPERATOR when it is up
    within 12 h; IGNORE otherwise (too large an error circle, or not observable)."""
    t = THRESHOLDS[Stream.GRB]
    r = alert.error_radius_deg
    if r > t["max_error_radius_deg"]:
        return Decision(Action.IGNORE, "grb-error-too-large", (f"error {r:.3g} deg > {t['max_error_radius_deg']} deg",))
    fits = f"error {r:.3g} deg <= {t['max_error_radius_deg']} deg"
    if _within(vis, t["auto_if_observable_within_h"]):
        return Decision(Action.AUTO, "grb-single-field", (fits, _observable_in(vis)), PLANS["grb"])
    if _within(vis, t["operator_if_observable_within_h"]):
        return Decision(Action.OPERATOR, "grb-late-field", (fits, _observable_in(vis)), PLANS["grb"])
    return Decision(Action.IGNORE, "grb-not-observable",
                    (fits, f"{_observable_in(vis)} (limit {t['operator_if_observable_within_h']} h)"))


def decide_ep(alert: Alert, vis: Visibility) -> Decision:
    """AUTO when the WXT circle fits one field and the field is up within 12 h; IGNORE otherwise."""
    t = THRESHOLDS[Stream.EP]
    r = alert.error_radius_deg
    if r > t["max_error_radius_deg"]:
        return Decision(Action.IGNORE, "ep-error-too-large", (f"error {r:.3g} deg > {t['max_error_radius_deg']} deg",))
    fits = f"error {r:.3g} deg <= {t['max_error_radius_deg']} deg"
    if _within(vis, t["auto_if_observable_within_h"]):
        return Decision(Action.AUTO, "ep-single-field", (fits, _observable_in(vis)), PLANS["ep"])
    return Decision(Action.IGNORE, "ep-not-observable",
                    (fits, f"{_observable_in(vis)} (limit {t['auto_if_observable_within_h']} h)"))


def decide_neutrino(alert: Alert, vis: Visibility) -> Decision:
    """Act only on the update that includes systematics (kind UPDATE); an INITIAL notice is IGNORE with
    rule "neutrino-wait-for-update". Pass when p_astro >= 0.5 or area < 10 deg2, and area <= 20 deg2,
    and observable within 24 h. AUTO when the area fits one field, OPERATOR when it needs tiling."""
    t = THRESHOLDS[Stream.NEUTRINO]
    if alert.kind is not NoticeKind.UPDATE:
        return Decision(Action.IGNORE, "neutrino-wait-for-update",
                        (f"{alert.kind.value} notice has no systematics",))
    area = _area90(alert)
    p = alert.p_astro
    p_text = "p_astro unknown" if p is None else f"p_astro {p:.2f}"
    if not ((p is not None and p >= t["min_p_astro"]) or area < t["or_max_area_deg2"]):
        return Decision(Action.IGNORE, "neutrino-weak",
                        (f"{p_text} < {t['min_p_astro']}", f"area {area:.3g} deg2 >= {t['or_max_area_deg2']} deg2"))
    if area > t["max_area_deg2"]:
        return Decision(Action.IGNORE, "neutrino-area-too-large", (f"area {area:.3g} deg2 > {t['max_area_deg2']} deg2",))
    if not _within(vis, t["observable_within_h"]):
        return Decision(Action.IGNORE, "neutrino-not-observable", (_observable_in(vis),))
    reasons = (p_text, f"area {area:.3g} deg2", _observable_in(vis))
    if area <= t["auto_max_area_deg2"]:
        return Decision(Action.AUTO, "neutrino-single-field",
                        reasons + (f"area <= {t['auto_max_area_deg2']} deg2 fits one field",), PLANS["neutrino"])
    return Decision(Action.OPERATOR, "neutrino-tiling",
                    reasons + (f"area > {t['auto_max_area_deg2']} deg2 needs tiling",), PLANS["neutrino"])


def decide_gw(alert: Alert, vis: Visibility) -> Decision:
    """Never AUTO: a GW map needs a tiling plan a single form request cannot carry.
    PRELIMINARY is IGNORE ("gw-wait-for-initial"). FAR > 1/yr, has_ns < 0.5 (when known) or the map being
    unobservable is IGNORE. Distance > 200 Mpc or area > 1000 deg2 with a passing FAR and has_ns is
    OPERATOR tier "deliberate". Otherwise OPERATOR tier "go-deep" (area < 100) or "go-wide"."""
    t = THRESHOLDS[Stream.GW]
    if alert.kind is NoticeKind.PRELIMINARY:
        return Decision(Action.IGNORE, "gw-wait-for-initial", ("preliminary notice",))
    if alert.far_per_year > t["max_far_per_year"]:
        return Decision(Action.IGNORE, "gw-far-too-high",
                        (f"FAR {alert.far_per_year:.3g}/yr > {t['max_far_per_year']}/yr",))
    if alert.has_ns is not None and alert.has_ns < t["min_has_ns"]:
        return Decision(Action.IGNORE, "gw-no-ns", (f"HasNS {alert.has_ns:.2f} < {t['min_has_ns']}",))
    observable = f"{vis.observable_fraction:.0%} of the 90% area observable, {_observable_in(vis)}"
    if vis.hours_until_observable is None or vis.observable_fraction < t["min_observable_fraction"]:
        return Decision(Action.IGNORE, "gw-not-observable",
                        (f"{observable} (min {t['min_observable_fraction']:.0%})",))
    area = alert.area90_deg2
    reasons = (
        f"FAR {alert.far_per_year:.3g}/yr",
        "HasNS unknown" if alert.has_ns is None else f"HasNS {alert.has_ns:.2f}",
        f"area90 {area:.0f} deg2",
        "distance unknown" if alert.distance_mpc is None else f"distance {alert.distance_mpc:.0f} Mpc",
        observable,
    )
    far_away = alert.distance_mpc is not None and alert.distance_mpc > t["max_distance_mpc"]
    if far_away or area > t["go_wide_max_area_deg2"]:
        return Decision(Action.OPERATOR, "gw-deliberate", reasons, tier="deliberate")
    if area < t["go_deep_max_area_deg2"]:
        return Decision(Action.OPERATOR, "gw-go-deep", reasons, tier="go-deep")
    return Decision(Action.OPERATOR, "gw-go-wide", reasons, tier="go-wide")


DECIDERS = {
    Stream.GRB: decide_grb,
    Stream.EP: decide_ep,
    Stream.NEUTRINO: decide_neutrino,
    Stream.GW: decide_gw,
}
