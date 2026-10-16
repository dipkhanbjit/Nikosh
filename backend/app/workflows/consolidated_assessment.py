import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Candidate, InterviewAnalysis, Job
from app.services.candidate_assessments import analysis_ready, get_assessment, mark_running, save_result
from app.services.consolidated_assessment import (
    AssessmentError,
    combine_requirements,
    final_score,
    write_findings,
)
from app.workflows.checkpointer import get_checkpointer

logger = logging.getLogger(__name__)


class AssessmentState(TypedDict, total=False):
    candidate_id: int
    version: int
    inputs: dict  # plain dicts, so the checkpointer can store them
    score: dict
    requirements: list[dict]
    findings: dict


# ---------- Nodes (results stay in the state; only save writes them) ----------

def load_inputs(state: AssessmentState) -> dict:
    """Mark the assessment running and snapshot the CV screening, CV score and interview analysis."""
    candidate_id = state["candidate_id"]
    if not mark_running(candidate_id, state["version"]):
        raise RuntimeError("Assessment was replaced or removed before it started")
    with SessionLocal() as db:
        assessment = get_assessment(db, candidate_id)
        candidate = db.get(Candidate, candidate_id)
        analysis = db.scalar(
            select(InterviewAnalysis).where(InterviewAnalysis.interview_id == assessment.interview_id)
        ) if assessment.interview_id else None
        if candidate is None or candidate.scoring_status != "scored" or candidate.overall_score is None:
            raise AssessmentError("The candidate's CV score is no longer available")
        if not analysis_ready(analysis) or analysis.version != assessment.analysis_version:
            raise AssessmentError("The interview analysis changed; run the assessment again")
        inputs = {
            "job_title": db.scalar(select(Job.title).where(Job.id == candidate.job_id)) or "Unknown",
            "screening": candidate.screening or [],
            "scores": candidate.scores or {},
            "cv_score": candidate.overall_score,
            "interview_overall": analysis.overall,
            "requirement_mapping": analysis.requirement_mapping or [],
            "evaluations": analysis.evaluations or [],
            "pairs": analysis.pairs or [],
        }
    logger.info("Candidate %s: assessment v%s started (interview %s)", candidate_id, state["version"],
                assessment.interview_id)
    return {"inputs": inputs}


def combine(state: AssessmentState) -> dict:
    """Final score and per-requirement status in code (no LLM)."""
    inputs = state["inputs"]
    score = final_score(inputs["cv_score"], inputs["interview_overall"]["score"])
    requirements = combine_requirements(inputs["screening"], inputs["requirement_mapping"])
    logger.info("Candidate %s: final score %s (%s)", state["candidate_id"], score["final"], score["band"])
    return {"score": score, "requirements": requirements}


def summarize(state: AssessmentState) -> dict:
    return {"findings": write_findings(state["inputs"], state["score"], state["requirements"], state["candidate_id"])}


def save(state: AssessmentState) -> dict:
    save_result(state["candidate_id"], state["version"], state)
    return {}


# ---------- Graph ----------

def _build_graph():
    builder = StateGraph(AssessmentState)
    builder.add_node("load_inputs", load_inputs)
    builder.add_node("combine", combine)
    builder.add_node("summarize", summarize)
    builder.add_node("save", save)
    builder.add_edge(START, "load_inputs")
    builder.add_edge("load_inputs", "combine")
    builder.add_edge("combine", "summarize")
    builder.add_edge("summarize", "save")
    builder.add_edge("save", END)
    return builder.compile(checkpointer=get_checkpointer())


_graph = None


def get_assessment_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def run_assessment_workflow(candidate_id: int, version: int) -> None:
    """Run the whole workflow (called in the background). One thread per run."""
    config = {"configurable": {"thread_id": f"assessment-candidate-{candidate_id}-v{version}"}}
    get_assessment_graph().invoke({"candidate_id": candidate_id, "version": version}, config)
