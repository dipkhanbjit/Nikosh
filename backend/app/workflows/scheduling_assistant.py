import json
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.models import Candidate, Interview, Job
from app.models.interview import ACTIVE_STATUSES
from app.services.ics import DHAKA
from app.services.interviews import create_interview
from app.services.llm import get_llm
from app.services.ranking import ranked_candidates
from app.services.schedule_planner import ScheduleIntent, build_plan, recheck_item, rules_from_settings
from app.workflows.checkpointer import get_checkpointer

logger = logging.getLogger(__name__)

MAX_REASON_LENGTH = 150


class SchedulingGraphState(TypedDict, total=False):
    job_id: int
    message: str
    intent: dict | None  # ScheduleIntent of the last successful message
    plan: dict | None  # {items, skipped, message, question}
    llm_failed: bool
    user_id: int | None  # interviewer who confirmed
    results: list[dict] | None  # one ScheduleResult per planned item, after confirm


def _prompt(shortlisted: list, current: dict | None, plan: dict | None, now: datetime) -> str:
    today = now.astimezone(DHAKA)
    lines = [
        "You turn an interviewer's instruction into interview scheduling fields.",
        f"Today is {today:%A %Y-%m-%d}, {today:%H:%M}, timezone Asia/Dhaka (GMT+6).",
        "Resolve words like 'tomorrow' or 'Monday' (the next one) to YYYY-MM-DD. "
        "Write times as 24-hour HH:MM.",
        "Put a candidate in 'candidates' only when they get their own time, day or email.",
        "Leave a field empty when it is not given. Never invent dates, times or emails.",
        "Shortlisted candidates in rank order: "
        + "; ".join(f"{rank}. {c.full_name}" for rank, c in enumerate(shortlisted, start=1)),
    ]
    if current:
        lines += [
            "The new message changes the current request. Return the full updated request "
            "and change only what the message asks.",
            "Current request: " + json.dumps(current),
        ]
        if plan and plan.get("question"):
            lines.append("Your last question: " + plan["question"])
        elif plan:
            lines.append("Current plan (in time order): " + "; ".join(
                f"{item['name']} at {item['start']}" for item in plan["items"]
            ))
    return "\n".join(lines)


def _read_intent(message: str, shortlisted: list, state: SchedulingGraphState, now: datetime) -> ScheduleIntent:
    """The one Gemini call per message: instruction -> ScheduleIntent."""
    llm = get_llm(temperature=0).with_structured_output(ScheduleIntent)
    prompt = _prompt(shortlisted, state.get("intent"), state.get("plan"), now)
    intent = llm.invoke([("system", prompt), ("human", message)])
    if intent is None:
        raise ValueError("Gemini returned no structured output")
    return intent


def _busy_slots(db) -> list[tuple[datetime, datetime]]:
    """One interviewer: active interviews of every job block their slots."""
    return [
        (i.scheduled_at.astimezone(DHAKA),
         (i.scheduled_at + timedelta(minutes=i.duration_minutes)).astimezone(DHAKA))
        for i in db.scalars(select(Interview).where(Interview.status.in_(ACTIVE_STATUSES)))
    ]


def plan(state: SchedulingGraphState) -> dict:
    job_id = state["job_id"]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        shortlisted = [c for c in ranked_candidates(db, job) if c.shortlisted]
        active_ids = set(db.scalars(
            select(Interview.candidate_id).where(
                Interview.job_id == job_id, Interview.status.in_(ACTIVE_STATUSES)
            )
        ).all())
        busy = _busy_slots(db)
        try:
            intent = _read_intent(state["message"], shortlisted, state, now)
        except Exception as exc:
            # Keep the previous plan; the API reports the failure
            logger.error("Scheduling assistant: Gemini failed for job %s: %s", job_id, exc.__class__.__name__)
            return {"llm_failed": True}
        result = build_plan(intent, shortlisted, active_ids, busy, now, rules_from_settings())

    logger.info(
        "Scheduling assistant job %s: %s planned, %s skipped, question=%s",
        job_id, len(result["items"]), len(result["skipped"]), bool(result["question"]),
    )
    return {"intent": intent.model_dump(), "plan": result, "llm_failed": False}


def review(state: SchedulingGraphState) -> Command[Literal["plan", "execute", "__end__"]]:
    decision = interrupt({"plan": state.get("plan")})
    if decision["action"] == "revise":
        return Command(goto="plan", update={"message": decision["message"]})
    if decision["action"] == "confirm":
        return Command(goto="execute", update={"user_id": decision["user_id"]})
    return Command(goto=END)


def _schedule_one(db, job: Job, item: dict, user_id: int) -> tuple[str, str | None, int | None]:
    """Schedule one planned item with the same service as the Schedule button.
    Returns (status, reason, interview_id)."""
    try:
        interview, _, _ = create_interview(
            db, job, item["candidate_id"], datetime.fromisoformat(item["start"]), item["duration_min"],
            created_by=user_id, contact_email=item["email"],
        )
    except AppException as exc:
        db.rollback()
        return "failed", exc.message, None
    except Exception:
        db.rollback()
        logger.exception("Scheduling assistant job %s: candidate %s failed", job.id, item["candidate_id"])
        return "failed", "Unexpected error, please schedule manually", None
    if interview.invitation_status == "failed":
        error = (interview.invitation_error or "Invitation not sent")[:MAX_REASON_LENGTH]
        return "failed", f"{error}. Use Resend.", interview.id
    return "sent", None, interview.id


def execute(state: SchedulingGraphState) -> dict:
    """Re-check every planned item in code, then schedule and invite them one by one (no LLM)."""
    job_id = state["job_id"]
    results = []
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        shortlisted_ids = set(db.scalars(
            select(Candidate.id).where(Candidate.job_id == job_id, Candidate.shortlisted.is_(True))
        ).all())
        active_ids = set(db.scalars(
            select(Interview.candidate_id).where(Interview.status.in_(ACTIVE_STATUSES))
        ).all())
        busy = _busy_slots(db)
        for item in state["plan"]["items"]:
            start = datetime.fromisoformat(item["start"])
            reason = recheck_item(item, shortlisted_ids, active_ids, busy, datetime.now(timezone.utc))
            if reason:
                status, interview_id = "skipped", None
            else:
                status, reason, interview_id = _schedule_one(db, job, item, state["user_id"])
                if interview_id:
                    active_ids.add(item["candidate_id"])
                    busy.append((start, start + timedelta(minutes=item["duration_min"])))
            results.append({
                "candidate_id": item["candidate_id"], "name": item["name"], "start": item["start"],
                "status": status, "reason": reason, "interview_id": interview_id,
            })

    counts = {s: sum(r["status"] == s for r in results) for s in ("sent", "failed", "skipped")}
    logger.info(
        "Scheduling assistant job %s confirmed: %s sent, %s failed, %s skipped, interviews %s",
        job_id, counts["sent"], counts["failed"], counts["skipped"],
        [r["interview_id"] for r in results if r["interview_id"]],
    )
    return {"results": results}


@lru_cache
def get_scheduling_graph():
    builder = StateGraph(SchedulingGraphState)
    builder.add_node("plan", plan)
    builder.add_node("review", review)
    builder.add_node("execute", execute)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "review")
    builder.add_edge("execute", END)
    return builder.compile(checkpointer=get_checkpointer())
