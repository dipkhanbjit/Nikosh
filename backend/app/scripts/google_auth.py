from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from app.core.config import settings
from app.services.google_clients import OAUTH_SCOPES


def main() -> None:
    """One-time sign-in: grants Nikosh access to Blogger, Google Forms and Drive."""
    flow = InstalledAppFlow.from_client_secrets_file(settings.google_oauth_client_file, OAUTH_SCOPES)
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    Path(settings.google_oauth_token_file).write_text(credentials.to_json())
    print(f"Google token saved to {settings.google_oauth_token_file}")


if __name__ == "__main__":
    main()