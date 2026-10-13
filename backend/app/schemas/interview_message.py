from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InterviewMessageOut(BaseModel):
    """One in-call chat message. The file is downloaded by message id (the path is never sent)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    interview_id: int
    sender_role: str
    sender_name: str | None
    text: str | None
    file_name: str | None
    file_size: int | None
    content_type: str | None
    created_at: datetime
