import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Interview, Job, User
from app.schemas.join import JoinInfo, RoomInfo
from app.services.interviews import closes_at, opens_at

logger = logging.getLogger(__name__)

# The candidate opens their unique link after logging in with their candidate account
router = APIRouter(prefix="/join", tags=["join"])


def _check_link(db: Session, token: str, user: User) -> tuple[Interview, str]:
    """Same checks for the join page and the room: valid link, own interview, not expired.
    Returns the interview and "too_early" or "ready"."""
    short = token[:8]  # never log the full token
    interview = db.scalar(select(Interview).where(Interview.join_token == token))
    if not interview:
        logger.warning("Join attempt with invalid link %s...", short)
        raise AppException("This interview link is not valid", 404, "INVALID_LINK")
    if interview.candidate.user_id != user.id:
        logger.warning("Join attempt for interview %s by another account (user %s)", interview.id, user.id)
        raise AppException("This interview belongs to another account", 403, "NOT_YOUR_INTERVIEW")

    now = datetime.now(timezone.utc)
    if interview.status == "in_progress":
        return interview, "ready"  # no expiry while the interview is running
    if interview.status != "scheduled" or now > closes_at(interview):
        logger.warning("Join attempt with expired link for interview %s (%s)", interview.id, interview.status)
        raise AppException("This interview link is no longer valid", 410, "LINK_EXPIRED")
    return interview, "too_early" if now < opens_at(interview) else "ready"


@router.get("/{token}", response_model=JoinInfo)
def get_join_info(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("candidate")),
):
    interview, status = _check_link(db, token, user)
    logger.info("Join attempt for interview %s: %s", interview.id, status)
    return JoinInfo(
        company_name=settings.company_name,
        job_title=db.get(Job, interview.job_id).title,
        candidate_name=interview.candidate.full_name,
        scheduled_at=interview.scheduled_at,
        duration_minutes=interview.duration_minutes,
        opens_at=opens_at(interview),
        status=status,
    )


@router.get("/{token}/room", response_model=RoomInfo)
def get_room_info(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("candidate")),
):
    """Candidate enters the room. Does not change the interview status."""
    interview, status = _check_link(db, token, user)
    if status != "ready":
        logger.warning("Interview %s: candidate tried to enter the room too early", interview.id)
        raise AppException("The interview room is not open yet", 409, "ROOM_NOT_OPEN")
    logger.info("Interview %s: candidate entered the room", interview.id)
    return RoomInfo(
        job_title=db.get(Job, interview.job_id).title,
        candidate_name=interview.candidate.full_name,
        status=interview.status,
        started_at=interview.started_at,
    )
