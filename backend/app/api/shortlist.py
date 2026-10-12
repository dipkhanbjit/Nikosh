import logging

from fastapi import APIRouter, Depends
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Job
from app.schemas.shortlist import (
    ShortlistItem,
    ShortlistReviewRequest,
    ShortlistStartRequest,
    ShortlistState,
)
from app.services.ranking import ranked_candidates
from app.workflows.checkpointer import get_checkpointer
from app.workflows.shortlisting import _requirement_counts, get_shortlist_graph

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/jobs/{job_id}/shortlist",
    tags=["shortlist"],
    dependencies=[Depends(require_role("interviewer"))],
)


def _config(job_id: int) -> dict:
    return {"configurable": {"thread_id": f"shortlist-job-{job_id}"}}


def _get_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise AppException("Job not found", 404, "JOB_NOT_FOUND")
    return job


def _saved_shortlist(db: Session, job: Job) -> tuple[list[ShortlistItem], int]:
    """Shortlisted candidates from the database, in rank order."""
    ranked = ranked_candidates(db, job)
    items = []
    for rank, candidate in enumerate(ranked, start=1):
        if not candidate.shortlisted:
            continue
        met, partial = _requirement_counts(candidate)
        items.append(ShortlistItem(
            candidate_id=candidate.id,
            rank=rank,
            full_name=candidate.full_name,
            email=candidate.email,
            score=candidate.overall_score,
            met=met,
            partial=partial,
        ))
    return items, len(ranked)


def _current_state(db: Session, job: Job) -> ShortlistState:
    snapshot = get_shortlist_graph().get_state(_config(job.id))
    values = snapshot.values or {}
    if "review" in snapshot.next:
        return ShortlistState(
            status="awaiting_review",
            top_n=values.get("top_n"),
            eligible_count=values.get("eligible_count", 0),
            items=values.get("items", []),
        )
    items, eligible_count = _saved_shortlist(db, job)
    return ShortlistState(
        status="approved" if items else "not_started",
        top_n=values.get("top_n"),
        eligible_count=eligible_count,
        items=items,
    )


def _run(job_id: int, graph_input) -> None:
    try:
        get_shortlist_graph().invoke(graph_input, _config(job_id))
    except Exception:
        logger.exception("Shortlist workflow failed for job %s", job_id)
        raise AppException("Shortlisting failed, please try again", 500, "SHORTLIST_ERROR") from None


@router.get("", response_model=ShortlistState)
def get_shortlist(job_id: int, db: Session = Depends(get_db)):
    return _current_state(db, _get_job(db, job_id))


@router.post("", response_model=ShortlistState)
def start_shortlist(job_id: int, payload: ShortlistStartRequest, db: Session = Depends(get_db)):
    """Apply: propose the top N ranked eligible candidates and wait for interviewer review."""
    job = _get_job(db, job_id)
    if not ranked_candidates(db, job):
        raise AppException("No eligible scored candidates to shortlist", 409, "NO_ELIGIBLE_CANDIDATES")

    get_checkpointer().delete_thread(_config(job_id)["configurable"]["thread_id"])
    _run(job_id, {"job_id": job.id, "top_n": payload.top_n, "removed_ids": []})
    return _current_state(db, job)


@router.post("/review", response_model=ShortlistState)
def review_shortlist(job_id: int, payload: ShortlistReviewRequest, db: Session = Depends(get_db)):
    """Approve the proposed shortlist, or send it back with a new N and/or removed candidates."""
    job = _get_job(db, job_id)
    if "review" not in get_shortlist_graph().get_state(_config(job_id)).next:
        raise AppException("No shortlist is waiting for review", 409, "NO_PENDING_SHORTLIST")
    if payload.action == "revise" and not payload.top_n and not payload.remove_ids:
        raise AppException("Change N or remove a candidate to revise", 422, "NOTHING_TO_REVISE")

    _run(job_id, Command(resume=payload.model_dump()))
    db.expire_all()
    return _current_state(db, job)