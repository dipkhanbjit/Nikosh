from datetime import datetime

from pydantic import BaseModel


class TranscriptTurnOut(BaseModel):
    """One saved transcript turn. Times are seconds since the interview started."""

    seq: int
    speaker: str
    text: str
    start_s: float
    end_s: float
    confidence: float | None
    incomplete: bool


class TranscriptOut(BaseModel):
    interview_id: int
    status: str
    candidate_name: str | None
    job_title: str
    started_at: datetime | None
    ended_at: datetime | None
    turn_count: int
    talk_time_s: dict[str, float]  # always has "interviewer" and "candidate"
    turns: list[TranscriptTurnOut]
