from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DecisionRequest(BaseModel):
    decision: Literal["selected", "not_selected"]
    note: str | None = Field(default=None, max_length=2000)  # internal
    notify: bool = False  # email the candidate and show it on their home page
    message: str | None = Field(default=None, max_length=2000)  # to the candidate, when notify


class DecisionOut(BaseModel):
    candidate_id: int
    full_name: str | None
    cv_filename: str | None
    source: str  # "form" applications can also be deleted from Drive
    decision: str | None
    decision_note: str | None
    decision_message: str | None
    decided_at: datetime | None
    decided_by_name: str | None
    decision_notified_at: datetime | None
    decision_email_status: str | None
    decision_email_error: str | None
    can_decide: bool
    contact_email: str | None
