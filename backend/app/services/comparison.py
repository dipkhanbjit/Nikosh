"""Side-by-side comparison of the assessed candidates of one job (8.6.2): stored data only, no LLM."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, CandidateAssessment, Job
from app.services.candidate_assessments import is_outdated, latest_interview_analysis


def _count(items: list | None) -> int:
    return len(items or [])


def comparison_row(row: dict) -> dict:
    """One candidate's summary from their completed assessment."""
    score = row.get("score") or {}
    findings = row.get("findings") or {}
    requirements = row.get("requirements") or []
    statuses = {r["requirement_id"]: r.get("final_status") for r in requirements}
    flagged = [item for key in ("strengths", "weaknesses", "gaps") for item in findings.get(key) or []]
    return {
        "candidate_id": row["candidate_id"],
        "name": row.get("name"),
        "interview_id": row.get("interview_id"),
        "final": score.get("final"),
        "band": score.get("band"),
        "recommendation": score.get("recommendation"),
        "cv_score": score.get("cv"),
        "interview_score": score.get("interview"),
        "statuses": statuses,
        "met": sum(1 for s in statuses.values() if s == "met"),
        "partial": sum(1 for s in statuses.values() if s == "partial"),
        "unmet": sum(1 for s in statuses.values() if s == "unmet"),
        "strengths": _count(findings.get("strengths")),
        "weaknesses": _count(findings.get("weaknesses")),
        "gaps": _count(findings.get("gaps")),
        "conflicts": sum(1 for r in requirements if r.get("conflict")),
        "unsupported": sum(1 for item in flagged if item.get("unsupported")),
        "outdated": bool(row.get("outdated")),
        "decision": row.get("decision"),
        "assessed_at": row.get("finished_at"),
    }


def build_comparison(requirements: list[dict] | None, rows: list[dict]) -> dict:
    """Job requirements (1-based ids, as in screening) and completed candidates, best final score first."""
    candidates = [comparison_row(r) for r in rows if r.get("status") == "completed"]
    candidates.sort(key=lambda c: (-(c["final"] if c["final"] is not None else -1), (c["name"] or "").lower()))
    return {
        "requirements": [
            {"id": i, "text": r.get("text") or "", "category": r.get("category")}
            for i, r in enumerate(requirements or [], start=1)
        ],
        "candidates": candidates,
    }


def job_comparison(db: Session, job: Job) -> dict:
    pairs = db.execute(
        select(Candidate, CandidateAssessment)
        .join(CandidateAssessment, CandidateAssessment.candidate_id == Candidate.id)
        .where(Candidate.job_id == job.id, CandidateAssessment.status == "completed")
    ).all()
    rows = [
        {
            "candidate_id": candidate.id,
            "name": candidate.full_name,
            "interview_id": assessment.interview_id,
            "status": assessment.status,
            "score": assessment.score,
            "requirements": assessment.requirements,
            "findings": assessment.findings,
            "outdated": is_outdated(assessment, latest_interview_analysis(db, candidate.id)[1]),
            "finished_at": assessment.finished_at,
            "decision": candidate.decision,
        }
        for candidate, assessment in pairs
    ]
    return {"job_id": job.id, "job_title": job.title, **build_comparison(job.requirements, rows)}
