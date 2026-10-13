import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Job, User
from app.schemas.join import JoinInfo, RoomInfo
from app.services.interviews import check_join_link, opens_at

logger = logging.getLogger(__name__)

# The candidate opens their unique link after logging in with their candidate account
router = APIRouter(prefix="/join", tags=["join"])


@router.get("/{token}", response_model=JoinInfo)
def get_join_info(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("candidate")),
):
    interview, status = check_join_link(db, token, user)
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
    interview, status = check_join_link(db, token, user)
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
