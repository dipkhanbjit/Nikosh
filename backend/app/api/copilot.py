from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Interview, User
from app.schemas.copilot import CopilotChatRequest, CopilotChatResponse, SuggestedQuestionsResponse
from app.services.copilot import answer, stored_questions, suggest_questions

# Interviewer co-pilot: RAG over company docs, the candidate's CV and the job requirements
router = APIRouter(prefix="/interviews/{interview_id}/copilot", tags=["interview co-pilot"])


def _get_interview(db: Session, interview_id: int) -> Interview:
    interview = db.get(Interview, interview_id)
    if not interview:
        raise AppException("Interview not found", 404, "INTERVIEW_NOT_FOUND")
    return interview


@router.post("/chat", response_model=CopilotChatResponse)
def copilot_chat(
    interview_id: int,
    payload: CopilotChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("interviewer")),
):
    return answer(db, _get_interview(db, interview_id), payload.message, payload.history)


@router.get("/questions", response_model=SuggestedQuestionsResponse)
def get_questions(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("interviewer")),
):
    """Stored suggested questions (empty list if none yet). Never calls the LLM."""
    return stored_questions(_get_interview(db, interview_id))


@router.post("/questions", response_model=SuggestedQuestionsResponse)
def generate_questions(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("interviewer")),
):
    """Generate (or regenerate) the suggested questions with reference answers."""
    return suggest_questions(db, _get_interview(db, interview_id))
