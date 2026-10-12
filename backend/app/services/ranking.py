from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, Job

MAX_REASON_LENGTH = 255


def unmet_requirements(matches: list[dict]) -> list[str]:
    return [m["text"] for m in matches if m.get("rating") == "unmet"]


def apply_gate(candidate: Candidate) -> None:
    """Eligible if every requirement is met or partially met; otherwise excluded.
    A manual override by the interviewer always wins over the AI result."""
    if candidate.override == "included":
        candidate.status = "applied"
        return
    if candidate.override == "excluded":
        candidate.status = "excluded"
        return
    unmet = unmet_requirements(candidate.screening or [])
    if unmet:
        candidate.status = "excluded"
        candidate.rejection_reason = ("Requirement not met: " + "; ".join(unmet))[:MAX_REASON_LENGTH]
    else:
        candidate.status = "applied"
        candidate.rejection_reason = None


def _rank_key(candidate: Candidate) -> tuple:
    """Score ↓, then Technical Skills ↓, then experience years ↓, then earlier application."""
    scores = candidate.scores or {}
    technical = (scores.get("technical_skills") or {}).get("score", 0)
    years = (candidate.profile or {}).get("total_experience_years") or 0
    applied = candidate.applied_at.timestamp() if candidate.applied_at else float("inf")
    return (-(candidate.overall_score or 0), -technical, -years, applied)


def ranked_candidates(db: Session, job: Job) -> list[Candidate]:
    """Eligible, scored candidates in rank order (1, 2, 3 …)."""
    candidates = db.scalars(
        select(Candidate).where(
            Candidate.job_id == job.id,
            Candidate.status == "applied",
            Candidate.scoring_status == "scored",
        )
    ).all()
    return sorted(candidates, key=_rank_key)