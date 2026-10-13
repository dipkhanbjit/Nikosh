from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class JoinInfo(BaseModel):
    """What the candidate sees on the join page. No internal IDs or scores."""

    company_name: str
    job_title: str
    candidate_name: str | None
    scheduled_at: datetime
    duration_minutes: int
    opens_at: datetime
    status: Literal["too_early", "ready"]


class MyInterview(BaseModel):
    """An interview in the logged-in candidate's list. No internal IDs or scores."""

    job_title: str
    scheduled_at: datetime
    duration_minutes: int
    status: str
    join_url: str


class RoomInfo(BaseModel):
    """What the candidate's interview room shows. No CV or scores; interview_id only for the
    in-call chat endpoints (they check that the interview is the candidate's own)."""

    interview_id: int
    job_title: str
    candidate_name: str | None
    status: str
    started_at: datetime | None
