from datetime import datetime

from pydantic import BaseModel, Field


class OverallSummaryResult(BaseModel):
    """Short overall summary of the interview (LLM output)."""

    summary: str = Field(
        description="2-4 sentences: key strengths, main concerns and a recommendation that matches the band"
    )


class InterviewAnalysisOut(BaseModel):
    interview_id: int
    status: str  # pending / running / completed / failed
    error: str | None
    version: int
    pairs: list | None
    evaluations: list | None
    requirement_mapping: list | None
    gaps: dict | None
    overall: dict | None  # score, answer_score, coverage_score, band, summary
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
