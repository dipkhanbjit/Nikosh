import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Job
from app.services.deadlines import applications_closed
from app.services.mcp_client import MCPToolError, call_tool

logger = logging.getLogger(__name__)


def update_form_state(db: Session, job: Job) -> None:
    """Open or close the job's form so it matches its status and deadline."""
    if not job.form_id:
        return
    should_accept = job.status == "posted" and not applications_closed(job)
    is_open = job.form_closed_at is None
    if should_accept == is_open:
        return
    try:
        call_tool("set_form_open", form_id=job.form_id, accepting=should_accept)
    except MCPToolError as exc:
        logger.error("Job %s: could not %s form: %s", job.id, "open" if should_accept else "close", exc)
        return
    job.form_closed_at = None if should_accept else datetime.now(timezone.utc)
    db.commit()
    logger.info("Job %s: application form %s", job.id, "reopened" if should_accept else "closed")


def check_all_forms() -> None:
    with SessionLocal() as db:
        for job in db.scalars(select(Job).where(Job.form_id.is_not(None))).all():
            update_form_state(db, job)


async def form_check_loop() -> None:
    """Background task: every few minutes, close forms past their deadline."""
    while True:
        try:
            await asyncio.to_thread(check_all_forms)
        except Exception:
            logger.exception("Form deadline check failed")
        await asyncio.sleep(settings.form_check_interval_minutes * 60)