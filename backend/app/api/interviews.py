import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Interview, Job, User
from app.schemas.interview import (
    CancelRequest,
    Credentials,
    InterviewCreate,
    InterviewOut,
    InterviewUpdate,
)
from app.services.interviews import (
    change_status,
    ensure_candidate_account,
    ensure_future,
    join_url,
    room_open,
    validate_candidate,
)
from app.services.invitations import cancel_invitation, send_invitation
from app.services.rooms import end_room, push_from_thread, rooms

logger = logging.getLogger(__name__)

interviewer_only = Depends(require_role("interviewer"))

router = APIRouter(prefix="/interviews", tags=["interviews"], dependencies=[interviewer_only])
job_router = APIRouter(prefix="/jobs/{job_id}/interviews", tags=["interviews"], dependencies=[interviewer_only])


def _get_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise AppException("Job not found", 404, "JOB_NOT_FOUND")
    return job


def _get_interview(db: Session, interview_id: int) -> Interview:
    interview = db.get(Interview, interview_id)
    if not interview:
        raise AppException("Interview not found", 404, "INTERVIEW_NOT_FOUND")
    return interview


def _to_out(db: Session, interview: Interview) -> InterviewOut:
    job = db.get(Job, interview.job_id)
    return InterviewOut(
        id=interview.id,
        job_id=interview.job_id,
        job_title=job.title,
        candidate_id=interview.candidate_id,
        candidate_name=interview.candidate.full_name,
        candidate_email=interview.candidate.email,
        scheduled_at=interview.scheduled_at,
        duration_minutes=interview.duration_minutes,
        status=interview.status,
        notes=interview.notes,
        started_at=interview.started_at,
        ended_at=interview.ended_at,
        cancel_reason=interview.cancel_reason,
        join_url=join_url(interview),
        room_open=room_open(interview),
        calendar_url=interview.calendar_url,
        invitation_status=interview.invitation_status,
        invitation_error=interview.invitation_error,
        invitation_sent_at=interview.invitation_sent_at,
        created_at=interview.created_at,
    )


@job_router.post("", response_model=InterviewOut, status_code=201)
def schedule_interview(
    job_id: int,
    payload: InterviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("interviewer")),
):
    job = _get_job(db, job_id)
    ensure_future(payload.scheduled_at)
    candidate = validate_candidate(db, job, payload.candidate_id, payload.contact_email)
    email, password = ensure_candidate_account(db, candidate)
    interview = Interview(
        job_id=job.id,
        candidate_id=candidate.id,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        notes=payload.notes,
        created_by=user.id,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)
    logger.info("Interview %s scheduled for candidate %s at %s", interview.id, candidate.id, interview.scheduled_at)
    send_invitation(db, interview, password)  # never undoes the schedule; result stored on the interview
    out = _to_out(db, interview)
    out.credentials = Credentials(email=email, password=password)
    return out


@job_router.get("", response_model=list[InterviewOut])
def list_job_interviews(job_id: int, db: Session = Depends(get_db)):
    _get_job(db, job_id)
    interviews = db.scalars(
        select(Interview).where(Interview.job_id == job_id).order_by(Interview.scheduled_at)
    ).all()
    return [_to_out(db, i) for i in interviews]


@router.get("", response_model=list[InterviewOut])
def list_interviews(status: str | None = None, db: Session = Depends(get_db)):
    """All interviews for the session list screen, optionally filtered by status."""
    query = select(Interview).order_by(Interview.scheduled_at)
    if status:
        query = query.where(Interview.status == status)
    return [_to_out(db, i) for i in db.scalars(query).all()]


@router.get("/{interview_id}", response_model=InterviewOut)
def get_interview(interview_id: int, db: Session = Depends(get_db)):
    return _to_out(db, _get_interview(db, interview_id))


@router.patch("/{interview_id}", response_model=InterviewOut)
def reschedule_interview(interview_id: int, payload: InterviewUpdate, db: Session = Depends(get_db)):
    interview = _get_interview(db, interview_id)
    if interview.status != "scheduled":
        raise AppException("Only scheduled interviews can be changed", 409, "INVALID_STATUS")
    if payload.scheduled_at:
        ensure_future(payload.scheduled_at)
        interview.scheduled_at = payload.scheduled_at
    if payload.duration_minutes:
        interview.duration_minutes = payload.duration_minutes
    if payload.notes is not None:
        interview.notes = payload.notes
    db.commit()
    db.refresh(interview)
    logger.info("Interview %s updated", interview.id)
    return _to_out(db, interview)


@router.post("/{interview_id}/cancel", response_model=InterviewOut)
def cancel_interview(interview_id: int, body: CancelRequest, db: Session = Depends(get_db)):
    interview = _get_interview(db, interview_id)
    interview.cancel_reason = body.reason
    interview = change_status(db, interview, "cancelled")
    push_from_thread(interview.id, end_room, "cancelled")
    cancel_invitation(db, interview)
    return _to_out(db, interview)


@router.post("/{interview_id}/resend-invitation", response_model=InterviewOut)
def resend_invitation(interview_id: int, db: Session = Depends(get_db)):
    """Retry the calendar event if it failed and email the invitation again with a NEW password
    (the old one is not stored)."""
    interview = _get_interview(db, interview_id)
    if interview.status != "scheduled":
        raise AppException("Only scheduled interviews can be re-invited", 409, "INVALID_STATUS")
    email, password = ensure_candidate_account(db, interview.candidate)
    db.commit()
    logger.info("Interview %s: resending invitation", interview.id)
    send_invitation(db, interview, password)
    out = _to_out(db, interview)
    out.credentials = Credentials(email=email, password=password)
    return out


@router.post("/{interview_id}/no-show", response_model=InterviewOut)
def mark_no_show(interview_id: int, db: Session = Depends(get_db)):
    interview = _get_interview(db, interview_id)
    if interview.scheduled_at > datetime.now(timezone.utc):
        raise AppException("Interview has not started yet", 409, "TOO_EARLY")
    interview = change_status(db, interview, "no_show")
    push_from_thread(interview.id, end_room, "no_show")
    return _to_out(db, interview)


@router.post("/{interview_id}/start", response_model=InterviewOut)
def start_interview(interview_id: int, db: Session = Depends(get_db)):
    """The interviewer joins the room: scheduled → in_progress. Rejoining a running interview is allowed."""
    interview = _get_interview(db, interview_id)
    if not room_open(interview):
        logger.warning("Interview %s: start refused (%s, room not open)", interview.id, interview.status)
        raise AppException("The interview room is not open", 409, "ROOM_NOT_OPEN")
    if interview.status == "scheduled":
        interview = change_status(db, interview, "in_progress")
        started = {"type": "interview-started", "started_at": interview.started_at.isoformat()}
        push_from_thread(interview.id, rooms.broadcast, started)
    else:
        logger.info("Interview %s: interviewer rejoined the room", interview.id)
    return _to_out(db, interview)


@router.post("/{interview_id}/end", response_model=InterviewOut)
def end_interview(interview_id: int, db: Session = Depends(get_db)):
    """The interviewer ends the interview: in_progress → completed."""
    interview = _get_interview(db, interview_id)
    try:
        interview = change_status(db, interview, "completed")
    except AppException:
        logger.warning("Interview %s: end refused (%s)", interview.id, interview.status)
        raise
    push_from_thread(interview.id, end_room, "completed")
    return _to_out(db, interview)
