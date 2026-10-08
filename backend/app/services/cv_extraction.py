import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, Job
from app.services.document_parser import extract_text

logger = logging.getLogger(__name__)

MIN_TEXT_CHARS = 50  # below this, the CV is treated as unreadable


def _clean(text: str) -> str:
    text = text.replace("\x00", "")  # PostgreSQL text cannot store null bytes
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def extract_candidate_text(db: Session, candidate: Candidate) -> bool:
    """Extract text from the candidate's CV (OCR for scanned pages). Returns True on success."""
    path = Path(candidate.cv_file_path) if candidate.cv_file_path else None
    if not path or not path.exists():
        return _fail(db, candidate, "CV file not found")

    try:
        text = _clean(extract_text(candidate.cv_filename or path.name, path.read_bytes()))
    except Exception as exc:
        logger.exception("Candidate %s: text extraction crashed", candidate.id)
        return _fail(db, candidate, f"Could not read the file ({exc.__class__.__name__})")

    if len(text) < MIN_TEXT_CHARS:
        return _fail(db, candidate, "No readable text found in the CV")

    candidate.cv_text = text
    candidate.extraction_status = "extracted"
    candidate.extraction_error = None
    db.commit()
    logger.info("Candidate %s: extracted %s characters from %s", candidate.id, len(text), path.name)
    return True


def _fail(db: Session, candidate: Candidate, reason: str) -> bool:
    candidate.cv_text = None
    candidate.extraction_status = "failed"
    candidate.extraction_error = reason
    db.commit()
    logger.warning("Candidate %s: text extraction failed: %s", candidate.id, reason)
    return False


def extract_pending(db: Session, job: Job) -> dict:
    """Extract text for every applied candidate of the job that hasn't been extracted yet."""
    candidates = db.scalars(
        select(Candidate).where(
            Candidate.job_id == job.id,
            Candidate.status == "applied",
            Candidate.extraction_status != "extracted",
        )
    ).all()
    extracted = sum(extract_candidate_text(db, c) for c in candidates)
    return {"processed": len(candidates), "extracted": extracted, "failed": len(candidates) - extracted}