import json
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Interview, Job
from app.services.interviews import join_url
from app.services.mcp_client import MCPToolError, call_tool

logger = logging.getLogger(__name__)

DHAKA = timezone(timedelta(hours=6), "Asia/Dhaka")  # Bangladesh has no daylight saving
MAX_ERROR_LENGTH = 300


def _reason(exc: Exception) -> str:
    """Short error text without the MCP 'Error executing tool x:' prefix."""
    text = str(exc)
    if text.startswith("Error executing tool") and ": " in text:
        text = text.split(": ", 1)[1]
    return text[:MAX_ERROR_LENGTH]


def _dhaka_time(dt: datetime) -> str:
    return dt.astimezone(DHAKA).strftime("%A, %d %B %Y, %I:%M %p") + " (Dhaka time)"


def _invitation_html(interview: Interview, job: Job, password: str) -> str:
    candidate = interview.candidate
    link = join_url(interview)
    return f"""
<p>Dear {escape(candidate.full_name or "Candidate")},</p>
<p>Thank you for applying to {escape(settings.company_name)}. You are invited to an online
video interview for the position of <strong>{escape(job.title)}</strong>.</p>
<table cellpadding="4">
  <tr><td><strong>Date &amp; time</strong></td><td>{_dhaka_time(interview.scheduled_at)}</td></tr>
  <tr><td><strong>Duration</strong></td><td>{interview.duration_minutes} minutes</td></tr>
  <tr><td><strong>Login email</strong></td><td>{escape(candidate.email)}</td></tr>
  <tr><td><strong>Password</strong></td><td>{escape(password)}</td></tr>
</table>
<p><a href="{link}">Join the interview</a><br>{link}</p>
<p><strong>Instructions</strong></p>
<ul>
  <li>Open the link above and log in with the email and password shown here.</li>
  <li>The interview room opens 10 minutes before the start time.</li>
  <li>Use a quiet place with a working camera and microphone.</li>
</ul>
<p>Best regards,<br>{escape(settings.company_name)} Recruitment Team</p>
"""


def _cancellation_html(interview: Interview, job: Job) -> str:
    return f"""
<p>Dear {escape(interview.candidate.full_name or "Candidate")},</p>
<p>Your interview for the position of <strong>{escape(job.title)}</strong> scheduled on
{_dhaka_time(interview.scheduled_at)} has been cancelled. The interview link is no longer valid.</p>
<p>We will contact you if a new interview is arranged.</p>
<p>Best regards,<br>{escape(settings.company_name)} Recruitment Team</p>
"""


def send_invitation(db: Session, interview: Interview, password: str) -> None:
    """Create the calendar event (if not created yet), then email the invitation with the
    login details. Never raises: the result is stored as invitation_status / invitation_error."""
    job = db.get(Job, interview.job_id)
    candidate = interview.candidate
    errors = []

    if not interview.calendar_event_id:
        start = interview.scheduled_at.astimezone(DHAKA)
        end = start + timedelta(minutes=interview.duration_minutes)
        try:
            event = json.loads(call_tool(
                "create_calendar_event",
                summary=f"Interview: {job.title} ({settings.company_name})",
                description=f"Online interview for {job.title}.\nJoin link: {join_url(interview)}",
                start=start.isoformat(),
                end=end.isoformat(),
                attendee_email=candidate.email,
            ))
            interview.calendar_event_id = event["event_id"]
            interview.calendar_url = event["html_link"]
            logger.info("Interview %s: calendar event %s created", interview.id, event["event_id"])
        except (MCPToolError, ValueError, KeyError) as exc:
            errors.append(f"Calendar: {_reason(exc)}")
            logger.error("Interview %s: calendar event failed: %s", interview.id, exc)

    try:
        call_tool(
            "send_email",
            to=candidate.email,
            subject=f"Interview invitation: {job.title} at {settings.company_name}",
            html=_invitation_html(interview, job, password),
        )
        interview.invitation_sent_at = datetime.now(timezone.utc)
        logger.info("Interview %s: invitation email sent to %s", interview.id, candidate.email)
    except MCPToolError as exc:
        errors.append(f"Email: {_reason(exc)}")
        logger.error("Interview %s: invitation email failed: %s", interview.id, exc)

    interview.invitation_status = "failed" if errors else "sent"
    interview.invitation_error = "; ".join(errors) or None
    db.commit()
    db.refresh(interview)


def cancel_invitation(db: Session, interview: Interview) -> None:
    """Delete the calendar event and send a short cancellation email. Failures are only logged."""
    job = db.get(Job, interview.job_id)
    if interview.calendar_event_id:
        try:
            call_tool("delete_calendar_event", event_id=interview.calendar_event_id)
            logger.info("Interview %s: calendar event %s removed", interview.id, interview.calendar_event_id)
        except MCPToolError as exc:
            logger.error("Interview %s: deleting calendar event failed: %s", interview.id, exc)
    try:
        call_tool(
            "send_email",
            to=interview.candidate.email,
            subject=f"Interview cancelled: {job.title} at {settings.company_name}",
            html=_cancellation_html(interview, job),
        )
        logger.info("Interview %s: cancellation email sent", interview.id)
    except MCPToolError as exc:
        logger.error("Interview %s: cancellation email failed: %s", interview.id, exc)
