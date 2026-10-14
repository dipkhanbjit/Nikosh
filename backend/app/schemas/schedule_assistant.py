from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AssistantMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=1000)


class PlanItem(BaseModel):
    candidate_id: int
    name: str | None
    email: str
    email_source: Literal["chat", "form", "cv"]
    start: datetime  # Asia/Dhaka, +06:00
    duration_min: int


class SkippedCandidate(BaseModel):
    candidate_id: int
    name: str | None
    reason: str


class AssistantState(BaseModel):
    status: Literal["none", "plan", "question"]
    items: list[PlanItem] = []
    skipped: list[SkippedCandidate] = []
    message: str | None = None  # plan summary, or the question to answer
