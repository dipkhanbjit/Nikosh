from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.candidate import Candidate

JOB_STATUSES = ("draft", "approved", "posted", "closed")


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    department: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(100))
    employment_type: Mapped[str] = mapped_column(String(20), default="full_time")
    min_experience_years: Mapped[int | None]
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    posted_url: Mapped[str | None] = mapped_column(String(500))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posting_error: Mapped[str | None] = mapped_column(String(500))
    telegram_url: Mapped[str | None] = mapped_column(String(500))
    telegram_error: Mapped[str | None] = mapped_column(String(500))
    telegram_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )