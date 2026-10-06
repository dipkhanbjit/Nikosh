from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Job, User
from app.schemas.job import JobCreate, JobOut, JobUpdate
from app.services.storage import delete_file

router = APIRouter(prefix="/jobs", tags=["jobs"])
interviewer_only = require_role("interviewer")


def get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise AppException("Job not found", 404, "JOB_NOT_FOUND")
    return job


@router.post("", response_model=JobOut, status_code=201)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(interviewer_only),
):
    job = Job(**payload.model_dump(), created_by=user.id)
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
    for field, value in payload.model_dump(exclude_unset=True).items():
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