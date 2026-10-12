import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models import Candidate, Interview, Job
from app.models.interview import ACTIVE_STATUSES

logger = logging.getLogger(__name__)

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