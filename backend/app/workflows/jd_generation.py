import operator
from datetime import date
from functools import lru_cache
from typing import Annotated, Literal, TypedDict, get_args

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.core.database import SessionLocal
from app.models import Job
from app.schemas.jd import MAX_EXPERIENCE_YEARS, JDDraft
from app.schemas.job import EmploymentType, Requirement
from app.services.deadlines import end_of_day, today
from app.services.job_posting import publish_job
from app.services.knowledge_base import search
from app.services.llm import get_llm
from app.workflows.checkpointer import get_checkpointer

SYSTEM_PROMPT = """You are an HR assistant writing job descriptions for the company.
Write a professional job description in Markdown with these sections:
About the Company, Role Overview, Key Responsibilities, Requirements, Nice to Have, and Benefits.

Rules:
- Use only company facts (profile, policies, benefits, tech stack) found in the
  provided company context. Never invent salary figures or benefits.
- The Benefits section must list the compensation, leave and other benefits
  found in the company context.
- Follow the role standards in the context for the seniority level.
- The Requirements section lists only the essential must-haves (4 to 8 items).
  Every candidate must meet all of them, so do not include optional skills there.
- Put optional or bonus skills only in the Nice to Have section.
- If there is a minimum experience, include it as a requirement worded
  like "At least N years of professional experience in ...".
- Then extract ONLY the items of the Requirements section (not Nice to Have) as the
  requirements list. For each one set category: skill, experience or qualification.

Also return the job profile fields: department, location, employment_type,
min_experience_years and application_deadline.
- Take each value from the recruiter request or feedback first, then from the
  company context. If neither mentions it, return null. Never guess.
- employment_type is one of: full_time, part_time, contract, internship.
- min_experience_years is a whole number of years.
- application_deadline is a date as YYYY-MM-DD. Convert relative dates
  (e.g. "within two weeks") using today's date.
- If a current job profile is given, keep its values unless the request or
  feedback changes them."""

EMPLOYMENT_TYPES = get_args(EmploymentType)
PROFILE_FIELDS = ("department", "location", "employment_type", "min_experience_years", "application_deadline")


def _text(value) -> str | None:
    text = " ".join(str(value or "").split())
    return text[:100] or None


def _employment_type(value) -> str:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return key if key in EMPLOYMENT_TYPES else "full_time"


