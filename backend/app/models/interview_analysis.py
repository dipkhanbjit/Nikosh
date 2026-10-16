from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InterviewAnalysis(Base):
    """The AI analysis of one interview (one row per interview; a re-run replaces it)."""

    __tablename__ = "interview_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / running / completed / failed
    error: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)  # +1 on every re-run
    pairs: Mapped[list | None] = mapped_column(JSONB)
    evaluations: Mapped[list | None] = mapped_column(JSONB)
    requirement_mapping: Mapped[list | None] = mapped_column(JSONB)
    gaps: Mapped[dict | None] = mapped_column(JSONB)
    overall: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
