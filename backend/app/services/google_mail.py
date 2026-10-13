import base64
import logging
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.errors import HttpError

from app.services.google_clients import gmail_service

logger = logging.getLogger(__name__)


class MailError(Exception):
    pass


def _build_message(html: str, text: str, ics: str, ics_method: str) -> MIMEBase:
    """HTML only (old behaviour), or text + HTML, plus an optional calendar invite.
    The invite goes both inside the alternative part (so Gmail / Outlook show the
    invite card) and as an invite.ics attachment (the way Google Calendar sends it)."""
    if not text and not ics:
        return MIMEText(html, "html", "utf-8")

    body = MIMEMultipart("alternative")
    if text:
        body.attach(MIMEText(text, "plain", "utf-8"))
    body.attach(MIMEText(html, "html", "utf-8"))
    if not ics:
        return body

    method = ics_method.upper() or "REQUEST"
    body.attach(MIMEText(ics, f"calendar; method={method}", "utf-8"))
    attachment = MIMEText(ics, "calendar", "utf-8")
    attachment.set_param("method", method)
    attachment.add_header("Content-Disposition", "attachment", filename="invite.ics")

    message = MIMEMultipart("mixed")
    message.attach(body)
    message.attach(attachment)
    return message


def send_email(to: str, subject: str, html: str, text: str = "", ics: str = "", ics_method: str = "") -> str:
    """Send an HTML email from the authorized Google account, optionally with a plain-text
    part and a calendar invite (ics text, method REQUEST or CANCEL). Returns the Gmail message id."""
    message = _build_message(html, text, ics, ics_method)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        sent = gmail_service().users().messages().send(userId="me", body={"raw": raw}).execute()
    except HttpError as exc:
        logger.error("Gmail: sending '%s' to %s failed: %s", subject, to, exc)
        raise MailError(f"Could not send the email (Google API error {exc.status_code})") from None
    return sent["id"]
