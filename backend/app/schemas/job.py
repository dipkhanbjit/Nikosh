import re
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

EmploymentType = Literal["full_time", "part_time", "contract", "internship"]
JobStatus = Literal["draft", "approved", "posted", "closed"]
RequirementCategory = Literal["skill", "experience", "qualification"]

_YEARS = re.compile(r"\d+(?:\.\d+)?\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
_QUALIFICATION = re.compile(
    r"\b(degree|bachelor'?s?|master'?s?|bsc|msc|b\.sc|m\.sc|phd|diploma|certifi\w*|graduate)\b",
    re.IGNORECASE,
)


def infer_category(text: str) -> str:
    """Category for a requirement typed by the interviewer (no AI call)."""
    if _YEARS.search(text) and "experience" in text.lower():
        return "experience"
    if _QUALIFICATION.search(text):
        return "qualification"
    return "skill"


class Requirement(BaseModel):
    """A mandatory requirement. Every requirement is a gate; there are no weights."""

    text: str = Field(min_length=1, max_length=500)
    category: RequirementCategory | None = None

    @model_validator(mode="after")
    def fill_category(self) -> "Requirement":
        self.text = self.text.strip()
        if self.category is None:
            self.category = infer_category(self.text)
        return self


class JobCreate(BaseModel):
    """Only the position; the JD Assistant fills the other fields."""

    title: str = Field(min_length=1, max_length=255)


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    employment_type: EmploymentType | None = None
    min_experience_years: int | None = Field(default=None, ge=0, le=50)
    description: str | None = None
    requirements: list[Requirement] | None = None
    status: JobStatus | None = None
    application_deadline: date | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    department: str | None
    location: str | None
    employment_type: str
    min_experience_years: int | None
    description: str | None
    requirements: list[Requirement]
    status: str
    posted_url: str | None
    posted_at: datetime | None
    posting_error: str | None
    telegram_url: str | None
    telegram_error: str | None
    telegram_posted_at: datetime | None
    application_deadline: datetime | None
    form_url: str | None
    form_error: str | None
    form_closed_at: datetime | None
    created_by: int
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def applications_closed(self) -> bool:
        return self.application_deadline is not None and datetime.now(timezone.utc) > self.application_deadline


class ScoreWeights(BaseModel):
    """Dimension weights in percent; must add up to 100."""

    technical_skills: int = Field(ge=0, le=100)
    experience: int = Field(ge=0, le=100)
    qualifications: int = Field(ge=0, le=100)
    cv_jd_match: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def check_total(self) -> "ScoreWeights":
        if sum(self.model_dump().values()) != 100:
            raise ValueError("Weights must add up to 100")
        return self


class ScoreWeightsOut(BaseModel):
    weights: ScoreWeights
    is_default: bool
    recalculated: int = 0