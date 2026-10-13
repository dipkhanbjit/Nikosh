import asyncio
import json
import logging

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.core.security import decode_access_token
from app.models import Interview, User
from app.services.interview_chat import add_text, ensure_chat_open, to_dict
from app.services.audio import BYTES_PER_SECOND, AudioConnection, audio
from app.services.interviews import check_join_link, room_open
from app.services.rooms import Connection, rooms

logger = logging.getLogger(__name__)

# Signaling channel for the interview room (WebRTC offer/answer/ICE go inside "signal")
router = APIRouter(prefix="/ws", tags=["ws"])

PING_SECONDS = 20
IDLE_TIMEOUT_SECONDS = 45  # no message (not even a pong) for this long = dead connection

# Close codes: 4401 not logged in, 4403 wrong role / not your interview, 4404 not found,
# 4409 room not open, 4410 link expired, 4001 timed out (client may reconnect)
CLOSE_TIMEOUT = 4001
# Audio sockets also: 4409 interview not in progress, 4413 audio chunk too large
CLOSE_TOO_LARGE = 4413
MAX_AUDIO_CHUNK = 64 * 1024  # ~2 s of LINEAR16 at 16 kHz; the browser sends ~100 ms chunks


class Refused(Exception):
    def __init__(self, code: int, reason: str):
        self.code = code
        self.reason = reason
        super().__init__(reason)


def _get_user(db, access_token: str | None, role: str) -> User:
    if not access_token:
        raise Refused(4401, "Not authenticated")
    try:
        payload = decode_access_token(access_token)
    except jwt.PyJWTError:
        raise Refused(4401, "Invalid or expired token") from None
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise Refused(4401, "User not found or inactive")
    if user.role != role:
        raise Refused(4403, "Access denied for this role")
    return user


def _room_info(interview: Interview) -> dict:
    return {
        "interview_id": interview.id,
        "status": interview.status,
        "started_at": interview.started_at.isoformat() if interview.started_at else None,
    }


def _authorize_interviewer(access_token: str | None, interview_id: int) -> dict:
    with SessionLocal() as db:
        user = _get_user(db, access_token, "interviewer")
        interview = db.get(Interview, interview_id)
        if not interview:
            raise Refused(4404, "Interview not found")
        if not room_open(interview):
            raise Refused(4409, "The interview room is not open")
        return {**_room_info(interview), "name": user.full_name}


def _authorize_candidate(access_token: str | None, token: str) -> dict:
    """Same checks as GET /join/{token}/room."""
    with SessionLocal() as db:
        user = _get_user(db, access_token, "candidate")
        try:
            interview, status = check_join_link(db, token, user)
        except AppException as exc:
            raise Refused(4000 + exc.status_code, exc.message) from None
        if status != "ready":
            raise Refused(4409, "The interview room is not open yet")
        return {**_room_info(interview), "name": interview.candidate.full_name or user.full_name}


def _save_chat(interview_id: int, role: str, name: str, text) -> dict | None:
    """Save a chat text (own DB session); None if empty or the chat is closed."""
    if not isinstance(text, str):
        return None
    with SessionLocal() as db:
        interview = db.get(Interview, interview_id)
        if not interview:
            return None
        try:
            ensure_chat_open(interview)
        except AppException:
            logger.warning("Interview %s: %s chat message refused (chat closed)", interview_id, role)
            return None
        message = add_text(db, interview, role, name, text)
        return to_dict(message) if message else None


async def _ping(conn: Connection) -> None:
    while True:
        await asyncio.sleep(PING_SECONDS)
        await conn.send({"type": "ping"})


async def _run(ws: WebSocket, info: dict, role: str) -> None:
    interview_id = info["interview_id"]
    conn = Connection(ws, role, info["name"])
    await rooms.join(interview_id, conn, info["status"], info["started_at"])
    logger.info("Interview %s: %s connected to the room", interview_id, role)
    pinger = asyncio.create_task(_ping(conn))
    try:
        while True:
            text = await asyncio.wait_for(ws.receive_text(), IDLE_TIMEOUT_SECONDS)
            try:
                message = json.loads(text)
            except ValueError:
                continue  # ignore anything that is not JSON
            if not isinstance(message, dict):
                continue
            if message.get("type") == "signal":
                await rooms.relay_signal(interview_id, role, message.get("data"))
            elif message.get("type") == "chat":
                saved = await asyncio.to_thread(_save_chat, interview_id, role, info["name"], message.get("text"))
                if saved:
                    await rooms.broadcast(interview_id, {"type": "chat", "message": saved})
            # "pong" and unknown types only keep the connection alive
    except asyncio.TimeoutError:
        logger.warning("Interview %s: %s connection timed out", interview_id, role)
        await conn.close(CLOSE_TIMEOUT, "Connection timed out")
    except (WebSocketDisconnect, RuntimeError):
        pass  # closed by the client, or by us (replaced / interview ended)
    finally:
        pinger.cancel()
        await rooms.leave(interview_id, conn)
        logger.info("Interview %s: %s disconnected from the room", interview_id, role)


