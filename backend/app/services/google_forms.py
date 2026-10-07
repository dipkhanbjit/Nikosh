import io
import re
from datetime import datetime

from googleapiclient.http import MediaIoBaseDownload

from app.core.config import settings
from app.services.google_clients import drive_service, sheets_service

FILE_ID_PATTERN = re.compile(r"[?&]id=([\w-]+)|/d/([\w-]+)")
TIMESTAMP_FORMATS = ("%m/%d/%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S")

COLUMNS = {
    "timestamp": "Timestamp",
    "email": "Email address",
    "full_name": "Full Name",
    "phone": "Phone Number",
    "job_id": "Job ID",
    "cv": "CV",
}


class GoogleFormsError(Exception):
    pass


def _file_id(cv_link: str) -> str | None:
    match = FILE_ID_PATTERN.search(cv_link or "")
    return (match.group(1) or match.group(2)) if match else None


def _timestamp(value: str) -> str | None:
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value, fmt).isoformat()
        except (ValueError, TypeError):
            continue
    return None


def list_applications(job_id: int) -> list[dict]:
    """Return all form submissions for the given job from the responses Sheet."""
    if not settings.google_sheet_id:
        raise GoogleFormsError("Google Sheet is not configured")
    try:
        result = sheets_service().spreadsheets().values().get(
            spreadsheetId=settings.google_sheet_id, range="A1:Z"
        ).execute()
    except Exception as exc:
        raise GoogleFormsError(f"Could not read the responses Sheet: {exc.__class__.__name__}") from None

    rows = result.get("values", [])
    if not rows:
        return []

    header = rows[0]
    index = {key: header.index(name) for key, name in COLUMNS.items() if name in header}
    missing = [COLUMNS[k] for k in COLUMNS if k not in index]
    if missing:
        raise GoogleFormsError(f"Sheet is missing columns: {', '.join(missing)}")

    applications = []
    for row in rows[1:]:
        cell = lambda key: row[index[key]].strip() if index[key] < len(row) else ""
        if cell("job_id") != str(job_id):
            continue
        file_id = _file_id(cell("cv"))
        if not file_id:
            continue
        applications.append({
            "file_id": file_id,
            "full_name": cell("full_name") or None,
            "email": cell("email") or None,
            "phone": cell("phone") or None,
            "submitted_at": _timestamp(cell("timestamp")),
        })
    return applications


def download_file(file_id: str) -> tuple[str, bytes]:
    """Download a Drive file and return (original filename, content)."""
    try:
        drive = drive_service()
        meta = drive.files().get(fileId=file_id, fields="name").execute()
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, drive.files().get_media(fileId=file_id))
        done = False
        while not done:
            _, done = downloader.next_chunk()
    except Exception as exc:
        raise GoogleFormsError(f"Could not download CV from Drive: {exc.__class__.__name__}") from None
    return meta["name"], buffer.getvalue()