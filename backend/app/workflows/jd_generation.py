import operator
from functools import lru_cache
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.core.database import SessionLocal
from app.models import Job
from app.schemas.jd import JDDraft
from app.schemas.job import Requirement
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
- If the job profile has a minimum experience, include it as a requirement worded
  like "At least N years of professional experience in ...".
- Then extract ONLY the items of the Requirements section (not Nice to Have) as the
  requirements list. For each one set category: skill, experience or qualification."""


class JDGraphState(TypedDict, total=False):
    job_id: int
    job_profile: str
    prompt: str
    context: str
    description: str
    requirements: list[dict]
    feedback: str | None
    messages: Annotated[list[dict], operator.add]


COMPANY_QUERY = "company profile, compensation, benefits, leave and work policy"


def retrieve(state: JDGraphState) -> dict:
    role_query = f"{state['job_profile']}\n{state['prompt']}"
    with SessionLocal() as db:
        chunks = search(db, role_query, k=5) + search(db, COMPANY_QUERY, k=3)

    seen, unique = set(), []
    for c in chunks:
        key = (c["source"], c["chunk_index"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    context = "\n\n".join(f"[{c['source']}]\n{c['content']}" for c in unique)
    return {"context": context}


def draft(state: JDGraphState) -> dict:
    parts = [
        f"Job profile:\n{state['job_profile']}",
        f"Recruiter request:\n{state['prompt']}",
        f"Company context:\n{state['context']}",
    ]
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
        "feedback": None,
        "messages": [{
            "role": "assistant",
            "content": "Here is the draft based on company documents. "
                       "Review the requirements (all are mandatory), then approve it or tell me what to change.",
        }],
    }


def review(state: JDGraphState) -> Command[Literal["draft", "save"]]:
    decision = interrupt({
        "description": state["description"],
        "requirements": state["requirements"],
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
    return Command(goto="save", update=update)


def _clean_requirements(requirements: list[dict]) -> list[dict]:
    """Keep non-empty requirements as {text, category}; fill missing categories automatically."""
    return [
        Requirement(text=r.get("text", ""), category=r.get("category")).model_dump()
        for r in requirements
        if (r.get("text") or "").strip()
    ]


def save(state: JDGraphState) -> dict:
    with SessionLocal() as db:
        job = db.get(Job, state["job_id"])
        job.description = state["description"]
        job.requirements = _clean_requirements(state["requirements"])
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