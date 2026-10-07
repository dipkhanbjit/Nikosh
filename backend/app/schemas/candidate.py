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