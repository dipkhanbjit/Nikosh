import html
import re

import httpx

from app.core.config import settings

TELEGRAM_LIMIT = 4096
TIMEOUT_SECONDS = 30


class PostingError(Exception):
    pass


def markdown_to_telegram_html(markdown: str) -> str:
    lines = []
    for raw in markdown.splitlines():
        line = html.escape(raw.strip())
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        if line.startswith("#"):
            line = f"<b>{line.lstrip('#').strip()}</b>"
        elif line.startswith(("- ", "* ")):
            line = f"• {line[2:]}"
        lines.append(line)
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    parts, current = [], ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = block[:limit]
    if current:
        parts.append(current)
    return parts


def post_job(title: str, description: str) -> str:
    """Post a JD to the Telegram channel and return the public post URL."""
    if not settings.telegram_bot_token or not settings.telegram_channel:
        raise PostingError("Telegram is not configured")

    text = f"<b>Job Opening: {html.escape(title)}</b>\n\n" + markdown_to_telegram_html(description)
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    first_message_id = None

    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            for part in split_message(text):
                response = client.post(url, json={
                    "chat_id": settings.telegram_channel,
                    "text": part,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                })
                data = response.json()
                if not data.get("ok"):
                    raise PostingError(data.get("description", "Telegram rejected the post"))
                first_message_id = first_message_id or data["result"]["message_id"]
    except httpx.HTTPError as exc:
        raise PostingError(f"Could not reach Telegram: {exc.__class__.__name__}") from None

    channel = settings.telegram_channel.lstrip("@")
    return f"https://t.me/{channel}/{first_message_id}"