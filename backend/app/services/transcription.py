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


OnEvent = Callable[[TranscriptEvent], Awaitable[None]]


async def _ignore_event(event: TranscriptEvent) -> None:
    pass


class Transcriber:
    """Speech-to-text engine for one speaker of one interview; the audio gateway only uses
    this interface. Results go to on_event."""

    async def start(self, interview_id: int, role: str, on_event: OnEvent = _ignore_event) -> None:
        """Raise if the engine cannot start; the stream then falls back to the stub."""
        self.interview_id = interview_id
        self.role = role
        self.on_event = on_event

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
        try:
            await self.engine.start(self.interview_id, self.role, self._on_event)
        except Exception as exc:
            logger.warning(
                "Interview %s: %s transcriber could not start for %s (%s), using the stub",
                self.interview_id,
                type(self.engine).__name__,
                self.role,
                type(exc).__name__,
            )
            self.engine = StubTranscriber()
            await self.engine.start(self.interview_id, self.role, self._on_event)
        self._task = asyncio.create_task(self._consume())
        logger.info(
            "Interview %s: transcriber %s started for %s", self.interview_id, type(self.engine).__name__, self.role
        )

    async def _on_event(self, event: TranscriptEvent) -> None:
        """For now only logs; 7.2 stores the events and 7.3 sends them to the interviewer.
        The text itself is logged only with TRANSCRIPT_LOG_TEXT=true."""
        if not event.is_final:
            self._interim += 1
            return
        self._finals += 1
        conf = f"{event.confidence:.2f}" if event.confidence is not None else "-"
        if settings.transcript_log_text:
            logger.info(
                "Interview %s: %s final %.1f-%.1f s (conf %s): %s",
                self.interview_id, self.role, event.start_s, event.end_s, conf, event.text,
            )  # fmt: skip
        else:
            logger.info(
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
            try:
                await self.engine.feed(*item)
            except Exception:
                logger.exception("Interview %s: %s transcriber feed failed", self.interview_id, self.role)

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
        logger.info(
            "Interview %s: transcriber stopped for %s (%d final, %d interim results, %d chunks dropped)",
            self.interview_id,
            self.role,
            self._finals,
            self._interim,
            self._dropped,
        )
