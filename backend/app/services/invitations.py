import json
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Interview, Job
from app.services.ics import DHAKA, build_ics
from app.services.interviews import join_url
from app.services.mcp_client import MCPToolError, call_tool

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 300
BRAND_COLOR = "#1d4ed8"


def _reason(exc: Exception) -> str:
    """Short error text without the MCP 'Error executing tool x:' prefix."""
    text = str(exc)
    if text.startswith("Error executing tool") and ": " in text:
        text = text.split(": ", 1)[1]
    return text[:MAX_ERROR_LENGTH]


def _dhaka_time(dt: datetime) -> str:
    return dt.astimezone(DHAKA).strftime("%A, %d %B %Y, %I:%M %p") + " (Dhaka time, GMT+6)"


def _uid(interview: Interview) -> str:
    """Stable calendar UID per interview (the join token part avoids clashes after a DB reset)."""
    return f"nikosh-interview-{interview.id}-{interview.join_token[:12]}@nirvik"


def _summary(job: Job) -> str:
    return f"Interview: {job.title} - {settings.company_name}"


def _ics(interview: Interview, job: Job, method: str) -> str:
    """Calendar invite / cancellation. Description is the join link (plus the recording notice
    on an invite), never the password. Empty if the organizer address is not configured."""
    if not settings.google_account_email:
        logger.warning("GOOGLE_ACCOUNT_EMAIL is not set: sending without a calendar invite")
        return ""
    start = interview.scheduled_at
    return build_ics(
        method=method,
        uid=_uid(interview),
        sequence=interview.invitation_sequence,
        start=start,
        end=start + timedelta(minutes=interview.duration_minutes),
        summary=_summary(job),
        description=join_url(interview) + (f"\n\n{RECORDING_NOTICE}" if method == "REQUEST" else ""),
        organizer_email=settings.google_account_email,
        organizer_name=settings.company_name,
        attendee_email=interview.candidate.email,
        attendee_name=interview.candidate.full_name or "Candidate",
    )


# ---------- email layout ----------

def _layout(body: str) -> str:
    """Single-column, inline-styled email that reads well on mobile."""
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f3f4f6;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
 style="max-width:600px;background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;">
<tr><td style="padding:20px 28px;border-bottom:3px solid {BRAND_COLOR};font-family:Arial,Helvetica,sans-serif;
 font-size:18px;font-weight:bold;color:#111827;">{escape(settings.company_name)}</td></tr>
<tr><td style="padding:24px 28px;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#1f2937;">
{body}
<p style="margin:24px 0 0;">Kind regards,<br>Recruitment Team<br>{escape(settings.company_name)}</p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def _heading(text: str) -> str:
    return (f'<p style="margin:24px 0 8px;font-size:16px;font-weight:bold;color:#111827;">'
            f"{escape(text)}</p>")


def _details(rows: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<tr><td style="padding:6px 12px 6px 0;color:#6b7280;white-space:nowrap;vertical-align:top;">'
        f'{escape(label)}</td><td style="padding:6px 0;color:#111827;">{escape(value)}</td></tr>'
        for label, value in rows
    )
    return f'<table role="presentation" cellpadding="0" cellspacing="0" style="font-size:15px;">{cells}</table>'


def _text_details(rows: list[tuple[str, str]]) -> str:
    return "\n".join(f"  {label}: {value}" for label, value in rows)


# ---------- invitation ----------

def _invitation_rows(interview: Interview, password: str) -> tuple[list, list]:
    details = [
        ("Date & time", _dhaka_time(interview.scheduled_at)),
        ("Duration", f"{interview.duration_minutes} minutes"),
        ("Format", "Online video interview"),
    ]
    login = [("Email", interview.candidate.email), ("Password", password)]
    return details, login


BEFORE_INTERVIEW = [
    "Log in with the email and password above, then open the interview link.",
    "The interview room opens 10 minutes before the start time.",
    "Join from a quiet place with a working camera and microphone, using Chrome or Edge.",
    "A calendar invitation is attached to this email.",
]
RECORDING_NOTICE = ("Please note that the audio of this interview will be recorded and transcribed "
                    "for evaluation and record-keeping purposes. The recording will be kept "
                    "confidential and used only for this recruitment process.")
PERSONAL_NOTE = ("These login details are personal. Please do not share them. "
                 "If you need to reschedule, please reply to this email.")


def _invitation_html(interview: Interview, job: Job, password: str) -> str:
    name = escape(interview.candidate.full_name or "Candidate")
    title = escape(job.title)
    company = escape(settings.company_name)
    link = escape(join_url(interview))
    details, login = _invitation_rows(interview, password)
    tips = "".join(f'<li style="margin:4px 0;">{escape(item)}</li>' for item in BEFORE_INTERVIEW)
    return _layout(f"""
<p style="margin:0 0 16px;">Dear {name},</p>
<p style="margin:0 0 16px;">Thank you for your interest in the <strong>{title}</strong> position at {company}.
We are pleased to invite you to an online video interview.</p>
{_heading("Interview details")}
{_details(details)}
{_heading("Login details")}
{_details(login)}
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 8px;">
<tr><td style="border-radius:6px;background:{BRAND_COLOR};">
<a href="{link}" style="display:inline-block;padding:12px 28px;font-family:Arial,Helvetica,sans-serif;
 font-size:15px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:6px;">Join Interview</a>
</td></tr></table>
<p style="margin:0 0 16px;font-size:13px;color:#6b7280;">If the button does not work, copy this link into
your browser:<br><a href="{link}" style="color:{BRAND_COLOR};word-break:break-all;">{link}</a></p>
{_heading("Before the interview")}
<ul style="margin:0;padding-left:20px;">{tips}</ul>
<p style="margin:16px 0 0;">{escape(RECORDING_NOTICE)}</p>
<p style="margin:16px 0 0;">{escape(PERSONAL_NOTE)}</p>
<p style="margin:16px 0 0;">We look forward to speaking with you.</p>
""")


