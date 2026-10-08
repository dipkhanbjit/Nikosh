from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from app.core.config import settings

SCOPES = ["https://www.googleapis.com/auth/blogger"]


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file(settings.google_oauth_client_file, SCOPES)
    credentials = flow.run_local_server(port=0)
    Path(settings.google_oauth_token_file).write_text(credentials.to_json())
    print(f"Blogger token saved to {settings.google_oauth_token_file}")


if __name__ == "__main__":
    main()