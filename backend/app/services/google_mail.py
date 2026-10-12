import base64
import logging
from email.mime.text import MIMEText

from googleapiclient.errors import HttpError

from app.services.google_clients import gmail_service

logger = logging.getLogger(__name__)


class MailError(Exception):
    pass


def send_email(to: str, subject: str, html: str) -> str:
    """Send an HTML email from the authorized Google account. Returns the Gmail message id."""
    message = MIMEText(html, "html", "utf-8")
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        sent = gmail_service().users().messages().send(userId="me", body={"raw": raw}).execute()
    except HttpError as exc:
        logger.error("Gmail: sending '%s' to %s failed: %s", subject, to, exc)
        raise MailError(f"Could not send the email (Google API error {exc.status_code})") from None
    return sent["id"]
