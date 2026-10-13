import asyncio
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Same meaning as in rooms.py: replaced by a newer connection (do not reconnect)
CLOSE_REPLACED = 4000

# LINEAR16 mono at 16 kHz = 32000 bytes per second of audio
BYTES_PER_SECOND = 16000 * 2


@dataclass(eq=False)
class AudioConnection:
    ws: WebSocket
    role: str
    bytes_received: int = 0

    async def close(self, code: int = 1000, reason: str = "") -> None:
        try:
            await self.ws.close(code=code, reason=reason)
        except Exception:
            pass  # already closed


@dataclass
class SpeakerTotal:
    bytes: int = 0
    connections: int = 0  # > 1 = the speaker reconnected

    @property
    def seconds(self) -> float:
        return self.bytes / BYTES_PER_SECOND


@dataclass
class AudioSession:
    conns: dict[str, AudioConnection] = field(default_factory=dict)
    totals: dict[str, SpeakerTotal] = field(default_factory=dict)


class AudioManager:
    """In-memory audio sockets: at most one per role per interview, plus a running total per
    speaker (kept until the interview ends). Single Uvicorn worker, like the room registry.
    STT is connected in Module 7; saving to disk in 6.4.2."""

    def __init__(self) -> None:
        self._sessions: dict[int, AudioSession] = {}
        self._lock = asyncio.Lock()

    async def join(self, interview_id: int, conn: AudioConnection) -> None:
        async with self._lock:
            session = self._sessions.setdefault(interview_id, AudioSession())
            old = session.conns.get(conn.role)
            session.conns[conn.role] = conn
            session.totals.setdefault(conn.role, SpeakerTotal()).connections += 1
        if old:
            logger.info("Interview %s: %s audio connection replaced by a new one", interview_id, conn.role)
            await old.close(CLOSE_REPLACED, "Replaced by a new connection")

    def add_chunk(self, interview_id: int, conn: AudioConnection, size: int) -> None:
        conn.bytes_received += size
        session = self._sessions.get(interview_id)
        if session and conn.role in session.totals:
            session.totals[conn.role].bytes += size

    def total(self, interview_id: int, role: str) -> SpeakerTotal:
        session = self._sessions.get(interview_id)
        return session.totals.get(role, SpeakerTotal()) if session else SpeakerTotal()

    async def leave(self, interview_id: int, conn: AudioConnection) -> None:
        async with self._lock:
            session = self._sessions.get(interview_id)
            if session and session.conns.get(conn.role) is conn:
                del session.conns[conn.role]

    async def close_interview(self, interview_id: int, reason: str) -> None:
        """The interview is over: close its audio sockets and log the totals per speaker."""
        async with self._lock:
            session = self._sessions.pop(interview_id, None)
        if not session:
            return
        for conn in session.conns.values():
            await conn.close(1000, reason)
        for role, total in session.totals.items():
            logger.info(
                "Interview %s: total %s audio received %.1f s (%d bytes)", interview_id, role, total.seconds, total.bytes
            )


audio = AudioManager()
