from datetime import datetime

from pydantic import BaseModel, Field


class AssessmentItem(BaseModel):
    """One strength, weakness or gap (LLM output)."""

    text: str = Field(description="One short, specific sentence")
    requirement_ids: list[int] = Field(
        default_factory=list, description="Numbers of the requirements this item is about (R3 -> 3); empty if none"
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="Evidence ids from the input that support this item, e.g. CV-R3, CV-D:experience, P5",
    )


class AssessmentRecommendation(BaseModel):
    text: str = Field(description="2-3 sentences that explain the given recommendation level")
    evidence_refs: list[str] = Field(default_factory=list, description="Evidence ids that support it")


class ConsolidatedAssessmentResult(BaseModel):
    """Strengths, weaknesses, gaps and recommendation text (LLM output)."""

    strengths: list[AssessmentItem] = Field(description="Up to 5 key strengths")
    weaknesses: list[AssessmentItem] = Field(description="Up to 5 main weaknesses or concerns")
    gaps: list[AssessmentItem] = Field(description="One item per listed gap requirement")
    recommendation: AssessmentRecommendation


class CandidateAssessmentOut(BaseModel):
    candidate_id: int
    interview_id: int | None
    analysis_version: int | None
    status: str  # pending / running / completed / failed
    error: str | None
    version: int
    score: dict | None  # final, cv, interview, weights, band, recommendation
    requirements: list | None
    findings: dict | None  # strengths, weaknesses, gaps, recommendation
    outdated: bool = False  # the interview was re-analysed after this assessment
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
