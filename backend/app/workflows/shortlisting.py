import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Candidate, Interview, Job
from app.models.interview import ACTIVE_STATUSES
from app.services.ranking import ranked_candidates
from app.workflows.checkpointer import get_checkpointer

logger = logging.getLogger(__name__)


class ShortlistGraphState(TypedDict, total=False):
    job_id: int
    top_n: int
    removed_ids: list[int]
    items: list[dict]
    eligible_count: int


def _requirement_counts(candidate: Candidate) -> tuple[int, int]:
    ratings = [m.get("rating") for m in (candidate.screening or [])]
    return ratings.count("met"), ratings.count("partial")


def propose(state: ShortlistGraphState) -> dict:
    """Pick the top N ranked eligible candidates, skipping those the interviewer removed."""
    removed = set(state.get("removed_ids") or [])
    with SessionLocal() as db:
        job = db.get(Job, state["job_id"])
        ranked = ranked_candidates(db, job)
        items = []
        for rank, candidate in enumerate(ranked, start=1):
            if candidate.id in removed:
                continue
            met, partial = _requirement_counts(candidate)
            items.append({
                "candidate_id": candidate.id,
                "rank": rank,
                "full_name": candidate.full_name,
                "email": candidate.email,
                "score": candidate.overall_score,
                "met": met,
                "partial": partial,
            })
            if len(items) == state["top_n"]:
                break

    logger.info("Shortlist proposed for job %s: %s candidates", state["job_id"], len(items))
    return {"items": items, "eligible_count": len(ranked)}


def review(state: ShortlistGraphState) -> Command[Literal["propose", "save"]]:
    decision = interrupt({"items": state["items"], "top_n": state["top_n"]})
    if decision["action"] == "revise":
        removed = set(state.get("removed_ids") or []) | set(decision.get("remove_ids") or [])
        return Command(
            goto="propose",
            update={
                "top_n": decision.get("top_n") or state["top_n"],
                "removed_ids": sorted(removed),
            },
        )
    return Command(goto="save")


def save(state: ShortlistGraphState) -> dict:
    """Mark the approved candidates as shortlisted. Earlier shortlisted candidates who are no
    longer in the list are un-shortlisted, unless they already have an active interview."""
    approved = {item["candidate_id"] for item in state["items"]}
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        candidates = db.scalars(select(Candidate).where(Candidate.job_id == state["job_id"])).all()
        active = set(db.scalars(
            select(Interview.candidate_id).where(
                Interview.job_id == state["job_id"], Interview.status.in_(ACTIVE_STATUSES)
            )
        ).all())
        for candidate in candidates:
            if candidate.id in approved:
                if not candidate.shortlisted:
                    candidate.shortlisted_at = now
                candidate.shortlisted = True
            elif candidate.shortlisted and candidate.id not in active:
                candidate.shortlisted = False
                candidate.shortlisted_at = None
        db.commit()
    logger.info("Shortlist approved for job %s: %s candidates", state["job_id"], len(approved))
    return {}


@lru_cache
def get_shortlist_graph():
    builder = StateGraph(ShortlistGraphState)
    builder.add_node("propose", propose)
    builder.add_node("review", review)
    builder.add_node("save", save)
    builder.add_edge(START, "propose")
    builder.add_edge("propose", "review")
    builder.add_edge("save", END)
    return builder.compile(checkpointer=get_checkpointer())