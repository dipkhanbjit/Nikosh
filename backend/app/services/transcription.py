import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.config import settings
from app.services.audio import BYTES_PER_SECOND

logger = logging.getLogger(__name__)

# ~60 s of 100 ms chunks; if the engine falls further behind, new chunks are dropped
MAX_QUEUE_CHUNKS = 600
STOP_TIMEOUT_SECONDS = 10


@dataclass
class TranscriptEvent:
    """One recognised piece of speech. start_s / end_s are seconds since the interview started_at."""

    interview_id: int
    role: str
    text: str
    is_final: bool
    start_s: float
    end_s: float
    confidence: float | None = None
    incomplete: bool = False  # the last interim text of a stream that dropped, kept as a final
    speech_final: bool = False  # Deepgram endpointing: a short pause (~300 ms) after this final
    utterance_end: bool = False  # no text: the speaker was silent ~2 s after start_s (Deepgram UtteranceEnd)


@dataclass
class TranscriptStatus:
    """Transcription state of one speaker, sent when it changes: active / reconnecting / unavailable."""

    interview_id: int
    role: str
    state: str


OnEvent = Callable[[TranscriptEvent | TranscriptStatus], Awaitable[None]]


async def _ignore_event(event: TranscriptEvent | TranscriptStatus) -> None:
    pass


class Transcriber:
    """Speech-to-text engine for one speaker of one interview; the audio gateway only uses
    this interface. Results go to on_event."""

    async def start(self, interview_id: int, role: str, on_event: OnEvent = _ignore_event) -> None:
        """Raise if the engine cannot start; the stream then falls back to the stub."""
        self.interview_id = interview_id
        self.role = role
        self.on_event = on_event
        self.state = "active"  # "unavailable" = failed for good; the stream then switches to the stub

    async def feed(self, chunk: bytes, offset_s: float) -> None:
        """LINEAR16 16 kHz mono chunk; offset_s = seconds since the interview started_at."""

    async def stop(self) -> None:
        pass


class StubTranscriber(Transcriber):
    """No speech-to-text: only counts the audio it receives."""

    async def start(self, interview_id: int, role: str, on_event: OnEvent = _ignore_event) -> None:
        await super().start(interview_id, role, on_event)
        self.bytes = 0
        self.last_offset_s = 0.0

    async def feed(self, chunk: bytes, offset_s: float) -> None:
        self.bytes += len(chunk)
        self.last_offset_s = offset_s

    async def stop(self) -> None:
        logger.info(
            "Interview %s: stub transcriber got %.1f s of %s audio (%d bytes, last offset %.1f s)",
            self.interview_id,
            self.bytes / BYTES_PER_SECOND,
            self.role,
            self.bytes,
            self.last_offset_s,
        )


ENGINES: dict[str, type[Transcriber]] = {"stub": StubTranscriber}


def create_transcriber() -> Transcriber:
    if settings.transcriber == "deepgram":
        from app.services.deepgram_stt import DeepgramTranscriber  # here to avoid a circular import

        return DeepgramTranscriber()
    engine = ENGINES.get(settings.transcriber)
    if engine is None:
        logger.warning("Unknown TRANSCRIBER %r, using the stub", settings.transcriber)
        engine = StubTranscriber
    return engine()


