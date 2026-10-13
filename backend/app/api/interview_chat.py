import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Interview, InterviewMessage, User
from app.schemas.interview_message import InterviewMessageOut
from app.services.interview_chat import add_file, ensure_chat_open, list_messages, to_dict
from app.services.rooms import push_from_thread, rooms

logger = logging.getLogger(__name__)

# In-call chat: only the interviewer and the interview's own candidate
router = APIRouter(prefix="/interviews/{interview_id}", tags=["interview chat"])


def _participant(db: Session, interview_id: int, user: User) -> tuple[Interview, str, str | None]:
    """Returns the interview, the user's role in it and the sender name."""
    interview = db.get(Interview, interview_id)
    if not interview:
        raise AppException("Interview not found", 404, "INTERVIEW_NOT_FOUND")
    if user.role == "interviewer":
        return interview, "interviewer", user.full_name
    if user.role == "candidate" and interview.candidate.user_id == user.id:
        return interview, "candidate", interview.candidate.full_name or user.full_name
    logger.warning("Interview %s: chat access refused for user %s", interview_id, user.id)
    raise AppException("This interview belongs to another account", 403, "NOT_YOUR_INTERVIEW")


@router.get("/messages", response_model=list[InterviewMessageOut])
def get_messages(interview_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Chat history; still available after the interview has ended."""
    interview, _, _ = _participant(db, interview_id, user)
    return list_messages(db, interview.id)


@router.post("/files", response_model=InterviewMessageOut, status_code=201)
def upload_file(
    interview_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Share a file in the chat; both sides receive it as a chat message."""
    interview, role, name = _participant(db, interview_id, user)
    try:
        ensure_chat_open(interview)
        # read one byte more than the limit so a too large file is detected without reading it all
        data = file.file.read(settings.chat_max_file_mb * 1024 * 1024 + 1)
        message = add_file(db, interview, role, name, file.filename, data)
    except AppException as exc:
        logger.warning("Interview %s: %s upload refused (%s)", interview.id, role, exc.code)
        raise
    logger.info("Interview %s: %s shared file %s (%s bytes)", interview.id, role, message.id, message.file_size)
    push_from_thread(interview.id, rooms.broadcast, {"type": "chat", "message": to_dict(message)})
    return message


@router.get("/files/{message_id}")
def download_file(
    interview_id: int, message_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    interview, role, _ = _participant(db, interview_id, user)
    message = db.get(InterviewMessage, message_id)
    if not message or message.interview_id != interview.id or not message.file_path:
        logger.warning("Interview %s: %s download refused (file %s not found)", interview.id, role, message_id)
        raise AppException("File not found", 404, "FILE_NOT_FOUND")
    if not Path(message.file_path).exists():
        logger.warning("Interview %s: file %s missing on disk", interview.id, message_id)
        raise AppException("File not found", 404, "FILE_NOT_FOUND")
    logger.info("Interview %s: %s downloaded file %s", interview.id, role, message_id)
    return FileResponse(
        message.file_path,
        media_type=message.content_type or "application/octet-stream",
        filename=message.file_name,
        headers={"X-Content-Type-Options": "nosniff"},
    )
