"""Scheduling assistant rules: name matching, email choice and slot assignment.

Pure code (no LLM, no database), so every rule can be unit tested.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.interview import DEFAULT_DURATION_MINUTES, MAX_DURATION_MINUTES, MIN_DURATION_MINUTES
from app.services.ics import DHAKA

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_GAP_MINUTES = 120
MAX_SEARCH_STEPS = 500
DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class CandidateRequest(BaseModel):
    name: str = Field(description="Candidate name as the interviewer wrote it")
    date: str | None = Field(None, description="YYYY-MM-DD, only if this candidate gets a different day")
    start_time: str | None = Field(None, description="HH:MM (24-hour), only if this candidate gets a time")
    email: str | None = Field(None, description="Email address given for this candidate, exactly as written")


class ScheduleIntent(BaseModel):
    """What the interviewer asked for, as read by the LLM. The code validates everything."""
    selection: Literal["all", "top_n", "names"] = Field(
        description="all = every shortlisted candidate, top_n = the first N in rank order, "
        "names = only the named candidates"
    )
    top_n: int | None = Field(None, description="N when selection is top_n")
    names: list[str] = Field(default_factory=list, description="Names when selection is names")
    date: str | None = Field(None, description="Interview day, YYYY-MM-DD")
    start_time: str | None = Field(None, description="First interview start, HH:MM (24-hour)")
    duration_min: int | None = Field(None, description="Length of each interview in minutes")
    gap_min: int | None = Field(None, description="Break between interviews in minutes")
    candidates: list[CandidateRequest] = Field(
        default_factory=list,
        description="Only candidates who get their own time, day or email",
    )


@dataclass(frozen=True)
class Rules:
    working_days: frozenset[int]  # 0 = Monday
    office_start: time
    office_end: time


def rules_from_settings() -> Rules:
    days = frozenset(
        DAY_NAMES.index(day.strip().lower()[:3]) for day in settings.working_days.split(",") if day.strip()
    )
    if not days:
        raise ValueError("WORKING_DAYS must name at least one day")
    return Rules(days, time.fromisoformat(settings.office_start), time.fromisoformat(settings.office_end))


class PlanQuestion(Exception):
    """The instruction cannot be planned as given; the message is asked back to the interviewer."""


def _norm(text: str | None) -> str:
    return " ".join((text or "").lower().split())


def match_name(name: str, candidates: list) -> object:
    """The one shortlisted candidate this name refers to (exact name, else every word a name prefix)."""
    query = _norm(name)
    found = [c for c in candidates if _norm(c.full_name) == query]
    if not found:
        words = query.split()
        found = [
            c for c in candidates
            if words and all(any(part.startswith(w) for part in _norm(c.full_name).split()) for w in words)
        ]
    if len(found) == 1:
        return found[0]
    if not found:
        raise PlanQuestion(f'No shortlisted candidate matches "{name}". Please check the name.')
    options = ", ".join(c.full_name or f"#{c.id}" for c in found)
    raise PlanQuestion(f'"{name}" matches {options}. Which one do you mean?')


def pick_email(candidate, chat_email: str | None = None) -> tuple[str | None, str | None]:
    """Email and its source: chat -> application form -> CV."""
    if chat_email:
        return chat_email.strip().lower(), "chat"
    if candidate.source == "form" and candidate.email:
        return candidate.email, "form"
    cv_email = (candidate.profile or {}).get("email")
    if cv_email:
        return cv_email.strip().lower(), "cv"
    if candidate.email:  # uploaded CV: the stored email came from the CV
        return candidate.email, "cv"
    return None, None


def _parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise PlanQuestion(f"I could not read the date for {label}. Which day do you mean?") from None


def _parse_time(value: str, label: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise PlanQuestion(f"I could not read the start time for {label}. What time do you mean?") from None


def _at(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=DHAKA)


def _fmt(moment: datetime) -> str:
    return moment.astimezone(DHAKA).strftime("%a %d %b %H:%M")


def _next_working_day(day: date, rules: Rules) -> date:
    day += timedelta(days=1)
    while day.weekday() not in rules.working_days:
        day += timedelta(days=1)
    return day


def _check_working_day(day: date, rules: Rules) -> None:
    if day.weekday() not in rules.working_days:
        suggestion = _next_working_day(day, rules)
        raise PlanQuestion(
            f"{day:%A %d %b} is not a working day. Shall I use {suggestion:%A %d %b} instead?"
        )


def _conflict(start: datetime, end: datetime, taken: list[tuple[datetime, datetime]]):
    return next(((s, e) for s, e in taken if s < end and start < e), None)


def _check_start(start: datetime, minutes: int, now: datetime, rules: Rules, label: str) -> None:
    """A requested start must be in the future, on a working day and inside office hours."""
    if start <= now:
        raise PlanQuestion(f"{label}: {_fmt(start)} has already passed. Please choose a later time.")
    _check_working_day(start.date(), rules)
    end = start + timedelta(minutes=minutes)
    if start.time() < rules.office_start or end > _at(start.date(), rules.office_end):
        raise PlanQuestion(
            f"{label}: {_fmt(start)} is outside office hours "
            f"({rules.office_start:%H:%M}-{rules.office_end:%H:%M}). Please choose another time."
        )


def _next_free(cursor: datetime, minutes: int, gap: int, taken: list, rules: Rules) -> datetime:
    """First start at or after cursor inside office hours on a working day, overlapping nothing."""
    length = timedelta(minutes=minutes)
    for _ in range(MAX_SEARCH_STEPS):
        day = cursor.date()
        if day.weekday() not in rules.working_days or cursor + length > _at(day, rules.office_end):
            cursor = _at(_next_working_day(day, rules), rules.office_start)
            continue
        if cursor.time() < rules.office_start:
            cursor = _at(day, rules.office_start)
            continue
        conflict = _conflict(cursor, cursor + length, taken)
        if conflict:
            cursor = conflict[1] + timedelta(minutes=gap)
            continue
        return cursor
    raise PlanQuestion("I could not find enough free slots. Please choose another day.")


def _item(candidate, email: str, source: str, start: datetime, minutes: int) -> dict:
    return {
        "candidate_id": candidate.id,
        "name": candidate.full_name,
        "email": email,
        "email_source": source,
        "start": start.isoformat(),  # Asia/Dhaka, +06:00
        "duration_min": minutes,
    }


def _plan(intent: ScheduleIntent, shortlisted: list, active_ids: set[int], busy: list,
          now: datetime, rules: Rules, skipped: list) -> tuple[list[dict], str]:
    minutes = intent.duration_min or DEFAULT_DURATION_MINUTES
    if not MIN_DURATION_MINUTES <= minutes <= MAX_DURATION_MINUTES:
        raise PlanQuestion(
            f"Duration must be between {MIN_DURATION_MINUTES} and {MAX_DURATION_MINUTES} minutes."
        )
    gap = intent.gap_min or 0
    if not 0 <= gap <= MAX_GAP_MINUTES:
        raise PlanQuestion(f"The gap must be between 0 and {MAX_GAP_MINUTES} minutes.")

    # Who: shortlisted is in rank order, so top N is its first N
    if intent.selection == "all":
        chosen = list(shortlisted)
    elif intent.selection == "top_n":
        if not intent.top_n or intent.top_n < 1:
            raise PlanQuestion("How many candidates should I schedule?")
        chosen = list(shortlisted[:intent.top_n])
    else:
        if not intent.names:
            raise PlanQuestion("Which candidates should I schedule?")
        chosen = [match_name(name, shortlisted) for name in intent.names]
    requests = {}
    for request in intent.candidates:
        candidate = match_name(request.name, shortlisted)
        requests[candidate.id] = request
        chosen.append(candidate)
    seen = set()
    chosen = [c for c in chosen if not (c.id in seen or seen.add(c.id))]

    entries = []
    for candidate in chosen:
        request = requests.get(candidate.id)
        if candidate.id in active_ids:
            skipped.append({"candidate_id": candidate.id, "name": candidate.full_name,
                            "reason": "Already has an active interview"})
            continue
        chat_email = request.email if request else None
        if chat_email and not EMAIL_RE.match(chat_email.strip()):
            raise PlanQuestion(f'"{chat_email}" is not a valid email address. Please check it.')
        email, source = pick_email(candidate, chat_email)
        if not email:
            skipped.append({"candidate_id": candidate.id, "name": candidate.full_name,
                            "reason": "No email address (give one in the message)"})
            continue
        entries.append((candidate, request, email, source))
    if not entries:
        raise PlanQuestion("There is no one left to schedule.")

    main_day = _parse_date(intent.date, "the interviews") if intent.date else None
    main_time = _parse_time(intent.start_time, "the interviews") if intent.start_time else None
    fixed = [e for e in entries if e[1] and e[1].start_time]
    free = [e for e in entries if not (e[1] and e[1].start_time)]
    for candidate, request, _, _ in free:
        if request and request.date:
            raise PlanQuestion(f"What time should {candidate.full_name}'s interview start?")
    if free and not main_day:
        raise PlanQuestion("Which date should the interviews be on?")
    if free and not main_time:
        raise PlanQuestion("What time should the first interview start?")

    taken = list(busy)
    items = []
    length = timedelta(minutes=minutes)
    # Per-candidate times first, exactly as asked
    for candidate, request, email, source in fixed:
        label = candidate.full_name or f"Candidate #{candidate.id}"
        day = _parse_date(request.date, label) if request.date else main_day
        if not day:
            raise PlanQuestion(f"Which date should {label}'s interview be on?")
        start = _at(day, _parse_time(request.start_time, label))
        _check_start(start, minutes, now, rules, label)
        if _conflict(start, start + length, taken):
            raise PlanQuestion(f"{label}: {_fmt(start)} overlaps another interview. Please choose another time.")
        taken.append((start, start + length))
        items.append(_item(candidate, email, source, start, minutes))

    # Everyone else in consecutive slots
    notes = []
    if free:
        cursor = _at(main_day, main_time)
        _check_start(cursor, minutes, now, rules, "Start time")
        for candidate, _, email, source in free:
            start = _next_free(cursor, minutes, gap, taken, rules)
            if start.date() != main_day and "next_day" not in notes:
                notes.append("next_day")
            elif start.date() == main_day and start != cursor and "moved" not in notes:
                notes.append("moved")
            taken.append((start, start + length))
            items.append(_item(candidate, email, source, start, minutes))
            cursor = start + length + timedelta(minutes=gap)

    items.sort(key=lambda item: item["start"])
    message = f"{len(items)} interview{'s' if len(items) != 1 else ''} planned."
    if "moved" in notes:
        message += " Some times were moved to avoid other interviews."
    if "next_day" in notes:
        message += f" Interviews that did not fit before {rules.office_end:%H:%M} continue on the next working day."
    return items, message


def build_plan(intent: ScheduleIntent, shortlisted: list, active_ids: set[int],
               busy: list[tuple[datetime, datetime]], now: datetime, rules: Rules) -> dict:
    """Plan from the intent. shortlisted: the job's shortlisted candidates in rank order;
    active_ids: candidates of this job with an active interview; busy: active interview
    slots of all jobs. Returns {items, skipped, message, question}."""
    skipped: list[dict] = []
    try:
        items, message = _plan(intent, shortlisted, active_ids, busy, now, rules, skipped)
    except PlanQuestion as question:
        return {"items": [], "skipped": skipped, "message": None, "question": str(question)}
    return {"items": items, "skipped": skipped, "message": message, "question": None}
