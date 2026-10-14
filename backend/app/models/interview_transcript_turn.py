from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InterviewTranscriptTurn(Base):
    """One closed transcript turn, saved during the session. Times are seconds since started_at."""

    __tablename__ = "interview_transcript_turns"
    __table_args__ = (UniqueConstraint("interview_id", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)  # the builder's stable turn id (creation order)
    speaker: Mapped[str] = mapped_column(String(20))  # interviewer / candidate
    text: Mapped[str] = mapped_column(Text)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    incomplete: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"), default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
