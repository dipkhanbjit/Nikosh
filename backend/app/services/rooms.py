import asyncio
import logging
from dataclasses import dataclass, field

import anyio.from_thread
from fastapi import WebSocket

from app.services.audio import audio

logger = logging.getLogger(__name__)

# Close codes: 1000 normal, 4000 replaced by a newer connection (do not reconnect)
CLOSE_REPLACED = 4000


def other_role(role: str) -> str:
    return "candidate" if role == "interviewer" else "interviewer"


@dataclass(eq=False)
class Connection:
    ws: WebSocket
    role: str
    name: str
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, message: dict) -> None:
        """Send one JSON message; a broken connection is ignored (its own loop cleans it up)."""
        try:
            async with self.send_lock:
                await self.ws.send_json(message)
        except Exception:
            logger.debug("Send to %s failed", self.role)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        try:
            await self.ws.close(code=code, reason=reason)
        except Exception:
            pass  # already closed


class RoomManager:
    """In-memory signaling rooms: at most one interviewer and one candidate per interview.
    Lives in the backend process, so Uvicorn must run with a single worker."""

    def __init__(self) -> None:
        self._rooms: dict[int, dict[str, Connection]] = {}
        self._lock = asyncio.Lock()

    async def join(self, interview_id: int, conn: Connection, status: str, started_at: str | None) -> None:
        """Add the connection (replacing an older one of the same role), send it the room state
        and tell the other participant."""
        async with self._lock:
            room = self._rooms.setdefault(interview_id, {})
            old = room.get(conn.role)
            room[conn.role] = conn
            peer = room.get(other_role(conn.role))

        if old:
            logger.info("Interview %s: %s connection replaced by a new one", interview_id, conn.role)
            await old.close(CLOSE_REPLACED, "Replaced by a new connection")
        peers = [{"role": peer.role, "name": peer.name}] if peer else []
        await conn.send({"type": "room-state", "peers": peers, "status": status, "started_at": started_at})
        if peer:
            await peer.send({"type": "peer-joined", "role": conn.role, "name": conn.name})

    async def leave(self, interview_id: int, conn: Connection) -> None:
        """Remove the connection if it is still the current one and tell the other participant."""
        async with self._lock:
            room = self._rooms.get(interview_id)
            if not room or room.get(conn.role) is not conn:
                return  # replaced or room already closed
            del room[conn.role]
            peer = room.get(other_role(conn.role))
            if not room:
                del self._rooms[interview_id]
        if peer:
            await peer.send({"type": "peer-left", "role": conn.role})

    async def relay_signal(self, interview_id: int, from_role: str, data) -> None:
        """Forward a signal unchanged to the other participant of the same interview only."""
        peer = self._rooms.get(interview_id, {}).get(other_role(from_role))
        if peer:
            await peer.send({"type": "signal", "data": data})

    async def broadcast(self, interview_id: int, message: dict) -> None:
        conns = list(self._rooms.get(interview_id, {}).values())
        for conn in conns:
            await conn.send(message)
        if conns:
            logger.info("Interview %s: sent %s to the room", interview_id, message["type"])

    async def close_room(self, interview_id: int, reason: str) -> None:
        async with self._lock:
            room = self._rooms.pop(interview_id, {})
        for conn in room.values():
            await conn.close(1000, reason)
        if room:
            logger.info("Interview %s: room closed (%s)", interview_id, reason)


rooms = RoomManager()


async def end_room(interview_id: int, reason: str) -> None:
    """The interview is over (reason: completed / cancelled / no_show): tell both sides and close."""
    await rooms.broadcast(interview_id, {"type": "interview-ended", "reason": reason})
    await rooms.close_room(interview_id, f"Interview ended ({reason})")
    await audio.close_interview(interview_id, f"Interview ended ({reason})")


def push_from_thread(interview_id: int, push, *args) -> None:
    """Run a room update (e.g. end_room) from a sync endpoint in the threadpool.
    A failure is only logged; it never undoes the status change."""
    try:
        anyio.from_thread.run(push, interview_id, *args)
    except Exception:
        logger.exception("Interview %s: could not update the room", interview_id)
