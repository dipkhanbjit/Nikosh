import asyncio
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.core.security import hash_password
from app.models import Candidate, Interview, Job, User
from app.models.interview import ACTIVE_STATUSES

logger = logging.getLogger(__name__)

PASSWORD_LENGTH = 10
PASSWORD_CHARS = string.ascii_letters + string.digits

# Allowed status changes: scheduled → in_progress → completed, or scheduled → cancelled / no_show
TRANSITIONS = {
    "scheduled": {"in_progress", "cancelled", "no_show"},
    "in_progress": {"completed"},
}


def change_status(db: Session, interview: Interview, new_status: str) -> Interview:
    if new_status not in TRANSITIONS.get(interview.status, set()):
        raise AppException(
            f"Cannot change interview from {interview.status} to {new_status}", 409, "INVALID_STATUS"
        )
    now = datetime.now(timezone.utc)
    if new_status == "in_progress":
        interview.started_at = now
    elif new_status in ("completed", "cancelled", "no_show"):
        interview.ended_at = now
    old_status, interview.status = interview.status, new_status
    db.commit()
    db.refresh(interview)
    logger.info("Interview %s: %s → %s", interview.id, old_status, new_status)
    return interview


def join_url(interview: Interview) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/interview/join/{interview.join_token}"


def ensure_future(scheduled_at: datetime) -> None:
    if scheduled_at <= datetime.now(timezone.utc):
        raise AppException("Interview time must be in the future", 422, "TIME_IN_PAST")


def validate_candidate(db: Session, job: Job, candidate_id: int) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if not candidate or candidate.job_id != job.id:
        raise AppException("Candidate not found for this job", 404, "CANDIDATE_NOT_FOUND")
    if not candidate.shortlisted:
        raise AppException("Only shortlisted candidates can be scheduled", 409, "NOT_SHORTLISTED")
    if not candidate.email:
        raise AppException("Candidate has no email address", 409, "NO_EMAIL")
    active = db.scalar(
        select(Interview.id).where(
            Interview.candidate_id == candidate.id, Interview.status.in_(ACTIVE_STATUSES)
        )
    )
    if active:
        raise AppException("Candidate already has an active interview", 409, "INTERVIEW_EXISTS")
    return candidate


def ensure_candidate_account(db: Session, candidate: Candidate) -> tuple[str, str]:
    """Find or create the candidate's login account, set a new password and link it.
    Returns (email, plain password) so it can be shown once; the password is never stored or logged."""
    email = candidate.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user and user.role != "candidate":
        raise AppException("This email belongs to a staff account", 409, "EMAIL_IN_USE")

    password = "".join(secrets.choice(PASSWORD_CHARS) for _ in range(PASSWORD_LENGTH))
    if user:
        user.hashed_password = hash_password(password)
        user.is_active = True
        logger.info("Candidate account %s: password reset for new interview", user.id)
    else:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=candidate.full_name or email,
            role="candidate",
        )
        db.add(user)
        db.flush()
        logger.info("Candidate account %s created for candidate %s", user.id, candidate.id)
    candidate.user_id = user.id
    return email, password


def mark_no_shows() -> None:
    """Mark scheduled interviews whose end time has passed as no-show."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        scheduled = db.scalars(select(Interview).where(Interview.status == "scheduled")).all()
        overdue = [i for i in scheduled if i.scheduled_at + timedelta(minutes=i.duration_minutes) <= now]
        for interview in overdue:
            change_status(db, interview, "no_show")
    if overdue:
        logger.info("Marked %s overdue interview(s) as no-show", len(overdue))


async def no_show_check_loop() -> None:
    """Background task: every few minutes, mark interviews nobody started as no-show."""
    while True:
        try:
            await asyncio.to_thread(mark_no_shows)
        except Exception:
            logger.exception("No-show check failed")
        await asyncio.sleep(settings.no_show_check_interval_minutes * 60)
