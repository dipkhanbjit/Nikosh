from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InterviewAudioPart(Base):
    """One recorded audio connection of a speaker (WAV on disk). Created when the audio socket
    connects; duration and size are filled in when it closes."""

    __tablename__ = "interview_audio_parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # interviewer / candidate
    part_no: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(500))
    # Seconds since the interview's started_at when this part began
    start_offset_s: Mapped[float] = mapped_column(Float, default=0)
    duration_s: Mapped[float | None] = mapped_column(Float)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
