import asyncio
import logging
import time

from app.services.rooms import rooms
from app.services.transcript_turns import Turn, log_turn_closed, log_turn_updated, turns

logger = logging.getLogger(__name__)

# Live transcript (7.3.1): sent on the room socket to the interviewer only, never queued.
# A reconnecting interviewer gets everything again in one transcript-snapshot.
INTERIM_INTERVAL_SECONDS = 0.25  # at most ~4 interim updates per second per speaker


async def _send(interview_id: int, message: dict) -> None:
    await rooms.send_to_role(interview_id, "interviewer", message)


async def turn_updated(turn: Turn) -> None:
    await log_turn_updated(turn)
    await _send(turn.interview_id, {"type": "transcript-turn", "turn": turn.to_message()})


async def turn_closed(turn: Turn) -> None:
    await log_turn_closed(turn)
    await _send(turn.interview_id, {"type": "transcript-turn", "turn": turn.to_message()})


async def status_changed(interview_id: int, role: str, state: str) -> None:
    await _send(interview_id, {"type": "transcript-status", "speaker": role, "state": state})


class InterimThrottle:
    """Sends each speaker's interim text at most every INTERIM_INTERVAL_SECONDS; the latest text
    is always sent in the end. A cleared interim (empty text) is sent at once."""

    def __init__(self) -> None:
        self._last: dict[tuple[int, str], float] = {}  # (interview_id, role) -> last send
        self._pending: dict[tuple[int, str], dict] = {}
        self._timers: dict[tuple[int, str], asyncio.Task] = {}

    async def push(self, interview_id: int, role: str, interim: dict | None) -> None:
        key = (interview_id, role)
        message = {
            "type": "transcript-interim",
            "speaker": role,
            "text": interim["text"] if interim else "",
            "start_s": interim["start_s"] if interim else None,
        }
        if interim is None:
            timer = self._timers.pop(key, None)
            if timer:
                timer.cancel()
            self._pending.pop(key, None)
            self._last.pop(key, None)
            await _send(interview_id, message)
            return
        wait = self._last.get(key, 0.0) + INTERIM_INTERVAL_SECONDS - time.monotonic()
        if wait <= 0 and key not in self._timers:
            self._last[key] = time.monotonic()
            await _send(interview_id, message)
            return
        self._pending[key] = message
        if key not in self._timers:
            self._timers[key] = asyncio.create_task(self._flush(key, wait))

    async def _flush(self, key: tuple[int, str], wait: float) -> None:
        await asyncio.sleep(max(wait, 0.0))
        self._timers.pop(key, None)
        message = self._pending.pop(key, None)
        if message:
            self._last[key] = time.monotonic()
            await _send(key[0], message)


_interims = InterimThrottle()
interim_changed = _interims.push


async def send_snapshot(interview_id: int) -> None:
    """All turns so far (saved and open), current interims and status, for a joining interviewer."""
    builder = await turns.get(interview_id)
    message = {
        "type": "transcript-snapshot",
        "turns": [t.to_message() for t in builder.turns],
        "interims": dict(builder.interims),  # role -> {"text", "start_s"}
        "status": dict(builder.status),
    }
    if await rooms.send_to_role(interview_id, "interviewer", message):
        logger.info("Interview %s: transcript snapshot sent (%d turns)", interview_id, len(builder.turns))