def _invitation_text(interview: Interview, job: Job, password: str) -> str:
    details, login = _invitation_rows(interview, password)
    tips = "\n".join(f"  - {item}" for item in BEFORE_INTERVIEW)
    return f"""Dear {interview.candidate.full_name or "Candidate"},

Thank you for your interest in the {job.title} position at {settings.company_name}. We are pleased to invite you to an online video interview.

Interview details
{_text_details(details)}

Login details
{_text_details(login)}

Join Interview:
{join_url(interview)}

Before the interview
{tips}

{RECORDING_NOTICE}

{PERSONAL_NOTE}

We look forward to speaking with you.

Kind regards,
Recruitment Team
{settings.company_name}
"""


# ---------- cancellation ----------

def _cancellation_lines(interview: Interview, job: Job) -> list[str]:
    return [
        f"The interview for the {job.title} position scheduled for "
        f"{_dhaka_time(interview.scheduled_at)} has been cancelled.",
        "The interview link and login details are no longer valid, "
        "and the calendar event has been removed.",
        "We will contact you if a new interview is arranged.",
    ]


def _cancellation_html(interview: Interview, job: Job) -> str:
    name = escape(interview.candidate.full_name or "Candidate")
    paragraphs = "".join(f'<p style="margin:0 0 16px;">{escape(line)}</p>'
                         for line in _cancellation_lines(interview, job))
    return _layout(f'<p style="margin:0 0 16px;">Dear {name},</p>{paragraphs}')


def _cancellation_text(interview: Interview, job: Job) -> str:
    lines = "\n\n".join(_cancellation_lines(interview, job))
    return f"""Dear {interview.candidate.full_name or "Candidate"},

{lines}

Kind regards,
Recruitment Team
{settings.company_name}
"""


# ---------- actions ----------

def send_invitation(db: Session, interview: Interview, password: str) -> None:
    """Create the calendar event (if not created yet; Google sends no email), then email the
    invitation with the login details and an .ics invite. Each send raises the .ics SEQUENCE.
    Never raises: the result is stored as invitation_status / invitation_error."""
    job = db.get(Job, interview.job_id)
    candidate = interview.candidate
    errors = []

    if not interview.calendar_event_id:
        start = interview.scheduled_at.astimezone(DHAKA)
        end = start + timedelta(minutes=interview.duration_minutes)
        try:
            event = json.loads(call_tool(
                "create_calendar_event",
                summary=_summary(job),
                description=join_url(interview),
                start=start.isoformat(),
                end=end.isoformat(),
                attendee_email=candidate.email,
                uid=_uid(interview),
            ))
            interview.calendar_event_id = event["event_id"]
            interview.calendar_url = event["html_link"]
            logger.info("Interview %s: calendar event %s created", interview.id, event["event_id"])
        except (MCPToolError, ValueError, KeyError) as exc:
            errors.append(f"Calendar: {_reason(exc)}")
            logger.error("Interview %s: calendar event failed: %s", interview.id, exc)

    interview.invitation_sequence = (interview.invitation_sequence or 0) + 1
    try:
        call_tool(
            "send_email",
            to=candidate.email,
            subject=f"Interview Invitation – {job.title} | {settings.company_name}",
            html=_invitation_html(interview, job, password),
            text=_invitation_text(interview, job, password),
            ics=_ics(interview, job, "REQUEST"),
            ics_method="REQUEST",
        )
        interview.invitation_sent_at = datetime.now(timezone.utc)
        logger.info("Interview %s: invitation email sent to %s (sequence %s)",
                    interview.id, candidate.email, interview.invitation_sequence)
    except MCPToolError as exc:
        errors.append(f"Email: {_reason(exc)}")
        logger.error("Interview %s: invitation email failed: %s", interview.id, exc)

    interview.invitation_status = "failed" if errors else "sent"
    interview.invitation_error = "; ".join(errors) or None
    db.commit()
    db.refresh(interview)


def cancel_invitation(db: Session, interview: Interview) -> None:
    """Delete the calendar event (silently) and send the cancellation email with an .ics
    CANCEL for the same UID. Failures are only logged."""
    job = db.get(Job, interview.job_id)
    if interview.calendar_event_id:
        try:
            call_tool("delete_calendar_event", event_id=interview.calendar_event_id)
            logger.info("Interview %s: calendar event %s removed", interview.id, interview.calendar_event_id)
        except MCPToolError as exc:
            logger.error("Interview %s: deleting calendar event failed: %s", interview.id, exc)

    interview.invitation_sequence = (interview.invitation_sequence or 0) + 1
    db.commit()
    try:
        call_tool(
            "send_email",
            to=interview.candidate.email,
            subject=f"Interview Cancelled – {job.title} | {settings.company_name}",
            html=_cancellation_html(interview, job),
            text=_cancellation_text(interview, job),
            ics=_ics(interview, job, "CANCEL"),
            ics_method="CANCEL",
        )
        logger.info("Interview %s: cancellation email sent (sequence %s)",
                    interview.id, interview.invitation_sequence)
    except MCPToolError as exc:
        logger.error("Interview %s: cancellation email failed: %s", interview.id, exc)
