from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Job, User
from app.schemas.job import JobCreate, JobOut, JobUpdate
from app.services.deadlines import end_of_day
from app.services.job_posting import publish_job
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
    """Open jobs must have unique titles, because form applications are matched by title."""
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
                "The title of a posted job cannot be changed, because applications are matched by title",
                409,
                "JOB_ALREADY_POSTED",
            )
        ensure_unique_title(db, new_title, exclude_id=job.id)
    if "application_deadline" in changes:
        deadline = changes.pop("application_deadline")
        job.application_deadline = end_of_day(deadline) if deadline else None
    for field, value in changes.items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=204, dependencies=[Depends(interviewer_only)])
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    cv_paths = [c.cv_file_path for c in job.candidates]
    db.delete(job)
    db.commit()
    for path in cv_paths:
        delete_file(path)


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