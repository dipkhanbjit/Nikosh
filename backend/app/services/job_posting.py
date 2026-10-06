from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Job
from app.services.telegram import PostingError, post_job


def publish_job(db: Session, job: Job) -> bool:
    """Post the job's JD and record the result on the job. Returns True on success."""
    try:
        url = post_job(job.title, job.description)
    except PostingError as exc:
        job.posting_error = str(exc)[:500]
        db.commit()
        return False

    job.status = "posted"
    job.posted_url = url
    job.posted_at = datetime.now(timezone.utc)
    job.posting_error = None
    db.commit()
    return True