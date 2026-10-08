import logging
from datetime import datetime, timezone
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Job
from app.services.mcp_client import MCPToolError, call_tool

logger = logging.getLogger(__name__)

EMPLOYMENT_LABELS = {
    "full_time": "Full-time",
    "part_time": "Part-time",
    "contract": "Contract",
    "internship": "Internship",
}


def apply_url_for(job: Job) -> str:
    """Pre-filled Google Form link with this job's title as the Position."""
    if not settings.google_form_prefill_url:
        return ""
    return settings.google_form_prefill_url.replace("{job_title}", quote(job.title))


def _details(job: Job) -> str:
    parts = [job.location, EMPLOYMENT_LABELS.get(job.employment_type, job.employment_type)]
    if job.min_experience_years is not None:
        parts.append(f"{job.min_experience_years}+ years experience")
    return " · ".join(p for p in parts if p)


def publish_job(db: Session, job: Job) -> bool:
    """Publish the JD to Blogger, then announce it on Telegram, via MCP tools.
    Returns True if the JD is live on Blogger."""
    apply_url = apply_url_for(job)

    if not job.posted_url:
        try:
            job.posted_url = call_tool(
                "publish_to_blogger",
                title=job.title, description=job.description, apply_url=apply_url,
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