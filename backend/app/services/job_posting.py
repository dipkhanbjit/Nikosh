import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Job
from app.services.deadlines import deadline_label, default_deadline
from app.services.mcp_client import MCPToolError, call_tool

logger = logging.getLogger(__name__)

EMPLOYMENT_LABELS = {
    "full_time": "Full-time",
    "part_time": "Part-time",
    "contract": "Contract",
    "internship": "Internship",
}


def apply_url_for(job: Job) -> str:
    """The job's own Google Form link."""
    return job.form_url or ""


def form_title(job: Job) -> str:
    return f"{settings.company_name} - {job.title}"


def _details(job: Job) -> str:
    parts = [job.location, EMPLOYMENT_LABELS.get(job.employment_type, job.employment_type)]
    if job.min_experience_years is not None:
        parts.append(f"{job.min_experience_years}+ years experience")
    if job.application_deadline:
        parts.append(f"Apply by {deadline_label(job)}")
    return " · ".join(p for p in parts if p)


def _form_description(job: Job) -> str:
    return (
        f"{_details(job)}\n\n"
        "Please enter the email address where we can contact you, and upload your CV "
        "(PDF or Word, max 10 MB)."
    )


def _ensure_form(db: Session, job: Job) -> bool:
    """Create the job's application form once. Returns True if the form exists."""
    if job.form_id:
        return True
    try:
        form = json.loads(
            call_tool("create_job_form", title=form_title(job), description=_form_description(job))
        )
    except (MCPToolError, ValueError) as exc:
        job.form_error = str(exc)[:500]
        db.commit()
        logger.error("Job %s: form creation failed: %s", job.id, exc)
        return False
    job.form_id = form["form_id"]
    job.form_url = form["form_url"]
    job.form_error = None
    job.form_closed_at = None
    db.commit()
    logger.info("Job %s: application form created: %s", job.id, job.form_url)
    return True


def publish_job(db: Session, job: Job) -> bool:
    """Create the job's form, publish the JD to Blogger, then announce it on Telegram,
    all via MCP tools. Returns True if the JD is live on Blogger."""
    if not job.application_deadline:
        job.application_deadline = default_deadline(datetime.now(timezone.utc))
        db.commit()
        logger.info("Job %s: default application deadline set to %s", job.id, deadline_label(job))

    if not _ensure_form(db, job):
        return False
    apply_url = apply_url_for(job)

    if not job.posted_url:
        try:
            job.posted_url = call_tool(
                "publish_to_blogger",
                title=job.title,
                description=job.description,
                apply_url=apply_url,
                deadline=deadline_label(job),
            )
        except MCPToolError as exc:
            job.posting_error = str(exc)[:500]
            db.commit()
            logger.error("Job %s: Blogger posting failed: %s", job.id, exc)
            return False
        job.status = "posted"
        job.posted_at = datetime.now(timezone.utc)
        job.posting_error = None
        db.commit()
        logger.info("Job %s: posted to Blogger: %s", job.id, job.posted_url)

    if not job.telegram_url:
        try:
            job.telegram_url = call_tool(
                "publish_to_telegram",
                title=job.title, details=_details(job), link=job.posted_url, apply_url=apply_url,
            )
            job.telegram_error = None
            job.telegram_posted_at = datetime.now(timezone.utc)
            logger.info("Job %s: announced on Telegram: %s", job.id, job.telegram_url)
        except MCPToolError as exc:
            job.telegram_error = str(exc)[:500]
            logger.error("Job %s: Telegram posting failed: %s", job.id, exc)
        db.commit()

    return True