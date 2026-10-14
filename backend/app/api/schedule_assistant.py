import logging
import threading

from fastapi import APIRouter, Depends
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Candidate, Job, User
from app.schemas.schedule_assistant import AssistantMessage, AssistantState
from app.workflows.checkpointer import get_checkpointer
from app.workflows.scheduling_assistant import get_scheduling_graph

logger = logging.getLogger(__name__)

# Jobs with a confirm in progress (single worker): a second click gets 409
_confirming: set[int] = set()
_confirming_lock = threading.Lock()

router = APIRouter(
    prefix="/jobs/{job_id}/schedule-assistant",
    tags=["schedule-assistant"],
    dependencies=[Depends(require_role("interviewer"))],
)


def _thread_id(job_id: int) -> str:
    return f"schedule-assistant-job-{job_id}"


def _config(job_id: int) -> dict:
    return {"configurable": {"thread_id": _thread_id(job_id)}}


def _get_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise AppException("Job not found", 404, "JOB_NOT_FOUND")
    return job


def _is_open(job_id: int) -> bool:
    return "review" in get_scheduling_graph().get_state(_config(job_id)).next


def _current_state(job_id: int) -> AssistantState:
    snapshot = get_scheduling_graph().get_state(_config(job_id))
    plan = (snapshot.values or {}).get("plan") if "review" in snapshot.next else None
    if not plan:
        return AssistantState(status="none")
    if plan["question"]:
        return AssistantState(status="question", skipped=plan["skipped"], message=plan["question"])
    return AssistantState(status="plan", items=plan["items"], skipped=plan["skipped"], message=plan["message"])


@router.get("", response_model=AssistantState)
def get_assistant(job_id: int, db: Session = Depends(get_db)):
    _get_job(db, job_id)
    return _current_state(job_id)


@router.post("/messages", response_model=AssistantState)
def send_message(job_id: int, payload: AssistantMessage, db: Session = Depends(get_db)):
    """New instruction (starts a thread) or a change to the open plan (revise)."""
    _get_job(db, job_id)
    has_shortlist = db.scalar(
        select(Candidate.id).where(Candidate.job_id == job_id, Candidate.shortlisted.is_(True)).limit(1)
    )
    if not has_shortlist:
        raise AppException("Approve a shortlist before scheduling", 409, "NO_SHORTLIST")

    graph = get_scheduling_graph()
    is_revise = _is_open(job_id)
    if is_revise:
        graph_input = Command(resume={"action": "revise", "message": payload.text})
    else:
        get_checkpointer().delete_thread(_thread_id(job_id))
        graph_input = {"job_id": job_id, "message": payload.text, "intent": None, "plan": None}
    try:
        graph.invoke(graph_input, _config(job_id))
    except Exception:
        logger.exception("Scheduling assistant workflow failed for job %s", job_id)
        raise AppException("Scheduling assistant failed, please try again", 500, "SCHEDULE_ASSISTANT_ERROR") from None

    if graph.get_state(_config(job_id)).values.get("llm_failed"):
        if not is_revise:
            get_checkpointer().delete_thread(_thread_id(job_id))
        raise AppException(
            "The AI assistant is not available right now. Please try again in a moment.", 502, "AI_UNAVAILABLE"
        )
    return _current_state(job_id)


@router.post("/cancel", response_model=AssistantState)
def cancel_assistant(job_id: int, db: Session = Depends(get_db)):
    """Drop the open plan so the next instruction starts fresh."""
    _get_job(db, job_id)
    if _is_open(job_id):
        get_scheduling_graph().invoke(Command(resume={"action": "cancel"}), _config(job_id))
    get_checkpointer().delete_thread(_thread_id(job_id))
    logger.info("Scheduling assistant cancelled for job %s", job_id)
    return AssistantState(status="none")


@router.post("/confirm", response_model=AssistantState)
def confirm_plan(job_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("interviewer"))):
    """Schedule every planned candidate and send the invitations. The thread ends afterwards."""
    _get_job(db, job_id)
    with _confirming_lock:
        if job_id in _confirming:
            raise AppException("This plan is already being confirmed", 409, "NO_OPEN_PLAN")
        _confirming.add(job_id)
    try:
        if _current_state(job_id).status != "plan":
            raise AppException("There is no plan to confirm", 409, "NO_OPEN_PLAN")
        graph = get_scheduling_graph()
        try:
            graph.invoke(Command(resume={"action": "confirm", "user_id": user.id}), _config(job_id))
        except Exception:
            logger.exception("Scheduling assistant confirm failed for job %s", job_id)
            raise AppException("Scheduling failed, please check the Interviews page", 500,
                               "SCHEDULE_ASSISTANT_ERROR") from None
        results = graph.get_state(_config(job_id)).values.get("results") or []
        return AssistantState(status="done", results=results)
    finally:
        with _confirming_lock:
            _confirming.discard(job_id)