async def _refuse(ws: WebSocket, refused: Refused) -> None:
    # Accept first so the browser receives the close code and reason
    await ws.accept()
    await ws.close(code=refused.code, reason=refused.reason)


@router.websocket("/interviews/{interview_id}")
async def interviewer_socket(ws: WebSocket, interview_id: int):
    try:
        info = await asyncio.to_thread(_authorize_interviewer, ws.cookies.get("access_token"), interview_id)
    except Refused as refused:
        logger.warning("Interview %s: interviewer socket refused (%s %s)", interview_id, refused.code, refused.reason)
        await _refuse(ws, refused)
        return
    await ws.accept()
    await _run(ws, info, "interviewer")


@router.websocket("/join/{token}")
async def candidate_socket(ws: WebSocket, token: str):
    short = token[:8]  # never log the full token
    try:
        info = await asyncio.to_thread(_authorize_candidate, ws.cookies.get("access_token"), token)
    except Refused as refused:
        logger.warning("Candidate socket for link %s... refused (%s %s)", short, refused.code, refused.reason)
        await _refuse(ws, refused)
        return
    await ws.accept()
    await _run(ws, info, "candidate")


# --- Audio capture (6.4.1): each browser sends only its own microphone as binary
# LINEAR16 chunks (16 kHz mono). The speaker role comes from the login, never from the client.
# Text frames (the client's ping while muted) only keep the connection alive.


def _require_in_progress(info: dict) -> dict:
    if info["status"] != "in_progress":
        raise Refused(4409, "The interview is not in progress")
    return info


async def _run_audio(ws: WebSocket, interview_id: int, role: str) -> None:
    conn = AudioConnection(ws, role)
    await audio.join(interview_id, conn)
    logger.info("Interview %s: %s audio connected", interview_id, role)
    try:
        while True:
            message = await asyncio.wait_for(ws.receive(), IDLE_TIMEOUT_SECONDS)
            if message["type"] == "websocket.disconnect":
                break
            chunk = message.get("bytes")
            if not chunk:
                continue  # ping (text)
            if len(chunk) > MAX_AUDIO_CHUNK:
                logger.warning("Interview %s: %s audio chunk too large (%d bytes)", interview_id, role, len(chunk))
                await conn.close(CLOSE_TOO_LARGE, "Audio chunk too large")
                break
            audio.add_chunk(interview_id, conn, len(chunk))
    except asyncio.TimeoutError:
        logger.warning("Interview %s: %s audio connection timed out", interview_id, role)
        await conn.close(CLOSE_TIMEOUT, "Connection timed out")
    except (WebSocketDisconnect, RuntimeError):
        pass  # closed by the client, or by us (replaced / interview ended)
    finally:
        await audio.leave(interview_id, conn)
        total = audio.total(interview_id, role)
        logger.info(
            "Interview %s: %s audio disconnected (%.1f s this connection, %.1f s total)",
            interview_id,
            role,
            conn.bytes_received / BYTES_PER_SECOND,
            total.seconds,
        )


@router.websocket("/audio/interviews/{interview_id}")
async def interviewer_audio_socket(ws: WebSocket, interview_id: int):
    try:
        info = await asyncio.to_thread(_authorize_interviewer, ws.cookies.get("access_token"), interview_id)
        _require_in_progress(info)
    except Refused as refused:
        logger.warning("Interview %s: interviewer audio refused (%s %s)", interview_id, refused.code, refused.reason)
        await _refuse(ws, refused)
        return
    await ws.accept()
    await _run_audio(ws, interview_id, "interviewer")


@router.websocket("/audio/join/{token}")
async def candidate_audio_socket(ws: WebSocket, token: str):
    short = token[:8]  # never log the full token
    try:
        info = await asyncio.to_thread(_authorize_candidate, ws.cookies.get("access_token"), token)
        _require_in_progress(info)
    except Refused as refused:
        logger.warning("Candidate audio for link %s... refused (%s %s)", short, refused.code, refused.reason)
        await _refuse(ws, refused)
        return
    await ws.accept()
    await _run_audio(ws, info["interview_id"], "candidate")
