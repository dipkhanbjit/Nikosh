import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Interview, InterviewTranscriptTurn, Job
from app.services.answer_evaluation import evaluate_answers
from app.services.interview_analyses import mark_running, save_result
from app.services.interview_evaluation import overall_score, summarize_interview
from app.services.qa_pairing import pair_turns
from app.services.requirement_mapping import map_requirements, summarize_gaps
from app.services.transcripts import list_turns
from app.workflows.checkpointer import get_checkpointer

logger = logging.getLogger(__name__)

TURN_FIELDS = ("interview_id", "seq", "speaker", "text", "start_s", "end_s", "incomplete")


class AnalysisState(TypedDict, total=False):
    interview_id: int
    version: int
    turns: list[dict]  # plain dicts, so the checkpointer can store them
    pairs: list[dict]
    evaluations: list[dict]
    requirement_mapping: list[dict]
    gaps: dict
    overall: dict


# ---------- Nodes (results stay in the state; only save writes them) ----------

def load_transcript(state: AnalysisState) -> dict:
    """Mark the analysis running and load the transcript turns in spoken order."""
    if not mark_running(state["interview_id"], state["version"]):
        raise RuntimeError("Analysis was replaced or removed before it started")
    turns = [{f: getattr(t, f) for f in TURN_FIELDS} for t in list_turns(state["interview_id"])]
    logger.info("Interview %s: analysis v%s started (%d turns)", state["interview_id"], state["version"], len(turns))
    return {"turns": turns}


def pair_qa(state: AnalysisState) -> dict:
    turns = [InterviewTranscriptTurn(**t) for t in state["turns"]]
    return {"pairs": pair_turns(turns) if turns else []}


def evaluate(state: AnalysisState) -> dict:
    with SessionLocal() as db:
        return {"evaluations": evaluate_answers(db, state["pairs"], state["interview_id"])}


def map_reqs(state: AnalysisState) -> dict:
    with SessionLocal() as db:
        mappings = map_requirements(db, state["pairs"], state["evaluations"], state["interview_id"])
    return {"requirement_mapping": mappings, "gaps": summarize_gaps(mappings)}


def overall_evaluation(state: AnalysisState) -> dict:
    """Score in code, then one short LLM summary."""
    overall = overall_score(state["evaluations"], state["requirement_mapping"])
    with SessionLocal() as db:
        job_title = db.scalar(
            select(Job.title).join(Interview, Interview.job_id == Job.id)
            .where(Interview.id == state["interview_id"])
        ) or "Unknown"
    overall["summary"] = summarize_interview(
        overall, state["gaps"], state["evaluations"], job_title, state["interview_id"]
    )
    return {"overall": overall}


def save(state: AnalysisState) -> dict:
    save_result(state["interview_id"], state["version"], state)
    return {}


# ---------- Graph ----------

def _build_graph():
    builder = StateGraph(AnalysisState)
    builder.add_node("load_transcript", load_transcript)
    builder.add_node("pair_qa", pair_qa)
    builder.add_node("evaluate", evaluate)
    builder.add_node("map_requirements", map_reqs)
    builder.add_node("overall_evaluation", overall_evaluation)
    builder.add_node("save", save)
    builder.add_edge(START, "load_transcript")
    builder.add_edge("load_transcript", "pair_qa")
    builder.add_edge("pair_qa", "evaluate")
    builder.add_edge("evaluate", "map_requirements")
    builder.add_edge("map_requirements", "overall_evaluation")
    builder.add_edge("overall_evaluation", "save")
    builder.add_edge("save", END)
    return builder.compile(checkpointer=get_checkpointer())


_graph = None


def get_analysis_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def run_analysis_workflow(interview_id: int, version: int) -> None:
    """Run the whole workflow (called in the background). One thread per run."""
    config = {"configurable": {"thread_id": f"analysis-interview-{interview_id}-v{version}"}}
    get_analysis_graph().invoke({"interview_id": interview_id, "version": version}, config)
