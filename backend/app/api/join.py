import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Interview, Job, User
from app.schemas.join import JoinInfo

logger = logging.getLogger(__name__)

# The candidate opens their unique link after logging in with their candidate account
router = APIRouter(prefix="/join", tags=["join"])

OPEN_BEFORE = timedelta(minutes=10)


@router.get("/{token}", response_model=JoinInfo)
def get_join_info(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("candidate")),
):
    short = token[:8]  # never log the full token
    interview = db.scalar(select(Interview).where(Interview.join_token == token))
    if not interview:
        logger.warning("Join attempt with invalid link %s...", short)
        raise AppException("This interview link is not valid", 404, "INVALID_LINK")
    if interview.candidate.user_id != user.id:
        logger.warning("Join attempt for interview %s by another account (user %s)", interview.id, user.id)
        raise AppException("This interview belongs to another account", 403, "NOT_YOUR_INTERVIEW")

    now = datetime.now(timezone.utc)
    opens_at = interview.scheduled_at - OPEN_BEFORE
    closes_at = interview.scheduled_at + timedelta(minutes=interview.duration_minutes)

    if interview.status == "in_progress":
        status = "ready"  # no expiry while the interview is running
    elif interview.status != "scheduled" or now > closes_at:
        logger.warning("Join attempt with expired link for interview %s (%s)", interview.id, interview.status)
        raise AppException("This interview link is no longer valid", 410, "LINK_EXPIRED")
    else:
        status = "too_early" if now < opens_at else "ready"

    logger.info("Join attempt for interview %s: %s", interview.id, status)
    return JoinInfo(
        company_name=settings.company_name,
        job_title=db.get(Job, interview.job_id).title,
        candidate_name=interview.candidate.full_name,
        scheduled_at=interview.scheduled_at,
        duration_minutes=interview.duration_minutes,
        opens_at=opens_at,
        status=status,
    )
