import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models import Candidate, Interview, Job, User
from app.schemas.join import MyInterview
from app.services.interviews import join_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/interviews", response_model=list[MyInterview])
def my_interviews(db: Session = Depends(get_db), user: User = Depends(require_role("candidate"))):
    """The logged-in candidate's interviews across all jobs they applied to."""
    rows = db.execute(
        select(Interview, Job.title)
        .join(Candidate, Interview.candidate_id == Candidate.id)
        .join(Job, Interview.job_id == Job.id)
        .where(Candidate.user_id == user.id)
        .order_by(Interview.scheduled_at.desc())
    ).all()
    return [
        MyInterview(
            job_title=title,
            scheduled_at=interview.scheduled_at,
            duration_minutes=interview.duration_minutes,
            status=interview.status,
            join_url=join_url(interview),
        )
        for interview, title in rows
    ]
