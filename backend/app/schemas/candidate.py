from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


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
    rejection_reason: str | None
    override: str | None = None
    override_reason: str | None = None
    overall_score: float | None = None
    scoring_status: str = "pending"
    scoring_error: str | None = None
    rank: int | None = None
    extraction_status: str
    extraction_error: str | None
    parse_status: str
    parse_error: str | None
    screening_status: str
    screening_error: str | None
    applied_at: datetime | None
    created_at: datetime
    screening: list[dict] | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def match_counts(self) -> dict | None:
        """Number of requirements rated met / partial / unmet (full details come from /text)."""
        if not self.screening:
            return None
        counts = {"met": 0, "partial": 0, "unmet": 0}
        for match in self.screening:
            if match.get("rating") in counts:
                counts[match["rating"]] += 1
        return counts


class OverrideRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Reason is required")
        return value


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


class CandidateText(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    cv_filename: str | None
    extraction_status: str
    cv_text: str | None
    parse_status: str
    profile: dict | None
    screening: list[dict] | None
    scores: dict | None = None
    overall_score: float | None = None
    scoring_status: str = "pending"
    scoring_error: str | None = None


class ScreeningRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    status: str
    total: int
    processed: int
    succeeded: int
    failed: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None