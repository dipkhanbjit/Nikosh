from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.job import Requirement


class JDDraft(BaseModel):
    """Structured output returned by the LLM for each draft."""

    description: str = Field(description="Full job description in Markdown")
    requirements: list[Requirement] = Field(
        description="Only the essential must-have requirements from the Requirements section (4 to 8 items). "
                    "Do not include Nice to Have items."
    )


class JDGenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


class JDReviewRequest(BaseModel):
    action: Literal["refine", "approve"]
    feedback: str | None = Field(default=None, max_length=2000)
    description: str | None = None
    requirements: list[Requirement] | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class JDState(BaseModel):
    status: Literal["not_started", "awaiting_review", "approved"]
    description: str | None = None
    requirements: list[Requirement] = []
    messages: list[ChatMessage] = []