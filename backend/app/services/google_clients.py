from functools import lru_cache
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.core.config import settings

SERVICE_ACCOUNT_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
BLOGGER_SCOPES = ["https://www.googleapis.com/auth/blogger"]


@lru_cache
def _service_account_credentials():
    return service_account.Credentials.from_service_account_file(
        settings.google_service_account_file, scopes=SERVICE_ACCOUNT_SCOPES
    )


def sheets_service():
    return build("sheets", "v4", credentials=_service_account_credentials(), cache_discovery=False)


def drive_service():
    return build("drive", "v3", credentials=_service_account_credentials(), cache_discovery=False)


def blogger_service():
    token_path = Path(settings.google_oauth_token_file)
    credentials = Credentials.from_authorized_user_file(str(token_path), BLOGGER_SCOPES)
    if not credentials.valid and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json())
    return build("blogger", "v3", credentials=credentials, cache_discovery=False)