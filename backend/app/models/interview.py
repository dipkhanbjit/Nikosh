import secrets
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.candidate import Candidate

INTERVIEW_STATUSES = ("scheduled", "in_progress", "completed", "cancelled", "no_show")
ACTIVE_STATUSES = ("scheduled", "in_progress")
# Same default as the manual Schedule modal (frontend DEFAULT_DURATION)
DEFAULT_DURATION_MINUTES = 30
MIN_DURATION_MINUTES = 15
MAX_DURATION_MINUTES = 120


class Interview(TimestampMixin, Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(default=DEFAULT_DURATION_MINUTES)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Secret for the candidate's interview link (no login needed)
    join_token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=lambda: secrets.token_urlsafe(32)
    )
    # Invitation (Google Calendar event + email); status is sent / failed
    calendar_event_id: Mapped[str | None] = mapped_column(String(255))
    calendar_url: Mapped[str | None] = mapped_column(String(500))
    invitation_status: Mapped[str | None] = mapped_column(String(20))
    invitation_error: Mapped[str | None] = mapped_column(Text)
    invitation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # .ics SEQUENCE: raised on every invitation / cancellation so calendars apply the update
    invitation_sequence: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    # Co-pilot suggested questions: {"questions": [...], "generated_at": iso}; regenerate replaces it
    suggested_questions: Mapped[dict | None] = mapped_column(JSONB)

    candidate: Mapped["Candidate"] = relationship(back_populates="interviews")