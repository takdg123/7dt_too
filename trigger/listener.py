"""GCN Kafka listener: parse -> visibility -> decide -> record, one JSON line per message.

Shadow mode (the default) decides and logs only. With TRIGGER_LIVE=1 an AUTO decision is submitted
as a ToO request and an OPERATOR decision is mailed to TRIGGER_OPERATOR_EMAILS.

    python -m trigger.listener                                  # consume GCN Kafka
    python -m trigger.listener --file notice.json --topic igwn.gwalert [--now 2026-01-15T03:10:00Z]
"""

import argparse
import dataclasses
import json
import os
import sqlite3
import sys
import traceback
from contextlib import closing
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from . import request, sky
from .model import Action, Alert, Decision, NoticeKind, Visibility
from .parse import TOPICS, Notice, ParseError, parse_notice, parse_time
from .rules import decide

DEFAULT_LOG = "/home/7dt/too_recovery/trigger_decisions.jsonl"


def _log_path() -> Path:
    return Path(os.environ.get("TRIGGER_LOG", DEFAULT_LOG))


def _live() -> bool:
    return os.environ.get("TRIGGER_LIVE") == "1"


def _json_default(o):
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def _append(record: dict) -> dict:
    """Write one log line and return the record as logged, in plain JSON types."""
    line = json.dumps(record, default=_json_default)
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(line + "\n")
    return json.loads(line)


class Ledger:
    """Which notices were already handled and which events were already submitted, next to the log.

    A notice is keyed by (event_id, kind, source): SVOM sends an MXT INITIAL after the ECLAIRs INITIAL
    for the same burst, and the MXT position must still be seen. Submission is keyed by event_id alone,
    and is claimed before the mail goes out, so a crash mid-submit errs toward not resubmitting.
    """

    def __init__(self, log_path: Path):
        self.path = log_path.with_name(log_path.name + ".ledger.sqlite")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.execute("CREATE TABLE IF NOT EXISTS notices (event_id TEXT, kind TEXT, source TEXT, first_seen TEXT,"
                   " PRIMARY KEY (event_id, kind, source))")
        db.execute("CREATE TABLE IF NOT EXISTS submissions (event_id TEXT PRIMARY KEY, claimed_at TEXT)")
        return db

    def _claim(self, sql: str, args: tuple) -> bool:
        with closing(self._connect()) as db, db:
            return db.execute(sql, args).rowcount == 1

    def claim_notice(self, alert: Alert) -> bool:
        return self._claim("INSERT OR IGNORE INTO notices VALUES (?, ?, ?, ?)",
                           (alert.event_id, alert.kind.value, alert.source, _now().isoformat()))

    def claim_submission(self, event_id: str) -> bool:
        return self._claim("INSERT OR IGNORE INTO submissions VALUES (?, ?)", (event_id, _now().isoformat()))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def visibility(notice: Notice, now: datetime) -> Optional[Visibility]:
    alert = notice.alert
    if alert.kind is NoticeKind.RETRACTION:
        return None
    if notice.prob_table is not None:
        return sky.visibility_map(notice.prob_table, now)
    if alert.ra_deg is not None:
        return sky.visibility_point(alert.ra_deg, alert.dec_deg, now)
    return None


def _act(alert: Alert, decision: Decision, ledger: Ledger, live: bool, record: dict) -> str:
    if decision.action is Action.AUTO:
        payload = request.to_form_payload(alert, decision)
        record["payload"] = payload
        if not ledger.claim_submission(alert.event_id):
            return "already-submitted"
        if not live:
            return "would-submit"
        try:
            request.submit(payload)
            return "submitted"
        except Exception as e:
            return f"submit-failed: {type(e).__name__}: {e}"
    if decision.action is Action.OPERATOR:
        if not live:
            return "would-notify"
        if not request.operator_recipients():
            return "no-operators"
        try:
            request.notify_operators(alert, decision)
            return "notified"
        except Exception as e:
            return f"notify-failed: {type(e).__name__}: {e}"
    return "none"


def handle(topic: str, value: bytes, now: Optional[datetime] = None, allow_test: bool = False) -> dict:
    now = now or _now()
    live = _live()
    record = {"received_at": _now().isoformat(), "now": now.isoformat(), "mode": "live" if live else "shadow",
              "topic": topic}
    try:
        notice = parse_notice(topic, value, allow_test)
    except ParseError as e:
        record.update(status="error", error=str(e))
        return _append(record)
    if notice is None:
        record["status"] = "skipped"
        return _append(record)

    alert = notice.alert
    record["alert"] = dataclasses.asdict(alert)
    ledger = Ledger(_log_path())
    if not ledger.claim_notice(alert):
        record["status"] = "duplicate"
        return _append(record)

    vis = visibility(notice, now)
    decision = decide(alert, vis or Visibility(None, 0.0))
    record.update(status="decided", visibility=vis and dataclasses.asdict(vis), decision=dataclasses.asdict(decision))
    record["effect"] = _act(alert, decision, ledger, live, record)
    return _append(record)


def _consume() -> int:
    client_id, client_secret = os.environ.get("GCN_CLIENT_ID"), os.environ.get("GCN_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("GCN_CLIENT_ID and GCN_CLIENT_SECRET must be set; create a client credential at "
              "https://gcn.nasa.gov/user/credentials", file=sys.stderr)
        return 2
    from gcn_kafka import Consumer

    consumer = Consumer(config={"group.id": os.environ.get("TRIGGER_GROUP_ID", "7dt-too-trigger")},
                        client_id=client_id, client_secret=client_secret)
    consumer.subscribe(list(TOPICS))
    print(f"listening on {', '.join(TOPICS)} in {'LIVE' if _live() else 'shadow'} mode; log {_log_path()}",
          flush=True)
    while True:
        for message in consumer.consume(timeout=1):
            if message.error():
                print(f"kafka: {message.error()}", file=sys.stderr, flush=True)
                continue
            try:
                handle(message.topic(), message.value())
            except Exception as e:
                traceback.print_exc()
                _append({"received_at": _now().isoformat(), "topic": message.topic(), "status": "error",
                         "error": f"{type(e).__name__}: {e}"})


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m trigger.listener", description=__doc__.splitlines()[0])
    p.add_argument("--file", type=Path, help="feed one saved notice through handle() instead of consuming Kafka")
    p.add_argument("--topic", choices=TOPICS, help="the Kafka topic the saved notice came from")
    p.add_argument("--now", type=parse_time, help="evaluate visibility at this ISO time instead of the current time")
    p.add_argument("--allow-test", action="store_true", help="accept mock/test GW superevents")
    args = p.parse_args(argv)
    if args.file is None:
        return _consume()
    if args.topic is None:
        p.error("--file needs --topic")
    record = handle(args.topic, args.file.read_bytes(), now=args.now, allow_test=args.allow_test)
    print(json.dumps(record, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    sys.exit(main())
