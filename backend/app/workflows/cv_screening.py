import logging
import operator
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Candidate, Job, ScreeningRun
from app.services.candidate_scoring import score_candidate
from app.services.cv_extraction import extract_candidate_text
from app.services.cv_matching import screen_candidate
from app.services.cv_parsing import parse_candidate
from app.workflows.checkpointer import get_checkpointer

logger = logging.getLogger(__name__)


class ScreeningState(TypedDict):
    run_id: int
    job_id: int
    candidate_ids: list[int]
    results: Annotated[list[dict], operator.add]  # each parallel branch appends its result


class CVTask(TypedDict):
    run_id: int
    job_id: int
    candidate_id: int


# ---------- Nodes ----------

def load_candidates(state: ScreeningState) -> dict:
    """Find the job's applicants that still need screening or scoring, and record the total."""
    with SessionLocal() as db:
        ids = list(db.scalars(
            select(Candidate.id)
            .where(
                Candidate.job_id == state["job_id"],
                Candidate.status == "applied",
                or_(Candidate.screening_status != "screened", Candidate.scoring_status != "scored"),
            )
            .order_by(Candidate.applied_at)
        ))
        db.execute(update(ScreeningRun).where(ScreeningRun.id == state["run_id"]).values(total=len(ids)))
        db.commit()
    logger.info("Screening run %s: %s CV(s) to process for job %s", state["run_id"], len(ids), state["job_id"])
    return {"candidate_ids": ids}


def dispatch(state: ScreeningState):
    """Fan out: one parallel screen_cv branch per CV (or go straight to finalize)."""
    if not state["candidate_ids"]:
        return "finalize"
    return [
        Send("screen_cv", {"run_id": state["run_id"], "job_id": state["job_id"], "candidate_id": cid})
        for cid in state["candidate_ids"]
    ]


def _prepare(db: Session, candidate: Candidate) -> str | None:
    """Make sure the CV has text and a profile. Returns an error message, or None if ready."""
    if candidate.extraction_status != "extracted":
        extract_candidate_text(db, candidate)
        if candidate.extraction_status != "extracted":
            return candidate.extraction_error or "Text extraction failed"
    if candidate.parse_status != "parsed":
        parse_candidate(db, candidate)
        if candidate.parse_status != "parsed":
            return candidate.parse_error or "Profile parsing failed"
    return None


def _process(db: Session, job: Job, candidate: Candidate) -> str | None:
    """Prepare → match requirements → (if still eligible) score. Returns an error or None."""
    error = _prepare(db, candidate)
    if error:
        return error
    if candidate.screening_status != "screened":
        if not screen_candidate(db, job, candidate):
            return candidate.screening_error or "Screening failed"
    if candidate.status == "applied":  # excluded candidates are not scored
        if not score_candidate(db, job, candidate):
            return candidate.scoring_error or "Scoring failed"
    return None


def screen_cv(task: CVTask) -> dict:
    """Screen and score one CV. A failure only affects this CV; the other branches continue."""
    error = None
    with SessionLocal() as db:
        candidate = db.get(Candidate, task["candidate_id"])
        job = db.get(Job, task["job_id"])
        try:
            if candidate is None or job is None:
                error = "Candidate or job no longer exists"
            else:
                error = _process(db, job, candidate)
        except Exception as exc:
            db.rollback()
            error = f"Unexpected error ({exc.__class__.__name__})"
            logger.exception("Screening run %s: candidate %s failed", task["run_id"], task["candidate_id"])
            if candidate is not None:
                candidate.screening_status = "failed"
                candidate.screening_error = error
                db.commit()

        ok = error is None
        db.execute(
            update(ScreeningRun)
            .where(ScreeningRun.id == task["run_id"])
            .values(
                processed=ScreeningRun.processed + 1,
                succeeded=ScreeningRun.succeeded + int(ok),
                failed=ScreeningRun.failed + int(not ok),
            )
        )
        db.commit()
    return {"results": [{"candidate_id": task["candidate_id"], "ok": ok, "error": error}]}


def finalize(state: ScreeningState) -> dict:
    """Mark the run completed. Ranking is read from the stored scores."""
    with SessionLocal() as db:
        run = db.get(ScreeningRun, state["run_id"])
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "Screening run %s completed: %s succeeded, %s failed of %s",
            run.id, run.succeeded, run.failed, run.total,
        )
    return {}


# ---------- Graph ----------

def _build_graph():
    builder = StateGraph(ScreeningState)
    builder.add_node("load_candidates", load_candidates)
    builder.add_node("screen_cv", screen_cv)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "load_candidates")
    builder.add_conditional_edges("load_candidates", dispatch, ["screen_cv", "finalize"])
    builder.add_edge("screen_cv", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=get_checkpointer())


_graph = None


def get_screening_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def run_screening_workflow(run_id: int, job_id: int) -> None:
    """Run the whole workflow (called in the background). At most N CVs run at once."""
    config = {
        "configurable": {"thread_id": f"screening-run-{run_id}"},
        "max_concurrency": settings.screening_concurrency,
    }
    get_screening_graph().invoke(
        {"run_id": run_id, "job_id": job_id, "candidate_ids": [], "results": []},
        config,
    )