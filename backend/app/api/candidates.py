from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Candidate, Job
from app.schemas.candidate import CandidateOut, ImportSummary, NewApplications
from app.services.cv_intake import add_uploaded_cv, new_applications, sync_applications
from app.services.mcp_client import MCPToolError
from app.services.storage import delete_file

MAX_FILES_PER_UPLOAD = 20
INTAKE_STATUSES = ("approved", "posted")

interviewer_only = Depends(require_role("interviewer"))

router = APIRouter(prefix="/candidates", tags=["candidates"], dependencies=[interviewer_only])
job_router = APIRouter(prefix="/jobs/{job_id}", tags=["candidates"], dependencies=[interviewer_only])


def _get_job(db: Session, job_id: int, for_intake: bool = False) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise AppException("Job not found", 404, "JOB_NOT_FOUND")
    if for_intake and job.status not in INTAKE_STATUSES:
        raise AppException("CVs can be added only to approved or posted jobs", 409, "JOB_NOT_OPEN")
    return job


@job_router.get("/candidates", response_model=list[CandidateOut])
def list_candidates(job_id: int, db: Session = Depends(get_db)):
    _get_job(db, job_id)
    return db.scalars(
        select(Candidate).where(Candidate.job_id == job_id).order_by(Candidate.applied_at.desc())
    ).all()


@job_router.post("/candidates/upload", response_model=ImportSummary)
def upload_cvs(job_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    job = _get_job(db, job_id, for_intake=True)
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise AppException(f"Upload at most {MAX_FILES_PER_UPLOAD} files at once", 400, "TOO_MANY_FILES")
    results = [add_uploaded_cv(db, job, f.filename, f.file.read()) for f in files]
    return ImportSummary.from_results(results)


@job_router.get("/applications/new", response_model=NewApplications)
def count_new_applications(job_id: int, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    try:
        return NewApplications(count=len(new_applications(db, job)))
    except MCPToolError:
        raise AppException("Could not check Google Form applications", 503, "SYNC_UNAVAILABLE") from None


@job_router.post("/applications/sync", response_model=ImportSummary)
def sync_job_applications(job_id: int, db: Session = Depends(get_db)):
    job = _get_job(db, job_id, for_intake=True)
    try:
        results = sync_applications(db, job)
    except MCPToolError:
        raise AppException("Could not reach Google Form applications", 503, "SYNC_UNAVAILABLE") from None
    return ImportSummary.from_results(results)


@router.delete("/{candidate_id}", status_code=204)
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise AppException("Candidate not found", 404, "CANDIDATE_NOT_FOUND")
    cv_path = candidate.cv_file_path
    db.delete(candidate)
    db.commit()
    delete_file(cv_path)