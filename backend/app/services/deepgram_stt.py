import asyncio
import json
import logging
import re
import time
from bisect import bisect_right
from collections import deque
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Interview
from app.services.audio import BYTES_PER_SECOND
from app.services.transcription import OnEvent, Transcriber, TranscriptEvent, TranscriptStatus, _ignore_event

logger = logging.getLogger(__name__)

DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"
CONNECT_TIMEOUT_SECONDS = 10
KEEPALIVE_SECONDS = 5  # Deepgram closes a stream after ~10 s without audio (e.g. muted)
CLOSE_WAIT_SECONDS = 3  # time for the last results after CloseStream
MAX_RECONNECT_SECONDS = 10  # backoff 1, 2, 4, 8, then every 10 s
MAX_BUFFER_SECONDS = 15  # audio kept while reconnecting; the oldest is dropped first
# Handshake errors that a retry cannot fix: invalid parameters, bad/missing key, no credit
PERMANENT_STATUS = {400: "invalid parameters", 401: "invalid API key", 402: "no credit left", 403: "access denied"}
GAP_SECONDS = 0.2  # a jump larger than this between audio and interview time starts a new anchor
MAX_KEYTERMS = 30
MAX_KEYTERM_WORDS = 3

_STOPWORDS = {
    "and", "or", "the", "a", "an", "of", "in", "on", "with", "for", "to", "at", "as", "is", "are",
    "be", "using", "use", "strong", "good", "solid", "knowledge", "experience", "understanding",
    "familiarity", "proficiency", "ability", "skills", "skill", "years", "year", "plus", "etc",
}  # fmt: skip
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#./-]*[A-Za-z0-9+#]|[A-Za-z]")


def _tech_words(text: str) -> list[str]:
    """Words of a long requirement that look like a technology: an inner capital, a digit or + # ."""
    words = []
    for i, token in enumerate(_TOKEN.findall(text)):
        if token.lower() in _STOPWORDS or not re.search(r"[A-Za-z]", token):
            continue
        capitalised = i > 0 and any(c.isupper() for c in token)
        symbols = any(c.isdigit() or c in "+#." for c in token)
        if capitalised or symbols:
            words.append(token)
    return words


def _permanent(exc: Exception) -> str | None:
    """Why a failed connect can never succeed (e.g. "HTTP 401 invalid API key"), or None."""
    if isinstance(exc, InvalidStatus):
        code = exc.response.status_code
        if code in PERMANENT_STATUS:
            return f"HTTP {code} {PERMANENT_STATUS[code]}"
    return None


def build_keyterms(skills: list[str], requirements: list[dict]) -> list[str]:
    """Up to MAX_KEYTERMS short terms: the candidate's skills, then the job's skill requirements."""
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        term = term.strip(" .,;:()")
        if term and len(term.split()) <= MAX_KEYTERM_WORDS and term.lower() not in seen:
            seen.add(term.lower())
            terms.append(term)

    for skill in skills:
        add(str(skill))
    for req in requirements:
        if req.get("category", "skill") != "skill":
            continue
        text = str(req.get("text", ""))
        if len(text.split()) <= MAX_KEYTERM_WORDS:
            add(text)
        else:
            for word in _tech_words(text):
                add(word)
    return terms[:MAX_KEYTERMS]


def load_keyterms(interview_id: int) -> list[str]:
    with SessionLocal() as db:
        interview = db.get(Interview, interview_id)
        if interview is None:
            return []
        candidate = interview.candidate
        skills = (candidate.profile or {}).get("skills") or []
        return build_keyterms(skills, candidate.job.requirements or [])


