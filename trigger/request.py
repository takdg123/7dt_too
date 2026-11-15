"""Turn a Decision into the ToO request the web form would send, and send it.

submit() mirrors backend/app/routes.py send_email: same subject, recipient, body layout and JSON
attachment, so the observation side cannot tell an automatic request from a form request except by
its comments. The wiki page and the requester confirmation that send_email also produces are not sent.
"""

import json
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr

import astropy.units as u
from astropy.coordinates import Angle
from dotenv import dotenv_values

from .model import Action, Alert, Decision, Stream

MAIL_ENV_PATH = "/home/7dt/7dt_too/backend/.env"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 587
REQUEST_RECIPIENT = "7dt.observation.alert@gmail.com"
REQUEST_SUBJECT = "[Automated] 7DT ToO Observation Request"
RAPID_STREAMS = {Stream.GRB, Stream.EP}


class NotLive(RuntimeError):
    pass


def _sexagesimal(ra_deg: float, dec_deg: float) -> tuple[str, str]:
    # The form accepts only -?HH:MM:SS(.s) with HH <= 23 and no leading "+", so round before formatting
    # (359.99999 deg would otherwise print as 24:00:00.00).
    ra_seconds = round(ra_deg / 15.0 * 3600.0, 2) % 86400.0
    ra = Angle(ra_seconds / 3600.0, u.hourangle).to_string(unit=u.hourangle, sep=":", precision=2, pad=True)
    dec = Angle(dec_deg, u.deg).to_string(unit=u.deg, sep=":", precision=1, pad=True)
    return str(ra), str(dec)


def _comments(decision: Decision) -> str:
    text = f"[auto-trigger] {decision.rule}: {'; '.join(decision.reasons)}"
    if decision.plan is not None:
        nights = ", ".join(str(n) for n in decision.plan.epochs_nights)
        text += f". Plan: {decision.plan.note}; repeat on nights {nights}"
    return text


def to_form_payload(alert: Alert, decision: Decision) -> dict:
    plan = decision.plan
    ra, dec = _sexagesimal(alert.ra_deg, alert.dec_deg)
    return {
        "requester": os.environ.get("TRIGGER_REQUESTER", ""),
        "target": alert.event_id,
        "ra": ra,
        "dec": dec,
        "exposure": plan.exposure_s,
        "imageCount": plan.image_count,
        "obsmode": plan.obsmode,
        "comments": _comments(decision),
        "abortObservation": alert.stream in RAPID_STREAMS,
        "priority": 100 if decision.action is Action.AUTO else 50,
        "gain": 2750,
        "binning": 1,
        "obsStartTime": "",
        "radius": 0,
        "selectedFilters": list(plan.filters),
        "selectedTelNumber": plan.n_telescopes,
    }


def _as_send_email_stores(payload: dict) -> dict:
    data = dict(payload)
    data["singleExposure"] = data["exposure"]
    data["exposure"] = float(data["singleExposure"]) * float(data["imageCount"])
    data["is_Too"] = True
    data["is_rapidToo"] = data["abortObservation"]
    data["cadence"] = 1
    data["Too_starttime"] = None
    data["Too_endtime"] = None
    return data


def _request_body(data: dict) -> str:
    filters = ",".join(data["selectedFilters"])
    return f"""
        ================================
        New ToO Request Submitted
        ================================

        **Observation Information**
        ----------------------
        - Requester: {data.get('requester')}
        - Target Name: {data.get('target')}
        - Right Ascension (R.A.): {data.get('ra')}
        - Declination (Dec.): {data.get('dec')}
        - Total Exposure Time (seconds): {data.get('exposure')}
        - Single Exposure Time (seconds): {data.get('singleExposure')}
        - # of images: {data.get('imageCount')}
        - Obsmode: {data.get('obsmode')}
            - Filters: {filters}
            - NumberofTelescopes: {data.get('selectedTelNumber')}

        **Detailed Settings**
        --------------------
        - Is_ToO: {data.get('is_Too')}
        - Is_rapidToO: {data.get('is_rapidToo')}
        - Cadence: {data.get('cadence')}
        - Number of Observation: 1
        - ToO start time: {data.get('Too_starttime')}
        - ToO end time: {data.get('Too_endtime')}
        - Priority: {data.get('priority')}
        - Gain: {data.get('gain')}
        - Radius (arcmin): {data.get('radius')}
        - Binning: {data.get('binning')}
        - Observation Start Time: {data.get('obsStartTime')}
        - Comments: {data.get('comments')}

        ================================
        Please take necessary actions.
        Link to the wiki (please update the page with relevant information)
        https://proton.snu.ac.kr/en/too/{data['target'].replace(' ', '')}
        ================================
        """


def _send(msg: EmailMessage) -> None:
    """The one place mail leaves this process."""
    if os.environ.get("TRIGGER_LIVE") != "1":
        raise NotLive("TRIGGER_LIVE is not 1; refusing to send mail")
    env = dotenv_values(MAIL_ENV_PATH)
    msg["From"] = formataddr(("7DT Observation Alert", env["SDT_SENDER"]))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(env["SDT_MAIL"], env["SDT_PASSWORD"])
        smtp.send_message(msg)


def submit(payload: dict) -> None:
    data = _as_send_email_stores(payload)
    msg = EmailMessage()
    msg["Subject"] = REQUEST_SUBJECT
    msg["To"] = REQUEST_RECIPIENT
    msg.set_content(_request_body(data))
    name = f"too_request_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    msg.add_attachment(json.dumps(data, indent=4).encode(), maintype="application", subtype="json", filename=name)
    _send(msg)


def operator_recipients() -> list[str]:
    return [a.strip() for a in os.environ.get("TRIGGER_OPERATOR_EMAILS", "").split(",") if a.strip()]


def notify_operators(alert: Alert, decision: Decision) -> None:
    recipients = operator_recipients()
    if not recipients:
        return
    lines = [
        f"{alert.source} {alert.event_id} ({alert.kind.value}), event time {alert.event_time.isoformat()}",
        f"Decision: {decision.action.value.upper()} by rule {decision.rule}"
        + (f", tier {decision.tier}" if decision.tier else ""),
        *(f"- {r}" for r in decision.reasons),
        "",
        "A human must submit this one through https://proton.snu.ac.kr/too/.",
    ]
    if alert.ra_deg is not None and decision.plan is not None:
        lines += ["Suggested form values:", json.dumps(to_form_payload(alert, decision), indent=2)]
    msg = EmailMessage()
    msg["Subject"] = f"[7DT trigger] {decision.action.value.upper()} {alert.event_id} ({decision.rule})"
    msg["To"] = ", ".join(recipients)
    msg.set_content("\n".join(lines))
    _send(msg)
