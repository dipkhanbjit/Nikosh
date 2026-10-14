import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.models import InterviewTranscriptTurn

logger = logging.getLogger(__name__)


def save_turn(turn) -> bool:
    """Save one closed turn (own session; runs in a thread). seq = the builder's stable turn id.
    Errors are logged, never raised: transcription goes on."""
    try:
        with SessionLocal() as db:
            db.add(
                InterviewTranscriptTurn(
                    interview_id=turn.interview_id,
                    seq=turn.id,
                    speaker=turn.role,
                    text=turn.text,
                    start_s=turn.start_s,
                    end_s=turn.end_s,
                    confidence=turn.confidence,
                    incomplete=turn.incomplete,
                )
            )
            db.commit()
    except SQLAlchemyError as exc:
        logger.error("Interview %s: transcript turn %d not saved (%s)", turn.interview_id, turn.id, type(exc).__name__)
        return False
    logger.info("Interview %s: transcript turn %d saved", turn.interview_id, turn.id)
    return True


def list_turns(interview_id: int) -> list[InterviewTranscriptTurn]:
    """Saved turns of an interview in spoken order."""
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(InterviewTranscriptTurn)
                .where(InterviewTranscriptTurn.interview_id == interview_id)
                .order_by(InterviewTranscriptTurn.start_s, InterviewTranscriptTurn.seq)
            )
        )
