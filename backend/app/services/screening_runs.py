import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.models import Job, ScreeningRun
from app.workflows.cv_screening import run_screening_workflow

logger = logging.getLogger(__name__)


def latest_run(db: Session, job_id: int) -> ScreeningRun | None:
    return db.scalar(
        select(ScreeningRun)
        .where(ScreeningRun.job_id == job_id)
        .order_by(ScreeningRun.id.desc())
        .limit(1)
    )


def start_screening(db: Session, job: Job) -> ScreeningRun:
    """Create a run record. The workflow itself is started in the background by the API."""
    if not job.requirements:
        raise AppException("The job has no requirements to screen against", 409, "NO_REQUIREMENTS")
    running = db.scalar(
        select(ScreeningRun.id).where(ScreeningRun.job_id == job.id, ScreeningRun.status == "running")
    )
    if running:
        raise AppException("Screening is already running for this job", 409, "SCREENING_RUNNING")
    run = ScreeningRun(job_id=job.id, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info("Job %s: screening run %s started", job.id, run.id)
    return run


def execute_run(run_id: int, job_id: int) -> None:
    """Background task: run the LangGraph workflow; record a failure if it crashes."""
    try:
        run_screening_workflow(run_id, job_id)
    except Exception as exc:
        logger.exception("Screening run %s crashed", run_id)
        with SessionLocal() as db:
            run = db.get(ScreeningRun, run_id)
            if run and run.status == "running":
                run.status = "failed"
                run.error = f"Workflow error ({exc.__class__.__name__})"
                run.finished_at = datetime.now(timezone.utc)
                db.commit()


def mark_interrupted_runs() -> None:
    """On startup: runs left 'running' by a restart can't continue, so mark them failed.
    Clicking Process CVs again screens only the CVs that are still unscreened."""
    with SessionLocal() as db:
        result = db.execute(
            update(ScreeningRun)
            .where(ScreeningRun.status == "running")
            .values(
                status="failed",
                error="Interrupted by a server restart",
                finished_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        if result.rowcount:
            logger.warning("Marked %s interrupted screening run(s) as failed", result.rowcount)