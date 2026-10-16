from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CandidateAssessment(Base):
    """Consolidated AI assessment of one candidate: CV screening + score + interview analysis
    (one row per candidate; a re-run replaces it). Separate from the interviewer's hiring decision."""

    __tablename__ = "candidate_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), unique=True, index=True
    )
    interview_id: Mapped[int | None] = mapped_column(ForeignKey("interviews.id", ondelete="SET NULL"))
    analysis_version: Mapped[int | None] = mapped_column(Integer)  # interview analysis version used
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / running / completed / failed
    error: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)  # +1 on every re-run
    score: Mapped[dict | None] = mapped_column(JSONB)
    requirements: Mapped[list | None] = mapped_column(JSONB)
    findings: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
