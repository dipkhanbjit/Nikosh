import hashlib
import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
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
DUPLICATE_EMAIL = "Already applied for this job"
DUPLICATE_CV = "Same CV already submitted for this job"


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


def _file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_email(value: str | None) -> str | None:
    return value.strip().lower() if value and value.strip() else None


def _parse_submitted_at(value: str | None) -> datetime:
    """Google Forms API timestamps are RFC 3339 in UTC (e.g. 2026-10-09T10:15:00.123Z)."""
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _original_filename(drive_name: str) -> str:
    """Google Forms renames uploads to '<original> - <uploader name>.<ext>'; undo that."""
    path = Path(drive_name)
    stem = path.stem.rsplit(" - ", 1)[0] if " - " in path.stem else path.stem
    return f"{stem}{path.suffix}"


def _is_duplicate_email(db: Session, job: Job, email: str | None) -> bool:
    if not email:
        return False
    return db.scalar(
        select(Candidate.id).where(
            Candidate.job_id == job.id,
            Candidate.status == "applied",
            func.lower(Candidate.email) == email,
        ).limit(1)
    ) is not None


def _is_duplicate_cv(db: Session, job: Job, cv_hash: str) -> bool:
    return db.scalar(
        select(Candidate.id).where(
            Candidate.job_id == job.id,
            Candidate.status == "applied",
            Candidate.cv_hash == cv_hash,
        ).limit(1)
    ) is not None


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
    cv_hash = _file_hash(data)
    if not reason and _is_duplicate_cv(db, job, cv_hash):
        reason = DUPLICATE_CV
    if reason:
        logger.warning("Job %s: rejected upload %s: %s", job.id, filename, reason)
        return {"filename": filename, "status": "rejected", "reason": reason}

    path = _job_dir(job.id) / _stored_name(filename)
    path.write_bytes(data)
    candidate = Candidate(
        job_id=job.id,
        cv_file_path=str(path),
        cv_filename=filename,
        cv_hash=cv_hash,
        source="upload",
        applied_at=datetime.now(timezone.utc),
    )
    db.add(candidate)
    db.commit()
    logger.info("Job %s: imported upload %s as candidate %s", job.id, filename, candidate.id)
    process_cv(db, candidate)
    return {"filename": filename, "status": "imported", "candidate_id": candidate.id}


# ---------- Channel 2: the job's own Google Form (via MCP tools) ----------

def _source_id(app: dict) -> str:
    """Unique id of a form submission: the uploaded CV's Drive file id."""
    return app.get("cv_file_id") or app["response_id"]


def new_applications(db: Session, job: Job) -> list[dict]:
    """Responses to this job's form that have not been imported yet (oldest first)."""
    if not job.form_id:
        return []
    applications = json.loads(call_tool("list_job_applications", form_id=job.form_id))
    ids = [_source_id(a) for a in applications]
    if not ids:
        return []
    imported = set(db.scalars(
        select(Candidate.source_file_id).where(Candidate.source_file_id.in_(ids))
    ))
    new = [a for a in applications if _source_id(a) not in imported]
    return sorted(new, key=lambda a: a.get("submitted_at") or "")


def _reject_form_application(
    db: Session, job: Job, app: dict, submitted_at: datetime, reason: str,
    filename: str | None = None, cv_hash: str | None = None,
) -> dict | None:
    """Record a rejected form application (kept for the log; its CV is not stored)."""
    candidate = Candidate(
        job_id=job.id,
        full_name=app.get("full_name"),
        email=_normalize_email(app.get("email")),
        phone=app.get("phone"),
        cv_filename=filename,
        cv_hash=cv_hash,
        source="form",
        source_file_id=_source_id(app),
        applied_at=submitted_at,
        status="rejected",
        rejection_reason=reason,
    )
    if not _commit_candidate(db, candidate):
        return None
    label = app.get("full_name") or filename or _source_id(app)
    logger.warning("Job %s: rejected application from %s: %s", job.id, label, reason)
    return {"filename": label, "status": "rejected", "reason": reason}


def sync_applications(db: Session, job: Job) -> list[dict]:
    """Import every new response from the job's form. Returns per-application results."""
    results = []
    for app in new_applications(db, job):
        label = app.get("full_name") or _source_id(app)
        submitted_at = _parse_submitted_at(app.get("submitted_at"))
        email = _normalize_email(app.get("email"))

        # Checks that need no download
        reason = None
        if applications_closed(job, submitted_at):
            reason = f"Applied after the deadline ({deadline_label(job)})"
        elif _is_duplicate_email(db, job, email):
            reason = DUPLICATE_EMAIL
        elif not app.get("cv_file_id"):
            reason = "No CV was uploaded"
        if reason:
            result = _reject_form_application(db, job, app, submitted_at, reason)
            if result:
                results.append(result)
            continue

        try:
            info = json.loads(call_tool("download_cv", file_id=app["cv_file_id"]))
        except (MCPToolError, ValueError) as exc:
            logger.error("Job %s: download failed for %s: %s", job.id, label, exc)
            results.append({"filename": label, "status": "failed", "reason": "Could not download CV"})
            continue

        incoming = Path(info["path"])
        filename = _original_filename(info["filename"])
        reason = validate_cv(filename, info["size"])
        cv_hash = None
        if not reason:
            cv_hash = _file_hash(incoming.read_bytes())
            if _is_duplicate_cv(db, job, cv_hash):
                reason = DUPLICATE_CV

        if reason:
            delete_file(str(incoming))
            result = _reject_form_application(db, job, app, submitted_at, reason, filename, cv_hash)
            if result:
                results.append(result)
            continue

        stored_path = _job_dir(job.id) / _stored_name(filename)
        shutil.move(incoming, stored_path)
        candidate = Candidate(
            job_id=job.id,
            full_name=app.get("full_name"),
            email=email,
            phone=app.get("phone"),
            cv_file_path=str(stored_path),
            cv_filename=filename,
            cv_hash=cv_hash,
            source="form",
            source_file_id=_source_id(app),
            applied_at=submitted_at,
            status="applied",
        )
        if not _commit_candidate(db, candidate, stored_path):
            continue  # imported concurrently by another sync

        logger.info("Job %s: imported form CV %s as candidate %s", job.id, filename, candidate.id)
        process_cv(db, candidate)
        results.append({"filename": filename, "status": "imported", "candidate_id": candidate.id})
    return results