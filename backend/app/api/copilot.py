from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Interview, User
from app.schemas.copilot import CopilotChatRequest, CopilotChatResponse
from app.services.copilot import answer

# Interviewer co-pilot: RAG over company docs, the candidate's CV and the job requirements
router = APIRouter(prefix="/interviews/{interview_id}/copilot", tags=["interview co-pilot"])


@router.post("/chat", response_model=CopilotChatResponse)
def copilot_chat(
    interview_id: int,
    payload: CopilotChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("interviewer")),
):
    interview = db.get(Interview, interview_id)
    if not interview:
        raise AppException("Interview not found", 404, "INTERVIEW_NOT_FOUND")
    return answer(db, interview, payload.message, payload.history)
