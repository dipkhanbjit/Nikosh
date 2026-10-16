import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.models import Candidate, CandidateAssessment, Interview, InterviewAnalysis
from app.services.consolidated_assessment import AssessmentError

logger = logging.getLogger(__name__)

ACTIVE = ("pending", "running")
RESULT_FIELDS = ("score", "requirements", "findings")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Pure status rules (no DB, tested offline) ----------

def analysis_ready(analysis: InterviewAnalysis | None) -> bool:
    return analysis is not None and analysis.status == "completed" and (analysis.overall or {}).get("score") is not None


def check_can_start(candidate: Candidate, analysis: InterviewAnalysis | None,
                    assessment: CandidateAssessment | None) -> None:
    if candidate.screening_status != "screened" or candidate.scoring_status != "scored" or candidate.overall_score is None:
        raise AppException("The candidate's CV has not been screened and scored", 409, "CANDIDATE_NOT_SCORED")
    if not analysis_ready(analysis):
        raise AppException("Run the interview analysis first", 409, "INTERVIEW_NOT_ANALYSED")
    if assessment is not None and assessment.status in ACTIVE:
        raise AppException("The assessment is already running", 409, "ASSESSMENT_RUNNING")


def is_outdated(assessment: CandidateAssessment, analysis: InterviewAnalysis | None) -> bool:
    """True when the interview was re-analysed (or the analysis is gone) after the assessment was made."""
    return not analysis_ready(analysis) or analysis.version != assessment.analysis_version


def reset_for_run(assessment: CandidateAssessment, interview_id: int, analysis_version: int) -> None:
    """Re-run: new version, old results cleared, back to pending."""
    assessment.version = (assessment.version or 0) + 1
    assessment.interview_id = interview_id
    assessment.analysis_version = analysis_version
    assessment.status = "pending"
    assessment.error = None
    assessment.started_at = None
    assessment.finished_at = None
    for field in RESULT_FIELDS:
        setattr(assessment, field, None)


def apply_running(assessment: CandidateAssessment | None, version: int) -> bool:
    if assessment is None or assessment.version != version or assessment.status != "pending":
        return False
    assessment.status = "running"
    assessment.started_at = _now()
    return True


def apply_result(assessment: CandidateAssessment | None, version: int, result: dict) -> bool:
    """Save all results at once. Skipped when a newer run has replaced this one."""
    if assessment is None or assessment.version != version or assessment.status != "running":
        return False
    for field in RESULT_FIELDS:
        setattr(assessment, field, result[field])
    assessment.status = "completed"
    assessment.error = None
    assessment.finished_at = _now()
    return True


def apply_failure(assessment: CandidateAssessment | None, version: int, error: str) -> bool:
    """Mark failed without any results (nothing half-saved)."""
    if assessment is None or assessment.version != version or assessment.status not in ACTIVE:
        return False
    for field in RESULT_FIELDS:
        setattr(assessment, field, None)
    assessment.status = "failed"
    assessment.error = error[:500]
    assessment.finished_at = _now()
    return True


# ---------- DB ----------

def get_assessment(db: Session, candidate_id: int) -> CandidateAssessment | None:
    return db.scalar(select(CandidateAssessment).where(CandidateAssessment.candidate_id == candidate_id))


def latest_interview_analysis(db: Session, candidate_id: int) -> tuple[Interview | None, InterviewAnalysis | None]:
    """The candidate's latest completed interview and its analysis (if any)."""
    interview = db.scalar(
        select(Interview)
        .where(Interview.candidate_id == candidate_id, Interview.status == "completed")
        .order_by(Interview.scheduled_at.desc(), Interview.id.desc())
        .limit(1)
    )
    if interview is None:
        return None, None
    analysis = db.scalar(select(InterviewAnalysis).where(InterviewAnalysis.interview_id == interview.id))
    return interview, analysis


def start_assessment(db: Session, candidate: Candidate) -> CandidateAssessment:
    """Create or reset the assessment row. The workflow is started in the background by the API."""
    interview, analysis = latest_interview_analysis(db, candidate.id)
    assessment = get_assessment(db, candidate.id)
    check_can_start(candidate, analysis, assessment)
    if assessment is None:
        assessment = CandidateAssessment(
            candidate_id=candidate.id, interview_id=interview.id, analysis_version=analysis.version,
            status="pending", version=1,
        )
        db.add(assessment)
    else:
        reset_for_run(assessment, interview.id, analysis.version)
    db.commit()
    db.refresh(assessment)
    logger.info("Candidate %s: assessment v%s queued (interview %s, analysis v%s)",
                candidate.id, assessment.version, interview.id, analysis.version)
    return assessment


def _update(candidate_id: int, apply, *args) -> bool:
    with SessionLocal() as db:
        ok = apply(get_assessment(db, candidate_id), *args)
        if ok:
            db.commit()
        return ok


def mark_running(candidate_id: int, version: int) -> bool:
    return _update(candidate_id, apply_running, version)


def save_result(candidate_id: int, version: int, result: dict) -> bool:
    ok = _update(candidate_id, apply_result, version, result)
    if ok:
        logger.info("Candidate %s: assessment v%s saved", candidate_id, version)
    else:
        logger.warning("Candidate %s: assessment v%s not saved (replaced or removed)", candidate_id, version)
    return ok


def execute_assessment(candidate_id: int, version: int) -> None:
    """Background task: run the workflow; on any failure mark the assessment failed."""
    from app.workflows.consolidated_assessment import run_assessment_workflow  # the workflow imports this module

    try:
        run_assessment_workflow(candidate_id, version)
    except Exception as exc:
        if isinstance(exc, AssessmentError):
            error = str(exc)
            logger.error("Candidate %s: assessment v%s failed: %s", candidate_id, version, error)
        else:
            error = f"Workflow error ({exc.__class__.__name__})"
            logger.exception("Candidate %s: assessment v%s crashed", candidate_id, version)
        _update(candidate_id, apply_failure, version, error)


def mark_interrupted_assessments() -> None:
    """On startup: assessments left pending/running by a restart can't continue, so mark them failed."""
    with SessionLocal() as db:
        result = db.execute(
            update(CandidateAssessment)
            .where(CandidateAssessment.status.in_(ACTIVE))
            .values(status="failed", error="Interrupted by a server restart", finished_at=_now())
        )
        db.commit()
        if result.rowcount:
            logger.warning("Marked %s interrupted candidate assessment(s) as failed", result.rowcount)
