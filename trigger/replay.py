"""Replay real O4 superevents and the notice fixtures through listener.handle, in shadow mode.

Each GW superevent becomes the igwn.gwalert INITIAL notice it would have produced, built from
GraceDB's public superevent record, its current bayestar.multiorder.fits, em_bright.json and the
preferred pipeline's p_astro.json. Visibility is evaluated 10 min after the event.

    python -m trigger.replay
"""

import base64
import json
import os
import urllib.request
from datetime import timedelta
from pathlib import Path

from astropy.time import Time

from . import listener
from .parse import parse, parse_time

CACHE = Path("/home/7dt/too_recovery/replay_cache")
GRACEDB = "https://gracedb.ligo.org/api/superevents"
SUPEREVENTS = [
    ("S250206dm", "BNS/NSBH candidate 7DT observed"),
    ("S240422ed", "NSBH, later downgraded"),
    ("S230518h", "NSBH"),
    ("S230529ay", "NSBH, poorly localized"),
    ("S230627c", "NSBH/BBH ambiguous"),
    ("S231113bw", "low-significance NSBH"),
    ("S230628ax", "plain BBH, p(BBH) 0.99998"),
]
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
FIXTURE_NOTICES = [
    ("gcn.notices.einstein_probe.wxt.alert", "ep_wxt_alert.json"),
    ("gcn.notices.icecube.gold_bronze_track_alerts", "icecube_bronze_initial.json"),
    ("gcn.notices.icecube.gold_bronze_track_alerts", "icecube_bronze_update.json"),
    ("gcn.notices.svom.voevent.eclairs", "svom_eclairs_wakeup.xml"),
    ("gcn.notices.svom.voevent.mxt", "svom_mxt_initial.xml"),
    ("gcn.notices.svom.voevent.mxt", "svom_mxt_update.xml"),
    ("gcn.notices.svom.voevent.eclairs", "svom_grm_trigger.xml"),
]
SECONDS_PER_MONTH = 3.15576e7 / 12


def _fetch(url: str, cache_name: str) -> bytes:
    path = CACHE / cache_name
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "too-trigger-replay"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return path.read_bytes()


def gw_notice(superevent_id: str) -> bytes:
    meta = json.loads(_fetch(f"{GRACEDB}/{superevent_id}/", f"{superevent_id}.json"))
    files = json.loads(_fetch(f"{GRACEDB}/{superevent_id}/files/", f"{superevent_id}.files.json"))
    preferred = meta["preferred_event_data"]
    p_astro_name = f"{preferred['pipeline'].lower()}.p_astro.json"
    if p_astro_name not in files:
        p_astro_name = next(n for n in sorted(files) if n.endswith(".p_astro.json") and "RapidPE" not in n)

    def file(name):
        return _fetch(files[name], f"{superevent_id}.{name}")

    notice = {
        "superevent_id": superevent_id,
        "alert_type": "INITIAL",
        "time_created": meta["created"].replace(" UTC", "Z").replace(" ", "T"),
        "event": {
            "time": Time(meta["t_0"], format="gps").utc.isot + "Z",
            "far": meta["far"],
            "significant": meta["far"] < 1 / SECONDS_PER_MONTH,
            "group": preferred["group"],
            "pipeline": preferred["pipeline"],
            "search": preferred["search"],
            "classification": json.loads(file(p_astro_name)),
            "properties": json.loads(file("em_bright.json")),
            "skymap": base64.b64encode(file("bayestar.multiorder.fits")).decode(),
        },
    }
    return json.dumps(notice).encode()


def _row(label: str, record: dict) -> list[str]:
    alert = record.get("alert") or {}
    vis = record.get("visibility") or {}
    decision = record.get("decision") or {}

    def num(v, fmt):
        return "" if v is None else format(v, fmt)

    return [
        label,
        num(alert.get("far_per_year"), ".2g"),
        num(alert.get("has_ns"), ".2f"),
        num(alert.get("area90_deg2") or (alert.get("error_radius_deg") and 3.14159 * alert["error_radius_deg"] ** 2),
            ".3g"),
        num(alert.get("distance_mpc"), ".0f"),
        num(vis.get("observable_fraction"), ".2f"),
        num(vis.get("hours_until_observable"), ".1f"),
        decision.get("action", record["status"]),
        decision.get("tier", ""),
        decision.get("rule", ""),
    ]


def _print_table(rows: list[list[str]]) -> None:
    header = ["event", "FAR/yr", "has_ns", "area90", "dist Mpc", "obs frac", "obs in h", "action", "tier", "rule"]
    widths = [max(len(str(r[i])) for r in [header] + rows) for i in range(len(header))]
    for r in [header, ["-" * w for w in widths]] + rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip())


def main() -> None:
    os.environ.pop("TRIGGER_LIVE", None)
    CACHE.mkdir(parents=True, exist_ok=True)
    log = CACHE / "replay_decisions.jsonl"
    for stale in (log, log.with_name(log.name + ".ledger.sqlite")):
        stale.unlink(missing_ok=True)
    os.environ["TRIGGER_LOG"] = str(log)

    rows = []
    for superevent_id, _ in SUPEREVENTS:
        value = gw_notice(superevent_id)
        now = parse_time(json.loads(value)["event"]["time"]) + timedelta(minutes=10)
        rows.append(_row(superevent_id, listener.handle("igwn.gwalert", value, now=now)))
    print("GW superevents (INITIAL notice, visibility at event + 10 min)\n")
    _print_table(rows)

    rows = []
    for topic, name in FIXTURE_NOTICES:
        value = (FIXTURES / name).read_bytes()
        alert = parse(topic, value)
        now = alert.event_time + timedelta(minutes=10) if alert else None
        rows.append(_row(name, listener.handle(topic, value, now=now)))
    print("\nNotice fixtures (visibility at event + 10 min)\n")
    _print_table(rows)
    print(f"\nshadow log: {os.environ['TRIGGER_LOG']}")


if __name__ == "__main__":
    main()
