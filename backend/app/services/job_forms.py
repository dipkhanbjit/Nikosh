import io
import logging

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.core.config import settings
from app.services.google_clients import forms_service, user_drive_service

logger = logging.getLogger(__name__)

# Template question titles (lowercase) → response field names
FIELDS = {"full name": "full_name", "email": "email", "phone number": "phone", "cv": "cv"}


class FormError(Exception):
    pass


def _google_error(action: str, exc: HttpError) -> FormError:
    logger.error("Google Forms: %s failed: %s", action, exc)
    return FormError(f"Could not {action} (Google API error {exc.status_code})")


def create_job_form(title: str, description: str) -> dict:
    """Copy the template form for one job, set its title/description and open it."""
    if not settings.google_form_template_id:
        raise FormError("GOOGLE_FORM_TEMPLATE_ID is not set")
    try:
        copy = (
            user_drive_service()
            .files()
            .copy(fileId=settings.google_form_template_id, body={"name": title}, fields="id")
            .execute()
        )
        form_id = copy["id"]
        forms = forms_service().forms()
        forms.batchUpdate(
            formId=form_id,
            body={
                "requests": [
                    {
                        "updateFormInfo": {
                            "info": {"title": title, "description": description},
                            "updateMask": "title,description",
                        }
                    }
                ]
            },
        ).execute()
        set_form_open(form_id, True)
        form_url = forms.get(formId=form_id).execute()["responderUri"]
    except HttpError as exc:
        raise _google_error("create the application form", exc) from None
    logger.info("Google Forms: created form %s (%s)", form_id, title)
    return {"form_id": form_id, "form_url": form_url}


def set_form_open(form_id: str, accepting: bool) -> None:
    """Publish the form and open or close it for responses."""
    try:
        forms_service().forms().setPublishSettings(
            formId=form_id,
            body={
                "publishSettings": {
                    "publishState": {"isPublished": True, "isAcceptingResponses": accepting}
                },
                "updateMask": "publishState",
            },
        ).execute()
    except HttpError as exc:
        raise _google_error("open the form" if accepting else "close the form", exc) from None
    logger.info("Google Forms: form %s %s", form_id, "opened" if accepting else "closed")


def list_responses(form_id: str) -> list[dict]:
    """All responses of a job form as simple dicts (full_name, email, phone, cv_file_id, ...)."""
    try:
        forms = forms_service().forms()
        form = forms.get(formId=form_id).execute()
        question_fields = {}
        for item in form.get("items", []):
            question = item.get("questionItem", {}).get("question")
            field = FIELDS.get(item.get("title", "").strip().lower())
            if question and field:
                question_fields[question["questionId"]] = field

        results, page_token = [], None
        while True:
            page = forms.responses().list(formId=form_id, pageToken=page_token).execute()
            for response in page.get("responses", []):
                results.append(_parse_response(response, question_fields))
            page_token = page.get("nextPageToken")
            if not page_token:
                break
    except HttpError as exc:
        raise _google_error("read form responses", exc) from None
    return results


def _parse_response(response: dict, question_fields: dict) -> dict:
    row = {
        "response_id": response["responseId"],
        "submitted_at": response.get("lastSubmittedTime") or response.get("createTime"),
    }
    for question_id, answer in response.get("answers", {}).items():
        field = question_fields.get(question_id)
        if field == "cv":
            files = answer.get("fileUploadAnswers", {}).get("answers", [])
            if files:
                row["cv_file_id"] = files[0]["fileId"]
                row["cv_filename"] = files[0].get("fileName")
        elif field:
            texts = answer.get("textAnswers", {}).get("answers", [])
            row[field] = texts[0]["value"].strip() if texts else ""
    return row


def download_file(file_id: str) -> tuple[str, bytes]:
    """Download an uploaded CV from Drive. Returns (file name, content)."""
    try:
        drive = user_drive_service()
        name = drive.files().get(fileId=file_id, fields="name").execute()["name"]
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, drive.files().get_media(fileId=file_id))
        done = False
        while not done:
            _, done = downloader.next_chunk()
    except HttpError as exc:
        raise _google_error("download the CV", exc) from None
    return name, buffer.getvalue()