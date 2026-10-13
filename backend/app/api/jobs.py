from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Job, User
from app.schemas.job import JobCreate, JobOut, JobUpdate, ScoreWeights, ScoreWeightsOut
from app.services.candidate_scoring import job_weights, recalculate_job_scores
from app.services.deadlines import end_of_day
from app.services.form_status import update_form_state
from app.services.audio_recorder import delete_interview_audio
from app.services.interview_chat import delete_interview_files
from app.services.job_posting import publish_job
from app.services.mcp_client import MCPToolError, call_tool
from app.services.storage import delete_file

router = APIRouter(prefix="/jobs", tags=["jobs"])
interviewer_only = require_role("interviewer")


def get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise AppException("Job not found", 404, "JOB_NOT_FOUND")
    return job


def _normalize(title: str) -> str:
    return " ".join(title.split()).casefold()


def ensure_unique_title(db: Session, title: str, exclude_id: int | None = None) -> None:
    """Open jobs must have unique titles so posts and application forms are not confused."""
    open_jobs = db.execute(select(Job.id, Job.title).where(Job.status != "closed")).all()
    target = _normalize(title)
    if any(job_id != exclude_id and _normalize(t) == target for job_id, t in open_jobs):
        raise AppException(
            "An open job with this title already exists. Use a more specific title, "
            "e.g. 'Frontend Developer (Payments)'.",
            409,
            "DUPLICATE_JOB_TITLE",
        )


@router.post("", response_model=JobOut, status_code=201)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(interviewer_only),
):
    ensure_unique_title(db, payload.title)
    data = payload.model_dump()
    deadline = data.pop("application_deadline")
    job = Job(**data, created_by=user.id)
    job.application_deadline = end_of_day(deadline) if deadline else None
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=list[JobOut], dependencies=[Depends(interviewer_only)])
def list_jobs(db: Session = Depends(get_db)):
    return db.scalars(select(Job).order_by(Job.created_at.desc())).all()


@router.get("/{job_id}", response_model=JobOut, dependencies=[Depends(interviewer_only)])
def get_job(job_id: int, db: Session = Depends(get_db)):
    return get_job_or_404(db, job_id)


@router.patch("/{job_id}", response_model=JobOut, dependencies=[Depends(interviewer_only)])
def update_job(job_id: int, payload: JobUpdate, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    changes = payload.model_dump(exclude_unset=True)
    new_title = changes.get("title")
    if new_title and _normalize(new_title) != _normalize(job.title):
        if job.status == "posted":
            raise AppException(
                "The title of a posted job cannot be changed, because the posts and the "
                "application form already use it",
                409,
                "JOB_ALREADY_POSTED",
            )
        ensure_unique_title(db, new_title, exclude_id=job.id)
    deadline_changed = "application_deadline" in changes
    if deadline_changed:
        deadline = changes.pop("application_deadline")
        job.application_deadline = end_of_day(deadline) if deadline else None
    for field, value in changes.items():
        setattr(job, field, value)
    db.commit()
    if deadline_changed or "status" in changes:
        update_form_state(db, job)  # close or reopen the form right away
    db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=204, dependencies=[Depends(interviewer_only)])
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    if job.form_id and not job.form_closed_at:
        try:
            call_tool("set_form_open", form_id=job.form_id, accepting=False)
        except MCPToolError:
            pass  # the job is deleted anyway; the failure is logged by the MCP client
    cv_paths = [c.cv_file_path for c in job.candidates]
    interview_ids = [i.id for c in job.candidates for i in c.interviews]  # messages go with the DB cascade
    db.delete(job)
    db.commit()
    for path in cv_paths:
        delete_file(path)
    delete_interview_files(interview_ids)
    delete_interview_audio(interview_ids)


@router.post("/{job_id}/post", response_model=JobOut, dependencies=[Depends(interviewer_only)])
def post_job_now(job_id: int, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    needs_blogger = job.status == "approved"
    needs_telegram = job.status == "posted" and not job.telegram_url
    if not (needs_blogger or needs_telegram):
        raise AppException("Nothing to post for this job", 409, "NOTHING_TO_POST")
    publish_job(db, job)
    db.refresh(job)
    return job


@router.get("/{job_id}/score-weights", response_model=ScoreWeightsOut, dependencies=[Depends(interviewer_only)])
def get_score_weights(job_id: int, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    return ScoreWeightsOut(weights=job_weights(job), is_default=not job.score_weights)


@router.put("/{job_id}/score-weights", response_model=ScoreWeightsOut, dependencies=[Depends(interviewer_only)])
def update_score_weights(job_id: int, payload: ScoreWeights, db: Session = Depends(get_db)):
    """Save the job's dimension weights and recalculate every overall score (no AI calls)."""
    job = get_job_or_404(db, job_id)
    job.score_weights = payload.model_dump()
    db.commit()
    count = recalculate_job_scores(db, job)
    return ScoreWeightsOut(weights=job.score_weights, is_default=False, recalculated=count)