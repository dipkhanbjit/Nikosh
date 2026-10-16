import logging

from fastapi import APIRouter, Depends
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Job
from app.schemas.jd import JDGenerateRequest, JDReviewRequest, JDState
from app.services.deadlines import DHAKA, today
from app.workflows.checkpointer import get_checkpointer
from app.workflows.jd_generation import get_jd_graph

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/jobs/{job_id}/jd",
    tags=["jd"],
    dependencies=[Depends(require_role("interviewer"))],
)


def _config(job_id: int) -> dict:
    return {"configurable": {"thread_id": f"jd-job-{job_id}"}}


def _get_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise AppException("Job not found", 404, "JOB_NOT_FOUND")
    return job


def _job_profile(job: Job) -> str:
    return f"Title: {job.title}"


def _saved_profile(job: Job) -> dict:
    """The job's saved profile fields, in the same shape as the workflow state."""
    deadline = job.application_deadline
    return {
        "department": job.department,
        "location": job.location,
        "employment_type": job.employment_type,
        "min_experience_years": job.min_experience_years,
        "application_deadline": deadline.astimezone(DHAKA).date().isoformat() if deadline else None,
    }


def _current_state(job: Job) -> JDState:
    snapshot = get_jd_graph().get_state(_config(job.id))
    values = snapshot.values
    if not values:
        status = "approved" if job.description else "not_started"
        return JDState(
            status=status,
            description=job.description,
            requirements=job.requirements,
            profile=_saved_profile(job),
        )
    status = "awaiting_review" if "review" in snapshot.next else "approved"
    return JDState(
        status=status,
        description=values.get("description"),
        requirements=values.get("requirements", []),
        profile=values.get("profile") or _saved_profile(job),
        messages=values.get("messages", []),
    )


def _run(job_id: int, graph_input) -> None:
    try:
        get_jd_graph().invoke(graph_input, _config(job_id))
    except Exception:
        logger.exception("JD workflow failed for job %s", job_id)
        raise AppException("AI service failed, please try again", 503, "LLM_ERROR") from None


@router.get("", response_model=JDState)
def get_jd(job_id: int, db: Session = Depends(get_db)):
    return _current_state(_get_job(db, job_id))


@router.post("/generate", response_model=JDState)
def generate_jd(job_id: int, payload: JDGenerateRequest, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    if job.status in ("posted", "closed"):
        raise AppException("JD cannot be regenerated after posting", 409, "JOB_ALREADY_POSTED")

    get_checkpointer().delete_thread(_config(job_id)["configurable"]["thread_id"])
    _run(job_id, {
        "job_id": job.id,
        "job_profile": _job_profile(job),
        "prompt": payload.prompt,
        "description": job.description,
        "profile": _saved_profile(job) if job.description else None,  # keep it when revising
        "feedback": payload.prompt if job.description else None,
        "messages": [{"role": "user", "content": payload.prompt}],
    })
    return _current_state(job)


@router.post("/review", response_model=JDState)
def review_jd(job_id: int, payload: JDReviewRequest, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    if "review" not in get_jd_graph().get_state(_config(job_id)).next:
        raise AppException("No draft is waiting for review", 409, "NO_PENDING_DRAFT")
    if payload.action == "refine" and not payload.feedback:
        raise AppException("Feedback is required to refine", 422, "FEEDBACK_REQUIRED")
    deadline = payload.profile and payload.profile.application_deadline
    if deadline and deadline < today():
        raise AppException("The application deadline must be today or later", 422, "INVALID_DEADLINE")

    resume = payload.model_dump(mode="json", exclude_none=True)
    if payload.profile:
        resume["profile"] = payload.profile.model_dump(mode="json")  # keep cleared fields as null
    _run(job_id, Command(resume=resume))
    db.refresh(job)
    return _current_state(job)