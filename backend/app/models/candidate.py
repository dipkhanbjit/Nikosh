from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

from pgvector.sqlalchemy import Vector

from app.core.config import settings

if TYPE_CHECKING:
    from app.models.job import Job


class Candidate(TimestampMixin, Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    cv_file_path: Mapped[str | None] = mapped_column(String(500))
    cv_filename: Mapped[str | None] = mapped_column(String(255))
    cv_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(20), default="upload")
    source_file_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="applied")
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    cv_text: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[str] = mapped_column(String(20), default="pending")
    extraction_error: Mapped[str | None] = mapped_column(String(500))
    profile: Mapped[dict | None] = mapped_column(JSONB)
    parse_status: Mapped[str] = mapped_column(String(20), default="pending")
    parse_error: Mapped[str | None] = mapped_column(String(500))
    screening: Mapped[list[dict] | None] = mapped_column(JSONB)
    screening_status: Mapped[str] = mapped_column(String(20), default="pending")
    screening_error: Mapped[str | None] = mapped_column(String(500))
    match_score: Mapped[float | None] = mapped_column(Float)
    scores: Mapped[dict | None] = mapped_column(JSONB)
    overall_score: Mapped[float | None] = mapped_column(Float)
    scoring_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    scoring_error: Mapped[str | None] = mapped_column(String(500))
    score_fingerprint: Mapped[str | None] = mapped_column(String(64))
    cv_embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))
    override: Mapped[str | None] = mapped_column(String(20))  # "included" / "excluded" by the interviewer
    override_reason: Mapped[str | None] = mapped_column(String(255))
    override_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped["Job"] = relationship(back_populates="candidates")