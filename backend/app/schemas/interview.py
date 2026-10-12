from datetime import datetime

from pydantic import AwareDatetime, BaseModel, Field

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class InterviewCreate(BaseModel):
    candidate_id: int
    scheduled_at: AwareDatetime  # must include a timezone, e.g. 2026-10-14T15:00:00+06:00
    duration_minutes: int = Field(default=30, ge=15, le=120)
    notes: str | None = Field(default=None, max_length=1000)
    # Updates the candidate's email (login + invitation address) before scheduling
    contact_email: str | None = Field(default=None, max_length=255, pattern=EMAIL_PATTERN)


class InterviewUpdate(BaseModel):
    scheduled_at: AwareDatetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=120)
    notes: str | None = Field(default=None, max_length=1000)


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class Credentials(BaseModel):
    email: str
    password: str


class InterviewOut(BaseModel):
    id: int
    job_id: int
    job_title: str
    candidate_id: int
    candidate_name: str | None
    candidate_email: str | None
    scheduled_at: datetime
    duration_minutes: int
    status: str
    notes: str | None
    started_at: datetime | None
    ended_at: datetime | None
    cancel_reason: str | None
    join_url: str
    calendar_url: str | None
    invitation_status: str | None
    invitation_error: str | None
    invitation_sent_at: datetime | None
    created_at: datetime
    credentials: Credentials | None = None  # only in the schedule response, shown once
