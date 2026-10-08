import html

import httpx

from app.core.config import settings

TIMEOUT_SECONDS = 30


class PostingError(Exception):
    pass


def send_message(text: str) -> int:
    """Send an HTML message to the channel and return its message ID."""
    if not settings.telegram_bot_token or not settings.telegram_channel:
        raise PostingError("Telegram is not configured")

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        response = httpx.post(
            url,
            json={"chat_id": settings.telegram_channel, "text": text, "parse_mode": "HTML"},
            timeout=TIMEOUT_SECONDS,
        )
        data = response.json()
    except httpx.HTTPError as exc:
        raise PostingError(f"Could not reach Telegram: {exc.__class__.__name__}") from None

    if not data.get("ok"):
        raise PostingError(data.get("description", "Telegram rejected the post"))
    return data["result"]["message_id"]


def announce_job(title: str, details: str, link: str, apply_url: str | None = None) -> str:
    """Post a short job announcement linking to the full JD and the application form."""
    text = (
        f"<b>Job Opening: {html.escape(title)}</b>\n"
        f"{html.escape(details)}\n\n"
        f'<a href="{html.escape(link, quote=True)}">View full job description</a>'
    )
    if apply_url:
        text += f'\n<a href="{html.escape(apply_url, quote=True)}">Apply now</a>'
    message_id = send_message(text)
    channel = settings.telegram_channel.lstrip("@")
    return f"https://t.me/{channel}/{message_id}"