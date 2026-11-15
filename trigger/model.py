"""Domain types for the 7DT automatic ToO trigger.

An Alert is what a GCN notice says, already parsed and in fixed units. Visibility is what the
sky allows from El Sauce. A Decision is what 7DT should do about it. Everything between the
parsers and the request writer works only with these types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Stream(Enum):
    GW = "gw"
    GRB = "grb"
    EP = "ep"
    NEUTRINO = "neutrino"


class NoticeKind(Enum):
    PRELIMINARY = "preliminary"
    INITIAL = "initial"
    UPDATE = "update"
    RETRACTION = "retraction"


class Action(Enum):
    AUTO = "auto"          # submit the ToO request without a human
    OPERATOR = "operator"  # notify operators with a recommended plan; a human submits
    IGNORE = "ignore"


@dataclass(frozen=True)
class Alert:
    stream: Stream
    source: str                       # instrument or pipeline, e.g. "SVOM/ECLAIRs", "EP/WXT", "IceCube Gold"
    event_id: str
    kind: NoticeKind
    event_time: datetime              # UTC, aware
    ra_deg: Optional[float] = None    # point-like localizations only
    dec_deg: Optional[float] = None
    error_radius_deg: Optional[float] = None  # 90% containment radius
    area90_deg2: Optional[float] = None       # 90% credible area; derived from the radius when absent
    distance_mpc: Optional[float] = None
    far_per_year: Optional[float] = None
    p_astro: Optional[float] = None           # IceCube signalness, GW 1 - p(Terrestrial), SVOM inference probability
    p_ns_merger: Optional[float] = None       # GW p(BNS) + p(NSBH)
    has_ns: Optional[float] = None
    has_remnant: Optional[float] = None
    significant: Optional[bool] = None
    raw_topic: str = ""


@dataclass(frozen=True)
class Visibility:
    """How much of the localization El Sauce can observe, and how soon."""

    hours_until_observable: Optional[float]  # None: not observable in the next 24 h
    observable_fraction: float                # 90% probability observable tonight (1.0 or 0.0 for a point)


@dataclass(frozen=True)
class Plan:
    obsmode: str                  # "Deep" (one filter set on N units) or "Spec" (medium-band set)
    filters: tuple                # Deep mode filters, e.g. ("r",)
    exposure_s: float             # single exposure
    image_count: int
    n_telescopes: int
    epochs_nights: tuple = (0,)   # nights after the alert on which to repeat
    note: str = ""


@dataclass(frozen=True)
class Decision:
    action: Action
    rule: str                     # name of the rule that decided, e.g. "grb-single-field"
    reasons: tuple                # human-readable facts behind the decision
    plan: Optional[Plan] = None
    tier: str = ""                # GW tier: "go-deep", "go-wide", "deliberate"
    extra: dict = field(default_factory=dict)
