import asyncio
import logging

from app.core.config import settings
from app.services.audio import BYTES_PER_SECOND

logger = logging.getLogger(__name__)

# ~60 s of 100 ms chunks; if the engine falls further behind, new chunks are dropped
MAX_QUEUE_CHUNKS = 600
STOP_TIMEOUT_SECONDS = 10


class Transcriber:
    """Speech-to-text engine for one speaker of one interview. Module 7 adds real engines
    (Google STT / faster-whisper); the audio gateway only uses this interface."""

    async def start(self, interview_id: int, role: str) -> None:
        self.interview_id = interview_id
        self.role = role

    async def feed(self, chunk: bytes, offset_s: float) -> None:
        """LINEAR16 16 kHz mono chunk; offset_s = seconds since the interview started_at."""

    async def stop(self) -> None:
        pass


class StubTranscriber(Transcriber):
    """No speech-to-text: only counts the audio it receives."""

    async def start(self, interview_id: int, role: str) -> None:
        await super().start(interview_id, role)
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

    async def start(self) -> None:
        await self.engine.start(self.interview_id, self.role)
        self._task = asyncio.create_task(self._consume())
        logger.info(
            "Interview %s: transcriber %s started for %s", self.interview_id, type(self.engine).__name__, self.role
        )

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
            "Interview %s: transcriber stopped for %s (%d chunks dropped)", self.interview_id, self.role, self._dropped
        )
