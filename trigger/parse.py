"""The boundary: raw GCN Kafka messages in, validated Alerts out.

Every check on notice content happens here. A topic or notice type the trigger does not act on
parses to None; a notice that claims to be one we act on but is malformed raises ParseError.
"""

import base64
import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Callable, NamedTuple, Optional

from . import sky
from .model import Alert, NoticeKind, Stream

SECONDS_PER_YEAR = 3.15576e7


class ParseError(ValueError):
    pass


class Notice(NamedTuple):
    alert: Alert
    prob_table: Optional[sky.ProbTable] = None   # GW maps only


def parse(topic: str, value: bytes, allow_test: bool = False) -> Optional[Alert]:
    notice = parse_notice(topic, value, allow_test)
    return None if notice is None else notice.alert


def parse_notice(topic: str, value: bytes, allow_test: bool = False) -> Optional[Notice]:
    parser = PARSERS.get(topic)
    if parser is None:
        return None
    try:
        return parser(topic, value, allow_test)
    except ParseError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, ET.ParseError) as e:
        raise ParseError(f"{topic}: {type(e).__name__}: {e}") from e


def _time(text: str) -> datetime:
    # Python 3.10's fromisoformat takes only 3 or 6 fractional digits; GCN sends 1 to 6.
    text = re.sub(r"\.(\d{1,6})\d*", lambda m: "." + m.group(1).ljust(6, "0"), text.strip().replace("Z", "+00:00"))
    t = datetime.fromisoformat(text)
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _ra_dec(ra, dec) -> tuple[float, float]:
    ra, dec = float(ra), float(dec)
    if not (0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0):
        raise ParseError(f"position out of range: ra {ra}, dec {dec}")
    return ra, dec


def _radius(r) -> float:
    r = float(r)
    if not (r > 0 and math.isfinite(r)):
        raise ParseError(f"bad error radius {r}")
    return r


GW_KINDS = {
    "EARLYWARNING": NoticeKind.PRELIMINARY,
    "PRELIMINARY": NoticeKind.PRELIMINARY,
    "INITIAL": NoticeKind.INITIAL,
    "UPDATE": NoticeKind.UPDATE,
    "RETRACTION": NoticeKind.RETRACTION,
}


def parse_gw(topic: str, value: bytes, allow_test: bool) -> Optional[Notice]:
    d = json.loads(value)
    event_id = d["superevent_id"]
    if event_id[:1] in ("M", "T") and not allow_test:
        return None
    kind = GW_KINDS[d["alert_type"]]
    if kind is NoticeKind.RETRACTION:
        return Notice(Alert(Stream.GW, "LVK", event_id, kind, _time(d["time_created"]), raw_topic=topic))

    event = d["event"]
    if event["group"] != "CBC":
        return None
    if event.get("search") == "MDC" and not allow_test:
        return None
    classification = event.get("classification") or {}
    properties = event.get("properties") or {}
    area90, distance, prob_table = sky.skymap_summary(base64.b64decode(event["skymap"]))
    alert = Alert(
        stream=Stream.GW,
        source="LVK",
        event_id=event_id,
        kind=kind,
        event_time=_time(event["time"]),
        area90_deg2=area90,
        distance_mpc=distance,
        far_per_year=float(event["far"]) * SECONDS_PER_YEAR,
        p_astro=1.0 - classification["Terrestrial"] if "Terrestrial" in classification else None,
        p_ns_merger=classification.get("BNS", 0.0) + classification.get("NSBH", 0.0) if classification else None,
        has_ns=properties.get("HasNS"),
        has_remnant=properties.get("HasRemnant"),
        significant=event.get("significant"),
        raw_topic=topic,
    )
    return Notice(alert, prob_table)


def _rayleigh_to_90(radius: float, containment: float) -> float:
    """Rescale a circular radius at `containment` to 90%, assuming a 2-D Gaussian error."""
    if math.isclose(containment, 0.9):
        return radius
    return radius * math.sqrt(math.log(10.0) / -math.log(1.0 - containment))


def parse_ep(topic: str, value: bytes, allow_test: bool) -> Optional[Notice]:
    d = json.loads(value)
    event_id = d["id"][0] if isinstance(d["id"], list) else d["id"]
    ra, dec = _ra_dec(d["ra"], d["dec"])
    err = d["ra_dec_error"]
    radius = _radius(err[0] if isinstance(err, list) else err)
    containment = float(d.get("containment_probability") or 0.9)
    alert = Alert(Stream.EP, "EP/WXT", str(event_id), NoticeKind.INITIAL, _time(d["trigger_time"]), ra, dec,
                  error_radius_deg=_rayleigh_to_90(radius, containment), raw_topic=topic)
    return Notice(alert)