class TimeMap:
    """Maps Deepgram's audio clock (seconds of audio sent) to the interview clock.
    Muted pauses send no audio, so every gap starts a new anchor."""

    def __init__(self) -> None:
        self.audio_s: list[float] = []
        self.interview_s: list[float] = []

    def add_chunk(self, audio_s: float, interview_s: float) -> None:
        if self.audio_s:
            expected = self.interview_s[-1] + (audio_s - self.audio_s[-1])
            if interview_s - expected <= GAP_SECONDS:
                return
        self.audio_s.append(audio_s)
        self.interview_s.append(interview_s)

    def to_interview(self, audio_s: float) -> float:
        if not self.audio_s:
            return audio_s
        i = max(bisect_right(self.audio_s, audio_s) - 1, 0)
        return round(self.interview_s[i] + (audio_s - self.audio_s[i]), 3)


class DeepgramTranscriber(Transcriber):
    """One Deepgram live stream for one speaker of one interview. If the stream drops while
    the speaker is still connected, it reconnects with backoff and replays the buffered audio."""

    async def start(self, interview_id: int, role: str, on_event: OnEvent = _ignore_event) -> None:
        await super().start(interview_id, role, on_event)
        if not settings.deepgram_api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        try:
            self.keyterms = await asyncio.to_thread(load_keyterms, interview_id)
        except Exception:
            logger.exception("Interview %s: keyterms could not be loaded", interview_id)
            self.keyterms = []
        self.sent_bytes = 0  # all streams together
        self.results = 0
        # active / idle (closed while silent, reopens on the next audio) / reconnecting / unavailable
        self.state = "active"
        self._status = "active"  # last status sent through on_event
        self._quiet = False  # reopening after a silent close: not shown as reconnecting
        self._stopping = False
        self._buffer: deque[tuple[bytes, float]] = deque()  # (chunk, offset_s) fed while reconnecting
        self._buffer_bytes = 0
        self._trimmed_bytes = 0
        self._dropped_at = 0.0
        self._last_audio = time.monotonic()
        self._reconnector: asyncio.Task | None = None
        try:
            await self._connect()
        except Exception as exc:
            reason = _permanent(exc)
            if reason:
                raise RuntimeError(f"Deepgram refused the stream ({reason})") from None
            raise
        logger.info(
            "Interview %s: Deepgram stream opened for %s (%s, %d keyterms)",
            interview_id,
            role,
            settings.deepgram_model,
            len(self.keyterms),
        )

    async def _connect(self) -> None:
        """Open a new stream. Its audio clock starts at 0, so it gets its own TimeMap."""
        ws = await connect(
            f"{DEEPGRAM_URL}?{self._query(self.keyterms)}",
            additional_headers={"Authorization": f"Token {settings.deepgram_api_key}"},
            open_timeout=CONNECT_TIMEOUT_SECONDS,
        )
        self.ws: ClientConnection = ws
        self.time_map = TimeMap()
        self.stream_bytes = 0
        self._last_send = time.monotonic()
        self._receiver = asyncio.create_task(self._receive(ws, self.time_map))
        self._keepalive = asyncio.create_task(self._keep_alive(ws))

    def _query(self, keyterms: list[str]) -> str:
        params = [
            ("model", settings.deepgram_model),
            ("encoding", "linear16"),
            ("sample_rate", "16000"),
            ("channels", "1"),
            ("language", "en"),
            ("smart_format", "true"),
            ("punctuate", "true"),
            ("interim_results", "true"),
            ("endpointing", "300"),
            ("utterance_end_ms", "1000"),
        ]
        name = "keyterm" if settings.deepgram_model.startswith("nova-3") else "keywords"
        params += [(name, term) for term in keyterms]
        return urlencode(params)

    async def feed(self, chunk: bytes, offset_s: float) -> None:
        if self._stopping or self.state == "unavailable":
            return
        if self.state == "idle":  # audio resumed after a silent close: reopen quietly
            self._quiet = True
            await self._set_state("reconnecting")
            self._reconnector = asyncio.create_task(self._reconnect())
        if self.state == "reconnecting":
            self._buffer_add(chunk, offset_s)
            return
        ws = self.ws
        if not await self._send_audio(chunk, offset_s):
            self._buffer_add(chunk, offset_s)
            await self._lost(ws)

    async def _send_audio(self, chunk: bytes, offset_s: float) -> bool:
        # offset_s is when the chunk arrived, i.e. the end of the audio it holds
        audio_s = self.stream_bytes / BYTES_PER_SECOND
        self.time_map.add_chunk(audio_s, max(offset_s - len(chunk) / BYTES_PER_SECOND, 0.0))
        try:
            await self.ws.send(chunk)
        except ConnectionClosed:
            return False
        self.stream_bytes += len(chunk)
        self.sent_bytes += len(chunk)
        self._last_send = self._last_audio = time.monotonic()
        return True

    def _buffer_add(self, chunk: bytes, offset_s: float) -> None:
        self._buffer.append((chunk, offset_s))
        self._buffer_bytes += len(chunk)
        while self._buffer_bytes > MAX_BUFFER_SECONDS * BYTES_PER_SECOND:
            old, _ = self._buffer.popleft()
            self._buffer_bytes -= len(old)
            self._trimmed_bytes += len(old)

    async def _emit(self, event: TranscriptEvent | TranscriptStatus) -> None:
        try:
            await self.on_event(event)
        except Exception:
            logger.exception("Interview %s: transcript event handler failed", self.interview_id)

    async def _set_state(self, state: str) -> None:
        """Change the state; send a TranscriptStatus when what the interviewer should see changes.
        A silent close (idle) and a quiet reopen still count as active."""
        self.state = state
        status = "active" if state == "idle" or (state == "reconnecting" and self._quiet) else state
        if status != self._status:
            self._status = status
            await self._emit(TranscriptStatus(self.interview_id, self.role, status))

    async def _lost(self, ws: ClientConnection) -> None:
        """The current stream dropped without stop(): start reconnecting (once per drop).
        A drop during silence (muted) only reconnects when audio resumes."""
        if self._stopping or ws is not self.ws or self.state != "active":
            return
        self._dropped_at = time.monotonic()
        if self._dropped_at - self._last_audio >= KEEPALIVE_SECONDS:
            await self._set_state("idle")
            logger.debug(
                "Interview %s: Deepgram stream for %s closed while silent (code %s)",
                self.interview_id,
                self.role,
                ws.close_code,
            )
            return
        logger.warning(
            "Interview %s: Deepgram stream for %s dropped (code %s, reason %r), reconnecting",
            self.interview_id,
            self.role,
            ws.close_code,
            ws.close_reason or "",
        )
        self._quiet = False
        await self._set_state("reconnecting")
        self._reconnector = asyncio.create_task(self._reconnect())

    async def _give_up(self, reason: str) -> None:
        await self._set_state("unavailable")
        self._buffer.clear()
        self._buffer_bytes = 0
        logger.warning(
            "Interview %s: Deepgram refused the stream for %s (%s); transcription is off for %s "
            "for the rest of the session",
            self.interview_id,
            self.role,
            reason,
            self.role,
        )

    async def _reconnect(self) -> None:
        """After a silent close (quiet) the first try is immediate and logged only at debug."""
        quiet = self._quiet
        attempt = 0
        while not self._stopping:
            if not (quiet and attempt == 0):
                await asyncio.sleep(min(2**attempt, MAX_RECONNECT_SECONDS))  # 1, 2, 4, 8, 10, 10 ...
            attempt += 1
            try:
                await self._connect()
            except Exception as exc:
                reason = _permanent(exc)
                if reason:
                    await self._give_up(reason)
                    return
                if self._quiet:  # the quiet reopen failed: now show it as reconnecting
                    self._quiet = False
                    await self._set_state("reconnecting")
                logger.info(
                    "Interview %s: Deepgram reconnect %d for %s failed (%s)",
                    self.interview_id,
                    attempt,
                    self.role,
                    type(exc).__name__,
                )
                continue
            # Buffered audio goes first; feed() keeps buffering until the buffer is empty
            replayed = 0
            while self._buffer:
                chunk, offset_s = self._buffer.popleft()
                self._buffer_bytes -= len(chunk)
                if not await self._send_audio(chunk, offset_s):
                    self._buffer.appendleft((chunk, offset_s))
                    self._buffer_bytes += len(chunk)
                    break
                replayed += len(chunk)
            if self._buffer:
                continue  # the new stream dropped during the replay
            await self._set_state("active")
            trimmed = self._trimmed_bytes / BYTES_PER_SECOND
            self._trimmed_bytes = 0
            logger.log(
                logging.DEBUG if quiet and attempt == 1 else logging.INFO,
                "Interview %s: Deepgram stream for %s recovered after %.1f s (%d tries, %.1f s buffered replayed%s)",
                self.interview_id,
                self.role,
                time.monotonic() - self._dropped_at,
                attempt,
                replayed / BYTES_PER_SECOND,
                f", {trimmed:.1f} s over the buffer limit lost" if trimmed else "",
            )
            return

    async def simulate_drop(self) -> None:
        """Testing aid (transcribe_wav --simulate-drop): close the stream as if it had dropped."""
        if self.state == "active":
            await self.ws.close(4000, "simulated drop")

    async def _keep_alive(self, ws: ClientConnection) -> None:
        while not self._stopping and ws is self.ws:
            await asyncio.sleep(1)
            if self.state == "active" and time.monotonic() - self._last_send >= KEEPALIVE_SECONDS:
                try:
                    await ws.send(json.dumps({"type": "KeepAlive"}))
                except ConnectionClosed:
                    await self._lost(ws)
                    return
                self._last_send = time.monotonic()

    async def _receive(self, ws: ClientConnection, time_map: TimeMap) -> None:
        pending: TranscriptEvent | None = None  # last interim of this stream not yet followed by a final
        try:
            async for message in ws:
                if not isinstance(message, str):
                    continue
                data = json.loads(message)
                if data.get("type") != "Results":
                    continue
                if data.get("is_final"):
                    pending = None
                event = self._event(data, time_map)
                if event:
                    if not event.is_final:
                        pending = event
                    await self._emit(event)
        except ConnectionClosed:
            pass
        except Exception:
            logger.exception("Interview %s: Deepgram results for %s failed", self.interview_id, self.role)
        finally:
            if pending:  # the stream ended mid-sentence: keep the words as an incomplete final
                pending.is_final = True
                pending.incomplete = True
                self.results += 1
                await self._emit(pending)
        await self._lost(ws)

    def _event(self, data: dict, time_map: TimeMap) -> TranscriptEvent | None:
        alternatives = (data.get("channel") or {}).get("alternatives") or []
        if not alternatives or not alternatives[0].get("transcript", "").strip():
            return None
        best = alternatives[0]
        start = float(data.get("start", 0.0))
        end = start + float(data.get("duration", 0.0))
        self.results += 1
        return TranscriptEvent(
            interview_id=self.interview_id,
            role=self.role,
            text=best["transcript"].strip(),
            is_final=bool(data.get("is_final")),
            start_s=time_map.to_interview(start),
            end_s=time_map.to_interview(end),
            confidence=best.get("confidence"),
        )

    async def stop(self) -> None:
        self._stopping = True
        if self._reconnector:
            self._reconnector.cancel()
        self._keepalive.cancel()
        if self.state == "active":
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
            except ConnectionClosed:
                pass
            try:
                await asyncio.wait_for(asyncio.shield(self._receiver), CLOSE_WAIT_SECONDS)
            except asyncio.TimeoutError:
                logger.warning(
                    "Interview %s: Deepgram gave no final results for %s in time", self.interview_id, self.role
                )
        self._receiver.cancel()
        await asyncio.gather(self._receiver, return_exceptions=True)  # sends a pending interim as incomplete
        await self.ws.close()
        unsent = self._buffer_bytes / BYTES_PER_SECOND
        logger.info(
            "Interview %s: Deepgram stream closed for %s (%.1f s audio sent, %d results%s)",
            self.interview_id,
            self.role,
            self.sent_bytes / BYTES_PER_SECOND,
            self.results,
            f", {unsent:.1f} s buffered audio not sent" if unsent else "",
        )
