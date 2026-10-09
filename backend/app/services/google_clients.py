from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.core.config import settings

# User OAuth token: Blogger posting, per-job Google Forms, and CV downloads
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/blogger",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/drive",
]


def _oauth_credentials() -> Credentials:
    token_path = Path(settings.google_oauth_token_file)
    credentials = Credentials.from_authorized_user_file(str(token_path), OAUTH_SCOPES)
    if not credentials.valid and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json())
    return credentials


def blogger_service():
    return build("blogger", "v3", credentials=_oauth_credentials(), cache_discovery=False)


def forms_service():
    return build("forms", "v1", credentials=_oauth_credentials(), cache_discovery=False)


def user_drive_service():
    return build("drive", "v3", credentials=_oauth_credentials(), cache_discovery=False)