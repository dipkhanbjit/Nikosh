"""Hiring decision (8.6.3): the interviewer's final call, separate from the AI recommendation.
Optionally notifies the candidate (one email + their home page); a failed email never undoes it."""

import logging
from datetime import datetime, timezone
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.models import Candidate, Interview, Job, User
from app.services.invitations import _heading, _layout, _reason
from app.services.mcp_client import MCPToolError, call_tool

logger = logging.getLogger(__name__)

DECISIONS = {"selected": "Selected", "not_selected": "Not selected"}


# ---------- Pure rules (no DB; tested offline) ----------

def can_decide(interview_statuses: list[str]) -> bool:
    """A decision needs at least one completed interview (an assessment is recommended, not required)."""
    return "completed" in interview_statuses


def apply_decision(candidate, decision: str, note: str | None, user_id: int | None, now: datetime) -> None:
    """Save the decision. A changed decision is no longer the one the candidate was told about."""
    if candidate.decision != decision:
        candidate.decision_notified_at = None
        candidate.decision_message = None
        candidate.decision_email_status = None
        candidate.decision_email_error = None
    candidate.decision = decision
    candidate.decision_note = (note or "").strip() or None
    candidate.decided_at = now
    candidate.decided_by = user_id


def candidate_view(candidate) -> tuple[str | None, str | None]:
    """What the candidate sees on their home page: only a decision they were notified about."""
    if candidate.decision and candidate.decision_notified_at:
        return candidate.decision, candidate.decision_message
    return None, None


def _outcome_lines(decision: str, job_title: str) -> list[str]:
    if decision == "selected":
        return [
            f"We are pleased to inform you that you have been selected for the {job_title} position.",
            "Our team will contact you shortly with the next steps.",
        ]
    return [
        f"Thank you for your interest in the {job_title} position and for the time you spent "
        "interviewing with us.",
        "After careful consideration, we will not be moving forward with your application at this time. "
        "We wish you every success in your job search.",
    ]


def decision_subject(job_title: str) -> str:
    return f"Application Outcome – {job_title} | {settings.company_name}"


def decision_email_html(name: str | None, job_title: str, decision: str, message: str | None) -> str:
    paragraphs = "".join(f'<p style="margin:0 0 16px;">{escape(line)}</p>'
                         for line in _outcome_lines(decision, job_title))
    note = ""
    if message and message.strip():
        body = escape(message.strip()).replace("\n", "<br>")
        note = f'{_heading("Message from the interviewer")}<p style="margin:0 0 16px;">{body}</p>'
    return _layout(f'<p style="margin:0 0 16px;">Dear {escape(name or "Candidate")},</p>{paragraphs}{note}')


def decision_email_text(name: str | None, job_title: str, decision: str, message: str | None) -> str:
    lines = "\n\n".join(_outcome_lines(decision, job_title))
    note = f"\n\nMessage from the interviewer:\n{message.strip()}" if message and message.strip() else ""
    return f"""Dear {name or "Candidate"},

{lines}{note}

Kind regards,
Recruitment Team
{settings.company_name}
"""


def notify_candidate(candidate, job_title: str, message: str | None, now: datetime) -> None:
    """Show the decision on the candidate's home page and email it. Never raises: a failed email
    is stored as decision_email_status / decision_email_error."""
    candidate.decision_message = (message or "").strip() or None
    candidate.decision_notified_at = now
    try:
        call_tool(
            "send_email",
            to=candidate.email,
            subject=decision_subject(job_title),
            html=decision_email_html(candidate.full_name, job_title, candidate.decision, candidate.decision_message),
            text=decision_email_text(candidate.full_name, job_title, candidate.decision, candidate.decision_message),
        )
        candidate.decision_email_status, candidate.decision_email_error = "sent", None
        logger.info("Candidate %s: decision email sent to %s", candidate.id, candidate.email)
    except MCPToolError as exc:
        candidate.decision_email_status, candidate.decision_email_error = "failed", _reason(exc)
        logger.error("Candidate %s: decision email failed: %s", candidate.id, exc)


# ---------- DB ----------

def interview_statuses(db: Session, candidate_id: int) -> list[str]:
    return list(db.scalars(select(Interview.status).where(Interview.candidate_id == candidate_id)))


def decided_by_name(db: Session, candidate: Candidate) -> str | None:
    user = db.get(User, candidate.decided_by) if candidate.decided_by else None
    return user.full_name if user else None


def save_decision(db: Session, candidate: Candidate, user: User, decision: str, note: str | None,
                  notify: bool, message: str | None) -> None:
    if not can_decide(interview_statuses(db, candidate.id)):
        raise AppException("A decision can be made only after a completed interview", 409,
                           "INTERVIEW_NOT_COMPLETED")
    if notify and not candidate.email:
        raise AppException("The candidate has no contact email", 400, "NO_CONTACT_EMAIL")
    now = datetime.now(timezone.utc)
    apply_decision(candidate, decision, note, user.id, now)
    db.commit()
    logger.info("Candidate %s: decision %s saved by user %s", candidate.id, decision, user.id)
    if notify:
        job = db.get(Job, candidate.job_id)
        notify_candidate(candidate, job.title if job else "", message, now)
        db.commit()
    db.refresh(candidate)