class TranscriptionStream:
    """Runs a transcriber in its own task so feeding never blocks the audio socket."""

    def __init__(self, interview_id: int, role: str) -> None:
        self.interview_id = interview_id
        self.role = role
        self.engine = create_transcriber()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_CHUNKS)
        self._task: asyncio.Task | None = None
        self._dropped = 0
        self._interim = 0
        self._finals = 0

    async def start(self) -> None:
        from app.services.transcript_turns import turns  # here to avoid a circular import

        # Kept for the whole stream, so the last results still arrive after the room ended
        self.turns = await turns.get(self.interview_id)
        self.turns.streams += 1
        try:
            await self.engine.start(self.interview_id, self.role, self._on_event)
        except Exception as exc:
            logger.warning(
                "Interview %s: %s transcriber could not start for %s (%s: %s), using the stub",
                self.interview_id,
                type(self.engine).__name__,
                self.role,
                type(exc).__name__,
                exc,
            )
            self.engine = StubTranscriber()
            await self.engine.start(self.interview_id, self.role, self._on_event)
            await self._on_event(TranscriptStatus(self.interview_id, self.role, "unavailable"))
        self._task = asyncio.create_task(self._consume())
        logger.info(
            "Interview %s: transcriber %s started for %s", self.interview_id, type(self.engine).__name__, self.role
        )

    async def _on_event(self, event: TranscriptEvent | TranscriptStatus) -> None:
        """Results go to the interview's TurnBuilder; 7.3 sends the status to the interviewer.
        The text itself is logged only with TRANSCRIPT_LOG_TEXT=true."""
        if isinstance(event, TranscriptStatus):
            logger.info("Interview %s: %s transcription is %s", self.interview_id, self.role, event.state)
            return
        try:
            await self.turns.add(event)
        except Exception:
            logger.exception("Interview %s: transcript turn update failed", self.interview_id)
        if event.utterance_end:
            logger.debug("Interview %s: %s utterance end at %.1f s", self.interview_id, self.role, event.start_s)
            return
        if not event.is_final:
            self._interim += 1
            return
        self._finals += 1
        conf = f"{event.confidence:.2f}" if event.confidence is not None else "-"
        if event.incomplete:
            conf += ", incomplete"
        if settings.transcript_log_text:
            logger.debug(
                "Interview %s: %s final %.1f-%.1f s (conf %s): %s",
                self.interview_id, self.role, event.start_s, event.end_s, conf, event.text,
            )  # fmt: skip
        else:
            logger.debug(
                "Interview %s: %s final %.1f-%.1f s (%d chars, conf %s)",
                self.interview_id, self.role, event.start_s, event.end_s, len(event.text), conf,
            )  # fmt: skip

    def feed(self, chunk: bytes, offset_s: float) -> None:
        try:
            self._queue.put_nowait((chunk, offset_s))
        except asyncio.QueueFull:
            if self._dropped == 0:
                logger.warning("Interview %s: %s transcriber is behind, dropping audio", self.interview_id, self.role)
            self._dropped += 1

    async def _consume(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            if self.engine.state == "unavailable":
                await self._use_stub()
            try:
                await self.engine.feed(*item)
            except Exception:
                logger.exception("Interview %s: %s transcriber feed failed", self.interview_id, self.role)

    async def _use_stub(self) -> None:
        """The engine failed for good: the stub counts the audio for the rest of the session."""
        try:
            await self.engine.stop()
        except Exception:
            logger.exception("Interview %s: %s transcriber stop failed", self.interview_id, self.role)
        self.engine = StubTranscriber()
        await self.engine.start(self.interview_id, self.role, self._on_event)
        logger.info("Interview %s: %s transcriber switched to the stub", self.interview_id, self.role)

    async def stop(self) -> None:
        if self._task:
            try:
                self._queue.put_nowait(None)  # finish what is queued, then stop
            except asyncio.QueueFull:
                self._task.cancel()
            try:
                await asyncio.wait_for(self._task, STOP_TIMEOUT_SECONDS)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning("Interview %s: %s transcriber did not finish in time", self.interview_id, self.role)
        try:
            await self.engine.stop()
        except Exception:
            logger.exception("Interview %s: %s transcriber stop failed", self.interview_id, self.role)
        try:
            await self.turns.speaker_stopped(self.role)
        except Exception:
            logger.exception("Interview %s: %s transcript turn could not be closed", self.interview_id, self.role)
        self.turns.streams -= 1
        logger.info(
            "Interview %s: transcriber stopped for %s (%d final, %d interim results, %d chunks dropped)",
            self.interview_id,
            self.role,
            self._finals,
            self._interim,
            self._dropped,
        )
