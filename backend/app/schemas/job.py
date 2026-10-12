from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

EmploymentType = Literal["full_time", "part_time", "contract", "internship"]
JobStatus = Literal["draft", "approved", "posted", "closed"]


class Requirement(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    category: Literal["skill", "experience", "qualification"]
    mandatory: bool = False
    weight: int = Field(default=3, ge=1, le=5)


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    employment_type: EmploymentType = "full_time"
    min_experience_years: int | None = Field(default=None, ge=0, le=50)
    description: str | None = None
    requirements: list[Requirement] = []
    application_deadline: date | None = None


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