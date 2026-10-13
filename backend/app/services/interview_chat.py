import logging
import mimetypes
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.models import Interview, InterviewMessage
from app.schemas.interview_message import InterviewMessageOut
from app.services.interviews import room_open

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 2000
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}


def to_dict(message: InterviewMessage) -> dict:
    """JSON-ready message for the room socket."""
    return InterviewMessageOut.model_validate(message).model_dump(mode="json")


def list_messages(db: Session, interview_id: int) -> list[InterviewMessage]:
    return list(
        db.scalars(
            select(InterviewMessage)
            .where(InterviewMessage.interview_id == interview_id)
            .order_by(InterviewMessage.created_at, InterviewMessage.id)
        )
    )


def ensure_chat_open(interview: Interview) -> None:
    """New messages and uploads only while the room is open; history and downloads always."""
    if not room_open(interview):
        raise AppException("The interview has ended; the chat is read-only", 409, "CHAT_CLOSED")


def add_text(db: Session, interview: Interview, role: str, name: str | None, text: str) -> InterviewMessage | None:
    text = (text or "").strip()[:MAX_TEXT_LENGTH]
    if not text:
        return None
    message = InterviewMessage(interview_id=interview.id, sender_role=role, sender_name=name, text=text)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def interview_dir(interview_id: int) -> Path:
    return Path(settings.interview_files_dir) / str(interview_id)


def add_file(
    db: Session, interview: Interview, role: str, name: str | None, filename: str, data: bytes
) -> InterviewMessage:
    """Validate and store a shared file, then save it as a chat message."""
    safe_name = Path(filename or "").name.strip()[:255]
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AppException("This file type is not allowed", 400, "FILE_TYPE_NOT_ALLOWED")
    if not data:
        raise AppException("The file is empty", 400, "EMPTY_FILE")
    if len(data) > settings.chat_max_file_mb * 1024 * 1024:
        raise AppException(f"The file is larger than {settings.chat_max_file_mb} MB", 400, "FILE_TOO_LARGE")

    folder = interview_dir(interview.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{ext}"  # random stored name; the original name is kept in the DB
    path.write_bytes(data)

    message = InterviewMessage(
        interview_id=interview.id,
        sender_role=role,
        sender_name=name,
        file_name=safe_name,
        file_path=str(path),
        file_size=len(data),
        content_type=mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def delete_interview_files(interview_ids: list[int]) -> None:
    """Remove the shared files of these interviews (the messages go with the DB cascade)."""
    for interview_id in interview_ids:
        folder = interview_dir(interview_id)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
            logger.info("Interview %s: chat files deleted", interview_id)
