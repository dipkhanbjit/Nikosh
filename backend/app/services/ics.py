"""Minimal iCalendar (RFC 5545) builder for interview invitations. No external library."""
from datetime import datetime, timedelta, timezone

DHAKA = timezone(timedelta(hours=6), "Asia/Dhaka")  # Bangladesh has no daylight saving

VTIMEZONE = [
    "BEGIN:VTIMEZONE",
    "TZID:Asia/Dhaka",
    "BEGIN:STANDARD",
    "DTSTART:19700101T000000",
    "TZOFFSETFROM:+0600",
    "TZOFFSETTO:+0600",
    "TZNAME:+06",
    "END:STANDARD",
    "END:VTIMEZONE",
]


def _text(value: str) -> str:
    """Escape a TEXT value."""
    return (
        value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\r\n", "\\n").replace("\n", "\\n")
    )


def _param(value: str) -> str:
    """Quote a parameter value (e.g. CN) and drop characters it cannot contain."""
    return '"' + value.replace('"', "").replace("\r", "").replace("\n", " ") + '"'


def _fold(line: str) -> str:
    """Fold a content line to at most 75 octets, without splitting UTF-8 characters."""
    parts, current, size = [], "", 0
    for char in line:
        length = len(char.encode("utf-8"))
        limit = 75 if not parts else 74  # continuation lines start with a space
        if size + length > limit:
            parts.append(current)
            current, size = "", 0
        current += char
        size += length
    parts.append(current)
    return "\r\n ".join(parts)


def _local(dt: datetime) -> str:
    return dt.astimezone(DHAKA).strftime("%Y%m%dT%H%M%S")


def build_ics(
    method: str,
    uid: str,
    sequence: int,
    start: datetime,
    end: datetime,
    summary: str,
    description: str,
    organizer_email: str,
    organizer_name: str,
    attendee_email: str,
    attendee_name: str,
) -> str:
    """Build a one-event calendar with METHOD REQUEST (invite / update) or CANCEL.
    The same uid with a higher sequence updates or cancels the earlier invite."""
    method = method.upper()
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//Nirvik Technology//Nikosh//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        f"METHOD:{method}",
        *VTIMEZONE,
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SEQUENCE:{sequence}",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID=Asia/Dhaka:{_local(start)}",
        f"DTEND;TZID=Asia/Dhaka:{_local(end)}",
        f"SUMMARY:{_text(summary)}",
        f"DESCRIPTION:{_text(description)}",
        f"ORGANIZER;CN={_param(organizer_name)}:mailto:{organizer_email}",
        f"ATTENDEE;CN={_param(attendee_name)};ROLE=REQ-PARTICIPANT;"
        f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{attendee_email}",
        "STATUS:CANCELLED" if method == "CANCEL" else "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
