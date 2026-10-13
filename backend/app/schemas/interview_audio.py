from datetime import datetime

from pydantic import BaseModel


class InterviewAudioPartOut(BaseModel):
    """One recorded audio part of a speaker. The WAV is streamed by part id (the path is never sent)."""

    id: int
    role: str
    part_no: int
    start_offset_s: float
    duration_s: float | None
    size_bytes: int | None
    created_at: datetime
