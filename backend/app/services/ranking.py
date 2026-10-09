from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, Job

RATING_VALUE = {"met": 1.0, "partial": 0.5, "unmet": 0.0}
MAX_REASON_LENGTH = 255


def match_score(matches: list[dict]) -> float:
    """Weighted requirement score from 0 to 100 (met = 1, partial = 0.5, unmet = 0)."""
    total_weight = sum(m.get("weight", 3) for m in matches)
    if not total_weight:
        return 0.0
    earned = sum(m.get("weight", 3) * RATING_VALUE.get(m.get("rating"), 0.0) for m in matches)
    return round(100 * earned / total_weight, 1)


def missing_mandatory(matches: list[dict]) -> list[str]:
    """Mandatory requirements rated unmet. Partial still passes the filter."""
    return [m["text"] for m in matches if m.get("mandatory") and m.get("rating") == "unmet"]


def apply_ranking_rules(candidate: Candidate) -> None:
    """Set the match score and exclude the candidate if a mandatory requirement is unmet."""
    matches = candidate.screening or []
    candidate.match_score = match_score(matches)
    missing = missing_mandatory(matches)
    if missing:
        candidate.status = "excluded"
        reason = "Missing mandatory requirement: " + "; ".join(missing)
        candidate.rejection_reason = reason[:MAX_REASON_LENGTH]


def ranked_candidates(db: Session, job: Job) -> list[Candidate]:
    """Eligible, screened candidates ordered by score (ties: earlier application first)."""
    return list(db.scalars(
        select(Candidate)
        .where(
            Candidate.job_id == job.id,
            Candidate.status == "applied",
            Candidate.screening_status == "screened",
        )
        .order_by(Candidate.match_score.desc().nulls_last(), Candidate.applied_at.asc())
    ))