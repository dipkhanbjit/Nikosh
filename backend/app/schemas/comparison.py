from datetime import datetime

from pydantic import BaseModel


class ComparisonRequirement(BaseModel):
    id: int
    text: str
    category: str | None


class ComparisonCandidate(BaseModel):
    candidate_id: int
    name: str | None
    interview_id: int | None
    final: int | None
    band: str | None
    recommendation: str | None
    cv_score: float | None
    interview_score: float | None
    statuses: dict[int, str | None]  # requirement id -> met / partial / unmet
    met: int
    partial: int
    unmet: int
    strengths: int
    weaknesses: int
    gaps: int
    conflicts: int
    unsupported: int
    outdated: bool
    assessed_at: datetime | None


class JobComparisonOut(BaseModel):
    job_id: int
    job_title: str
    requirements: list[ComparisonRequirement]
    candidates: list[ComparisonCandidate]
