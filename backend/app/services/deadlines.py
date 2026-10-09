from datetime import date, datetime, time, timedelta, timezone

from app.core.config import settings
from app.models import Job

DHAKA = timezone(timedelta(hours=6))


def end_of_day(day: date) -> datetime:
    """Deadline is the last second of the chosen day, Dhaka time."""
    return datetime.combine(day, time(23, 59, 59), tzinfo=DHAKA)


def default_deadline(posted_at: datetime) -> datetime:
    """Default deadline: N days after posting."""
    day = (posted_at.astimezone(DHAKA) + timedelta(days=settings.default_application_days)).date()
    return end_of_day(day)


def applications_closed(job: Job, at: datetime | None = None) -> bool:
    """True if the given time (default: now) is past the job's deadline."""
    if not job.application_deadline:
        return False
    return (at or datetime.now(timezone.utc)) > job.application_deadline


def deadline_label(job: Job) -> str:
    """Deadline as '21 Oct 2026' for posts and messages."""
    if not job.application_deadline:
        return ""
    return job.application_deadline.astimezone(DHAKA).strftime("%d %b %Y")