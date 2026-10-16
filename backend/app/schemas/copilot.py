from typing import Literal

from pydantic import BaseModel, Field

MAX_MESSAGE_CHARS = 1000
MAX_HISTORY = 6


class CopilotTurn(BaseModel):
    """One earlier message of the co-pilot chat (kept in the frontend)."""

    role: Literal["user", "assistant"]
    content: str


class CopilotChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[CopilotTurn] = Field(default_factory=list)


class CopilotChatResponse(BaseModel):
    answer: str
    sources: list[str]


class CopilotReply(BaseModel):
    """Structured output of the co-pilot LLM call."""

    answer: str = Field(description="Short, practical answer for the interviewer")
    source_ids: list[str] = Field(default_factory=list, description="Passage labels used, e.g. S1, S2")
    used_cv: bool = Field(default=False, description="True if the answer used the candidate CV")
    used_job: bool = Field(default=False, description="True if the answer used the job requirements")
