import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Candidate, Job
from app.services.cv_extraction import extract_candidate_text
from app.services.cv_parsing import parse_candidate
from app.services.deadlines import applications_closed, deadline_label
from app.services.mcp_client import MCPToolError, call_tool
from app.services.storage import delete_file

logger = logging.getLogger(__name__)

ALLOWED_CV_EXTENSIONS = {".pdf", ".docx"}
FORM_TIMEZONE = timezone(timedelta(hours=6))  # Google Form timestamps are in Dhaka time


def validate_cv(filename: str, size: int) -> str | None:
    """Return a rejection reason, or None if the file is acceptable."""
    if Path(filename).suffix.lower() not in ALLOWED_CV_EXTENSIONS:
        return "Unsupported file type (only PDF and DOCX are accepted)"
    if size == 0:
        return "File is empty"
    if size > settings.cv_max_file_mb * 1024 * 1024:
        return f"File is larger than {settings.cv_max_file_mb} MB"
    return None


def process_cv(db: Session, candidate: Candidate) -> None:
    """Extract the CV text, then parse it into a structured profile."""
    if extract_candidate_text(db, candidate):
        parse_candidate(db, candidate)


def _job_dir(job_id: int) -> Path:
    path = Path(settings.cv_storage_dir) / f"job_{job_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stored_name(filename: str) -> str:
    safe = re.sub(r"[^\w.\-]", "_", Path(filename).name)
    return f"{uuid.uuid4().hex[:12]}_{safe}"


def _parse_submitted_at(value: str | None) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value).replace(tzinfo=FORM_TIMEZONE)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _original_filename(drive_name: str) -> str:
    """Google Forms renames uploads to '<original> - <uploader name>.<ext>'; undo that."""
    path = Path(drive_name)
    stem = path.stem.rsplit(" - ", 1)[0] if " - " in path.stem else path.stem
    return f"{stem}{path.suffix}"


def _commit_candidate(db: Session, candidate: Candidate, stored_path: Path | None = None) -> bool:
    """Save a form candidate; returns False if another sync imported it first."""
    db.add(candidate)
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        delete_file(str(stored_path) if stored_path else None)
        return False


# ---------- Channel 1: manual upload ----------

def add_uploaded_cv(db: Session, job: Job, filename: str, data: bytes) -> dict:
    reason = validate_cv(filename, len(data))
    if reason:
        logger.warning("Job %s: rejected upload %s: %s", job.id, filename, reason)
        return {"filename": filename, "status": "rejected", "reason": reason}

    path = _job_dir(job.id) / _stored_name(filename)
    path.write_bytes(data)
    candidate = Candidate(
        job_id=job.id,
        cv_file_path=str(path),
        cv_filename=filename,
        source="upload",
        applied_at=datetime.now(timezone.utc),
    )
    db.add(candidate)
    db.commit()
    logger.info("Job %s: imported upload %s as candidate %s", job.id, filename, candidate.id)
    process_cv(db, candidate)
    return {"filename": filename, "status": "imported", "candidate_id": candidate.id}


# ---------- Channel 2: Google Form sync (via MCP tools) ----------

def new_applications(db: Session, job: Job) -> list[dict]:
    """Form applications for this job that have not been imported yet."""
    applications = json.loads(call_tool("list_job_applications", job_title=job.title))
    file_ids = [a["file_id"] for a in applications]
    if not file_ids:
        return []
    imported = set(db.scalars(
        select(Candidate.source_file_id).where(Candidate.source_file_id.in_(file_ids))
    ))
    return [a for a in applications if a["file_id"] not in imported]


def _reject_late(db: Session, job: Job, app: dict, submitted_at: datetime) -> dict | None:
    """Record an application submitted after the deadline without downloading its CV."""
    reason = f"Applied after the deadline ({deadline_label(job)})"
    candidate = Candidate(
        job_id=job.id,
        full_name=app.get("full_name"),
        email=app.get("email"),
        phone=app.get("phone"),
        source="form",
        source_file_id=app["file_id"],
        applied_at=submitted_at,
        status="rejected",
        rejection_reason=reason,
    )
    if not _commit_candidate(db, candidate):
        return None
    label = app.get("full_name") or app["file_id"]
    logger.warning("Job %s: rejected late application from %s: %s", job.id, label, reason)
    return {"filename": label, "status": "rejected", "reason": reason}


def sync_applications(db: Session, job: Job) -> list[dict]:
    """Import every new form application for the job. Returns per-file results."""
    results = []
    for app in new_applications(db, job):
        label = app.get("full_name") or app["file_id"]
        submitted_at = _parse_submitted_at(app.get("submitted_at"))

        if applications_closed(job, submitted_at):
            result = _reject_late(db, job, app, submitted_at)
            if result:
                results.append(result)
            continue

        try:
            info = json.loads(call_tool("download_cv", file_id=app["file_id"]))
        except MCPToolError as exc:
            logger.error("Job %s: download failed for %s: %s", job.id, label, exc)
            results.append({"filename": label, "status": "failed", "reason": "Could not download CV"})
            continue

        incoming = Path(info["path"])
        filename = _original_filename(info["filename"])
        reason = validate_cv(filename, info["size"])
        stored_path = None
        if reason:
            delete_file(str(incoming))
        else:
            stored_path = _job_dir(job.id) / _stored_name(filename)
            shutil.move(incoming, stored_path)

        candidate = Candidate(
            job_id=job.id,
            full_name=app.get("full_name"),
            email=app.get("email"),
            phone=app.get("phone"),
            cv_file_path=str(stored_path) if stored_path else None,
            cv_filename=filename,
            source="form",
            source_file_id=app["file_id"],
            applied_at=submitted_at,
            status="rejected" if reason else "applied",
            rejection_reason=reason,
        )
        if not _commit_candidate(db, candidate, stored_path):
            continue  # imported concurrently by another sync

        if reason:
            logger.warning("Job %s: rejected form CV %s: %s", job.id, filename, reason)
            results.append({"filename": filename, "status": "rejected", "reason": reason})
        else:
            logger.info("Job %s: imported form CV %s as candidate %s", job.id, filename, candidate.id)
            process_cv(db, candidate)
            results.append({"filename": filename, "status": "imported", "candidate_id": candidate.id})
    return results