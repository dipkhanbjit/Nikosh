import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.models import Interview, InterviewAnalysis, InterviewTranscriptTurn
from app.services.answer_evaluation import AnswerEvaluationError
from app.services.interview_evaluation import OverallEvaluationError
from app.services.qa_pairing import QAPairingError
from app.services.requirement_mapping import RequirementMappingError

logger = logging.getLogger(__name__)

ACTIVE = ("pending", "running")
RESULT_FIELDS = ("pairs", "evaluations", "requirement_mapping", "gaps", "overall")
KNOWN_ERRORS = (QAPairingError, AnswerEvaluationError, RequirementMappingError, OverallEvaluationError)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Pure status rules (no DB, tested offline) ----------

def check_can_start(interview: Interview, turn_count: int, analysis: InterviewAnalysis | None) -> None:
    if interview.status != "completed":
        raise AppException("Only completed interviews can be analysed", 409, "INTERVIEW_NOT_COMPLETED")
    if turn_count == 0:
        raise AppException("The interview has no transcript", 409, "NO_TRANSCRIPT")
    if analysis is not None and analysis.status in ACTIVE:
        raise AppException("The analysis is already running", 409, "ANALYSIS_RUNNING")


def reset_for_run(analysis: InterviewAnalysis) -> None:
    """Re-run: new version, old results cleared, back to pending."""
    analysis.version = (analysis.version or 0) + 1
    analysis.status = "pending"
    analysis.error = None
    analysis.started_at = None
    analysis.finished_at = None
    for field in RESULT_FIELDS:
        setattr(analysis, field, None)


def apply_running(analysis: InterviewAnalysis | None, version: int) -> bool:
    if analysis is None or analysis.version != version or analysis.status != "pending":
        return False
    analysis.status = "running"
    analysis.started_at = _now()
    return True


def apply_result(analysis: InterviewAnalysis | None, version: int, result: dict) -> bool:
    """Save all results at once. Skipped when a newer run has replaced this one."""
    if analysis is None or analysis.version != version or analysis.status != "running":
        return False
    for field in RESULT_FIELDS:
        setattr(analysis, field, result[field])
    analysis.status = "completed"
    analysis.error = None
    analysis.finished_at = _now()
    return True


def apply_failure(analysis: InterviewAnalysis | None, version: int, error: str) -> bool:
    """Mark failed without any results (nothing half-saved)."""
    if analysis is None or analysis.version != version or analysis.status not in ACTIVE:
        return False
    for field in RESULT_FIELDS:
        setattr(analysis, field, None)
    analysis.status = "failed"
    analysis.error = error[:500]
    analysis.finished_at = _now()
    return True


# ---------- DB ----------

def get_analysis(db: Session, interview_id: int) -> InterviewAnalysis | None:
    return db.scalar(select(InterviewAnalysis).where(InterviewAnalysis.interview_id == interview_id))


def start_analysis(db: Session, interview: Interview) -> InterviewAnalysis:
    """Create or reset the analysis row. The workflow is started in the background by the API."""
    turn_count = db.scalar(
        select(func.count()).select_from(InterviewTranscriptTurn)
        .where(InterviewTranscriptTurn.interview_id == interview.id)
    )
    analysis = get_analysis(db, interview.id)
    check_can_start(interview, turn_count, analysis)
    if analysis is None:
        analysis = InterviewAnalysis(interview_id=interview.id, status="pending", version=1)
        db.add(analysis)
    else:
        reset_for_run(analysis)
    db.commit()
    db.refresh(analysis)
    logger.info("Interview %s: analysis v%s queued (%d turns)", interview.id, analysis.version, turn_count)
    return analysis


def _update(interview_id: int, apply, *args) -> bool:
    with SessionLocal() as db:
        ok = apply(get_analysis(db, interview_id), *args)
        if ok:
            db.commit()
        return ok


def mark_running(interview_id: int, version: int) -> bool:
    return _update(interview_id, apply_running, version)


def save_result(interview_id: int, version: int, result: dict) -> bool:
    ok = _update(interview_id, apply_result, version, result)
    if ok:
        logger.info("Interview %s: analysis v%s saved", interview_id, version)
    else:
        logger.warning("Interview %s: analysis v%s not saved (replaced or removed)", interview_id, version)
    return ok


def execute_analysis(interview_id: int, version: int) -> None:
    """Background task: run the workflow; on any failure mark the analysis failed."""
    from app.workflows.interview_analysis import run_analysis_workflow  # the workflow imports this module

    try:
        run_analysis_workflow(interview_id, version)
    except Exception as exc:
        if isinstance(exc, KNOWN_ERRORS):
            error = str(exc)
            logger.error("Interview %s: analysis v%s failed: %s", interview_id, version, error)
        else:
            error = f"Workflow error ({exc.__class__.__name__})"
            logger.exception("Interview %s: analysis v%s crashed", interview_id, version)
        _update(interview_id, apply_failure, version, error)


def mark_interrupted_analyses() -> None:
    """On startup: analyses left pending/running by a restart can't continue, so mark them failed."""
    with SessionLocal() as db:
        result = db.execute(
            update(InterviewAnalysis)
            .where(InterviewAnalysis.status.in_(ACTIVE))
            .values(status="failed", error="Interrupted by a server restart", finished_at=_now())
        )
        db.commit()
        if result.rowcount:
            logger.warning("Marked %s interrupted interview analysis(es) as failed", result.rowcount)
