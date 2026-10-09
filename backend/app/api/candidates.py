import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Candidate, Job
from app.schemas.candidate import (
    CandidateOut,
    CandidateText,
    ImportSummary,
    NewApplications,
    ScreeningRunOut,
)
from app.services.cv_intake import add_uploaded_cv, new_applications, sync_applications
from app.services.deadlines import applications_closed, deadline_label
from app.services.mcp_client import MCPToolError
from app.services.ranking import ranked_candidates
from app.services.screening_runs import execute_run, latest_run, start_screening
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


def _get_candidate(db: Session, candidate_id: int) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise AppException("Candidate not found", 404, "CANDIDATE_NOT_FOUND")
    return candidate


@job_router.get("/candidates", response_model=list[CandidateOut])
def list_candidates(job_id: int, db: Session = Depends(get_db)):
    """Ranked (eligible + screened) candidates first, then everyone else, newest first."""
    job = _get_job(db, job_id)
    ranked = ranked_candidates(db, job)
    for position, candidate in enumerate(ranked, start=1):
        candidate.rank = position
    ranked_ids = {c.id for c in ranked}
    others = db.scalars(
        select(Candidate).where(Candidate.job_id == job_id).order_by(Candidate.applied_at.desc())
    ).all()
    return ranked + [c for c in others if c.id not in ranked_ids]


@job_router.post("/candidates/upload", response_model=ImportSummary)
def upload_cvs(job_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    job = _get_job(db, job_id, for_intake=True)
    if applications_closed(job):
        raise AppException(f"Applications closed on {deadline_label(job)}", 409, "APPLICATIONS_CLOSED")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise AppException(f"Upload at most {MAX_FILES_PER_UPLOAD} files at once", 400, "TOO_MANY_FILES")
    results = [add_uploaded_cv(db, job, f.filename, f.file.read()) for f in files]
    return ImportSummary.from_results(results)


@job_router.post("/screening", response_model=ScreeningRunOut, status_code=202)
def start_job_screening(job_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Start the LangGraph screening workflow in the background; returns the run to poll."""
    job = _get_job(db, job_id)
    run = start_screening(db, job)
    background_tasks.add_task(execute_run, run.id, job.id)
    return run


@job_router.get("/screening", response_model=ScreeningRunOut | None)
def get_job_screening(job_id: int, db: Session = Depends(get_db)):
    """Latest screening run of the job (progress while running), or null if none yet."""
    _get_job(db, job_id)
    return latest_run(db, job_id)


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


@router.get("/{candidate_id}/text", response_model=CandidateText)
def get_cv_text(candidate_id: int, db: Session = Depends(get_db)):
    return _get_candidate(db, candidate_id)


@router.get("/{candidate_id}/cv")
def view_cv(candidate_id: int, db: Session = Depends(get_db)):
    candidate = _get_candidate(db, candidate_id)
    if not candidate.cv_file_path or not Path(candidate.cv_file_path).exists():
        raise AppException("CV file not found", 404, "CV_NOT_FOUND")
    media_type = mimetypes.guess_type(candidate.cv_filename or candidate.cv_file_path)[0]
    return FileResponse(
        candidate.cv_file_path,
        media_type=media_type or "application/octet-stream",
        filename=candidate.cv_filename,
        content_disposition_type="inline",
    )


@router.delete("/{candidate_id}", status_code=204)
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)):
    candidate = _get_candidate(db, candidate_id)
    cv_path = candidate.cv_file_path
    db.delete(candidate)
    db.commit()
    delete_file(cv_path)