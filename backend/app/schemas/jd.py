from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.job import EmploymentType, Requirement

MAX_EXPERIENCE_YEARS = 30


class JDDraft(BaseModel):
    """Structured output returned by the LLM for each draft."""

    description: str = Field(description="Full job description in Markdown")
    requirements: list[Requirement] = Field(
        description="Only the essential must-have requirements from the Requirements section (4 to 8 items). "
                    "Do not include Nice to Have items."
    )
    # Job profile fields. Loose types on purpose: one bad value must not break the
    # whole structured output; the code validates them afterwards (clean_profile).
    department: str | None = Field(default=None, description="Department, or null if not mentioned")
    location: str | None = Field(default=None, description="Work location, or null if not mentioned")
    employment_type: str | None = Field(
        default=None, description="One of full_time, part_time, contract, internship; null if not mentioned"
    )
    min_experience_years: int | None = Field(
        default=None, description="Minimum years of experience as a whole number, or null if not mentioned"
    )
    application_deadline: str | None = Field(
        default=None, description="Application deadline as YYYY-MM-DD, or null if not mentioned"
    )


class JobProfile(BaseModel):
    """Job profile fields shown in the review step and saved on approve."""

    department: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    employment_type: EmploymentType = "full_time"
    min_experience_years: int | None = Field(default=None, ge=0, le=MAX_EXPERIENCE_YEARS)
    application_deadline: date | None = None


class JDGenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


class JDReviewRequest(BaseModel):
    action: Literal["refine", "approve"]
    feedback: str | None = Field(default=None, max_length=2000)
    description: str | None = None
    requirements: list[Requirement] | None = None
    profile: JobProfile | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class JDState(BaseModel):
    status: Literal["not_started", "awaiting_review", "approved"]
    description: str | None = None
    requirements: list[Requirement] = []
    profile: JobProfile | None = None
    messages: list[ChatMessage] = []