def _years(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= MAX_EXPERIENCE_YEARS else None


def _deadline(value, on: date) -> str | None:
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        return None
    return day.isoformat() if day >= on else None


def clean_profile(raw: dict, on: date) -> dict:
    """Validate AI profile values: invalid ones are dropped (employment type falls back to full_time)."""
    return {
        "department": _text(raw.get("department")),
        "location": _text(raw.get("location")),
        "employment_type": _employment_type(raw.get("employment_type")),
        "min_experience_years": _years(raw.get("min_experience_years")),
        "application_deadline": _deadline(raw.get("application_deadline"), on),
    }


def _profile_text(profile: dict) -> str:
    return "\n".join(f"{k}: {'not set' if profile.get(k) is None else profile[k]}" for k in PROFILE_FIELDS)


class JDGraphState(TypedDict, total=False):
    job_id: int
    job_profile: str
    prompt: str
    context: str
    description: str
    requirements: list[dict]
    profile: dict | None
    feedback: str | None
    messages: Annotated[list[dict], operator.add]


COMPANY_QUERY = "company profile, compensation, benefits, leave and work policy"


def retrieve(state: JDGraphState) -> dict:
    role_query = f"{state['job_profile']}\n{state['prompt']}"
    with SessionLocal() as db:
        chunks = search(db, role_query, k=5, kind="company") + search(
            db, COMPANY_QUERY, k=3, kind="company"
        )

    seen, unique = set(), []
    for c in chunks:
        key = (c["source"], c["chunk_index"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    context = "\n\n".join(f"[{c['source']}]\n{c['content']}" for c in unique)
    return {"context": context}


def draft(state: JDGraphState) -> dict:
    on = today()
    parts = [
        f"Job profile:\n{state['job_profile']}",
        f"Today's date: {on.isoformat()}",
        f"Recruiter request:\n{state['prompt']}",
        f"Company context:\n{state['context']}",
    ]
    if state.get("profile"):
        parts.append(f"Current job profile:\n{_profile_text(state['profile'])}")
    if state.get("feedback"):
        parts.append(f"Previous draft:\n{state['description']}")
        parts.append(f"Revise the previous draft based on this feedback:\n{state['feedback']}")

    llm = get_llm().with_structured_output(JDDraft)
    result: JDDraft = llm.invoke(
        [SystemMessage(SYSTEM_PROMPT), HumanMessage("\n\n".join(parts))]
    )
    return {
        "description": result.description,
        "requirements": [r.model_dump() for r in result.requirements],
        "profile": clean_profile(result.model_dump(include=set(PROFILE_FIELDS)), on),
        "feedback": None,
        "messages": [{
            "role": "assistant",
            "content": "Here is the draft based on company documents. "
                       "Review the job profile and requirements (all are mandatory), then approve it or tell me what to change.",
        }],
    }


def review(state: JDGraphState) -> Command[Literal["draft", "save"]]:
    decision = interrupt({
        "description": state["description"],
        "requirements": state["requirements"],
        "profile": state.get("profile"),
    })
    if decision["action"] == "refine":
        return Command(
            goto="draft",
            update={
                "feedback": decision["feedback"],
                "messages": [{"role": "user", "content": decision["feedback"]}],
            },
        )
    update = {}
    if decision.get("description"):
        update["description"] = decision["description"]
    if decision.get("requirements") is not None:
        update["requirements"] = decision["requirements"]
    if decision.get("profile") is not None:
        update["profile"] = decision["profile"]
    return Command(goto="save", update=update)


def _clean_requirements(requirements: list[dict]) -> list[dict]:
    """Keep non-empty requirements as {text, category}; fill missing categories automatically."""
    return [
        Requirement(text=r.get("text", ""), category=r.get("category")).model_dump()
        for r in requirements
        if (r.get("text") or "").strip()
    ]


def _apply_profile(job: Job, profile: dict) -> None:
    """Write the reviewed profile to the job. No deadline: the default is set on posting."""
    job.department = profile.get("department")
    job.location = profile.get("location")
    job.employment_type = profile.get("employment_type") or "full_time"
    job.min_experience_years = profile.get("min_experience_years")
    deadline = profile.get("application_deadline")
    job.application_deadline = end_of_day(date.fromisoformat(deadline)) if deadline else None


def save(state: JDGraphState) -> dict:
    with SessionLocal() as db:
        job = db.get(Job, state["job_id"])
        job.description = state["description"]
        job.requirements = _clean_requirements(state["requirements"])
        if profile := state.get("profile"):
            _apply_profile(job, profile)
        job.status = "approved"
        db.commit()
    return {"messages": [{"role": "assistant", "content": "JD approved and saved to the job."}]}


def post_jd(state: JDGraphState) -> dict:
    with SessionLocal() as db:
        job = db.get(Job, state["job_id"])
        if publish_job(db, job):
            content = f"JD posted: {job.posted_url}"
        else:
            content = f"JD saved, but posting failed: {job.posting_error}"
    return {"messages": [{"role": "assistant", "content": content}]}


@lru_cache
def get_jd_graph():
    builder = StateGraph(JDGraphState)
    builder.add_node("retrieve", retrieve)
    builder.add_node("draft", draft)
    builder.add_node("review", review)
    builder.add_node("save", save)
    builder.add_node("post_jd", post_jd)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "draft")
    builder.add_edge("draft", "review")
    builder.add_edge("save", "post_jd")
    builder.add_edge("post_jd", END)
    return builder.compile(checkpointer=get_checkpointer())