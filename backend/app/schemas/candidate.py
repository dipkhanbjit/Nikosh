from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    full_name: str | None
    email: str | None
    phone: str | None
    cv_filename: str | None
    source: str
    status: str
    extraction_status: str
    extraction_error: str | None
    parse_status: str
    parse_error: str | None
    screening_status: str
    screening_error: str | None
    applied_at: datetime | None
    created_at: datetime


class ImportResult(BaseModel):
    filename: str
    status: Literal["imported", "rejected", "failed"]
    reason: str | None = None
    candidate_id: int | None = None


class ImportSummary(BaseModel):
    imported: int
    rejected: int
    failed: int
    results: list[ImportResult]

    @classmethod
    def from_results(cls, results: list[dict]) -> "ImportSummary":
        count = lambda s: sum(1 for r in results if r["status"] == s)
        return cls(
            imported=count("imported"),
            rejected=count("rejected"),
            failed=count("failed"),
            results=results,
        )


class NewApplications(BaseModel):
    count: int


class ExtractionSummary(BaseModel):
    processed: int
    extracted: int
    failed: int


class ParseSummary(BaseModel):
    processed: int
    parsed: int
    failed: int


class ScreeningSummary(BaseModel):
    processed: int
    screened: int
    failed: int


class CandidateText(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cv_filename: str | None
    extraction_status: str
    cv_text: str | None
    parse_status: str
    profile: dict | None
    screening: list[dict] | None