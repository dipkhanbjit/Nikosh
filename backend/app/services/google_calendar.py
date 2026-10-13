import logging

from googleapiclient.errors import HttpError

from app.services.google_clients import calendar_service

logger = logging.getLogger(__name__)

TIMEZONE = "Asia/Dhaka"


class CalendarError(Exception):
    pass


def _google_error(action: str, exc: HttpError) -> CalendarError:
    logger.error("Google Calendar: %s failed: %s", action, exc)
    return CalendarError(f"Could not {action} (Google API error {exc.status_code})")


def create_event(
    summary: str, description: str, start: str, end: str, attendee_email: str, uid: str = ""
) -> dict:
    """Create an event on the primary calendar with the attendee listed as a guest.
    Google sends no email (the app sends its own invitation with an .ics); uid, if given,
    becomes the event's iCalUID so both are the same event. Returns {event_id, html_link}."""
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start, "timeZone": TIMEZONE},
        "end": {"dateTime": end, "timeZone": TIMEZONE},
        "attendees": [{"email": attendee_email}],
    }
    if uid:
        body["iCalUID"] = uid
    try:
        event = calendar_service().events().insert(
            calendarId="primary", body=body, sendUpdates="none"
        ).execute()
    except HttpError as exc:
        raise _google_error("create the calendar event", exc) from None
    return {"event_id": event["id"], "html_link": event.get("htmlLink", "")}


def delete_event(event_id: str) -> bool:
    """Delete an event without emailing attendees. Returns False if it no longer exists."""
    try:
        calendar_service().events().delete(
            calendarId="primary", eventId=event_id, sendUpdates="none"
        ).execute()
    except HttpError as exc:
        if exc.status_code in (404, 410):
            logger.info("Google Calendar: event %s not found (already deleted)", event_id)
            return False
        raise _google_error("delete the calendar event", exc) from None
    return True
