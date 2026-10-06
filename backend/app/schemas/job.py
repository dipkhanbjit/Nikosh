from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    employment_type: EmploymentType | None = None
    min_experience_years: int | None = Field(default=None, ge=0, le=50)
    description: str | None = None
    requirements: list[Requirement] | None = None
    status: JobStatus | None = None


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
    created_by: int
    created_at: datetime
    updated_at: datetime