from typing import Literal

from pydantic import BaseModel, Field


class ShortlistStartRequest(BaseModel):
    top_n: int = Field(ge=1, le=50)


class ShortlistReviewRequest(BaseModel):
    action: Literal["approve", "revise"]
    top_n: int | None = Field(default=None, ge=1, le=50)
    remove_ids: list[int] = []


class ShortlistItem(BaseModel):
    candidate_id: int
    rank: int
    full_name: str | None
    email: str | None
    score: float | None
    met: int
    partial: int


class ShortlistState(BaseModel):
    status: Literal["not_started", "awaiting_review", "approved"]
    top_n: int | None = None
    eligible_count: int = 0
    items: list[ShortlistItem] = []