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