ICECUBE_SOURCES = {"Gold Track Alert": "IceCube Gold", "Bronze Track Alert": "IceCube Bronze"}


def parse_icecube(topic: str, value: bytes, allow_test: bool) -> Optional[Notice]:
    d = json.loads(value)
    if d.get("alert_tense", "current") != "current":
        return None
    alert_type = d["alert_type"]
    if alert_type == "retraction":
        kind = NoticeKind.RETRACTION
    elif alert_type in ("initial", "update"):
        # The update notice is the one whose 90% radius includes systematics; that is what the rule waits for.
        kind = NoticeKind.UPDATE if d.get("systematic_included", alert_type == "update") else NoticeKind.INITIAL
    else:
        raise ParseError(f"unknown IceCube alert_type {alert_type!r}")
    source = ICECUBE_SOURCES.get(d["pipeline"])
    if source is None:
        return None
    event_id = d["event_name"][0] if isinstance(d["event_name"], list) else d["event_name"]
    event_time = _time(d["trigger_time"])
    if kind is NoticeKind.RETRACTION:
        return Notice(Alert(Stream.NEUTRINO, source, event_id, kind, event_time, raw_topic=topic))
    ra, dec = _ra_dec(d["ra"], d["dec"])
    radius = _radius(d["ra_dec_error"])
    p_astro = d.get("p_astro")
    alert = Alert(Stream.NEUTRINO, source, event_id, kind, event_time, ra, dec,
                  error_radius_deg=radius, area90_deg2=math.pi * radius ** 2,
                  p_astro=None if p_astro is None else float(p_astro), raw_topic=topic)
    return Notice(alert)


SVOM_PACKETS = {
    "eclairs-wakeup": (NoticeKind.INITIAL, "SVOM/ECLAIRs"),
    "eclairs-catalog": (NoticeKind.INITIAL, "SVOM/ECLAIRs"),
    "mxt-initial": (NoticeKind.INITIAL, "SVOM/MXT"),
    "mxt-update": (NoticeKind.UPDATE, "SVOM/MXT"),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(root: ET.Element, path: str) -> ET.Element:
    """Follow a slash path of local tag names, ignoring namespaces, descending at any depth per step."""
    node = root
    for name in path.split("/"):
        node = next((e for e in node.iter() if e is not node and _local(e.tag) == name), None)
        if node is None:
            raise ParseError(f"VOEvent has no {path}")
    return node


def _params(root: ET.Element) -> dict:
    return {e.get("name"): e.get("value") for e in root.iter() if _local(e.tag) == "Param"}


def parse_svom(topic: str, value: bytes, allow_test: bool) -> Optional[Notice]:
    root = ET.fromstring(value)
    if root.get("role", "observation") != "observation" and not allow_test:
        return None
    # The ivorn fragment is "<burst id>_<packet>", e.g. "sb25020504_mxt-initial_qf1".
    packet = root.get("ivorn", "").rsplit("#", 1)[-1].split("_", 1)[-1]
    match = next(((k, v) for k, v in SVOM_PACKETS.items() if packet.startswith(k)), None)
    if match is None:
        return None
    kind, source = match[1]
    params = _params(root)
    coords = _find(root, "WhereWhen/ObsDataLocation/ObservationLocation/AstroCoords")
    ra, dec = _ra_dec(_find(coords, "Position2D/Value2/C1").text, _find(coords, "Position2D/Value2/C2").text)
    radius = _radius(_find(coords, "Position2D/Error2Radius").text)
    inference = next((e for e in root.iter() if _local(e.tag) == "Inference"), None)
    p_astro = inference.get("probability") if inference is not None else None
    alert = Alert(Stream.GRB, source, params["Burst_Id"], kind, _time(_find(coords, "Time/TimeInstant/ISOTime").text),
                  ra, dec, error_radius_deg=radius, p_astro=None if p_astro is None else float(p_astro),
                  raw_topic=topic)
    return Notice(alert)


PARSERS: dict[str, Callable[[str, bytes, bool], Optional[Notice]]] = {
    "igwn.gwalert": parse_gw,
    "gcn.notices.einstein_probe.wxt.alert": parse_ep,
    "gcn.notices.icecube.gold_bronze_track_alerts": parse_icecube,
    "gcn.notices.svom.voevent.eclairs": parse_svom,
    "gcn.notices.svom.voevent.mxt": parse_svom,
}
TOPICS = tuple(PARSERS)
