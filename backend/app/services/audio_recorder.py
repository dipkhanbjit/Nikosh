import asyncio
import logging
import shutil
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import InterviewAudioPart
from app.services.audio import BYTES_PER_SECOND

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
HEADER_SIZE = 44
HEADER_UPDATE_SECONDS = 1.0  # sizes in the header are kept current, so a crash leaves a readable file
GAP_THRESHOLD_BYTES = int(0.2 * BYTES_PER_SECOND)  # pause longer than ~200 ms → filled with silence
MAX_GAP_BYTES = 10 * 60 * BYTES_PER_SECOND  # at most 10 minutes of silence per gap
SILENCE_BLOCK = bytes(BYTES_PER_SECOND)


def audio_dir(interview_id: int) -> Path:
    return Path(settings.interview_audio_dir) / str(interview_id)


def wav_header(data_size: int) -> bytes:
    """44-byte PCM WAV header: 16 kHz, mono, 16-bit."""
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, 1, SAMPLE_RATE, BYTES_PER_SECOND, 2, 16,
        b"data", data_size,
    )  # fmt: skip


def _create_part(interview_id: int, role: str, start_offset_s: float) -> tuple[int, Path]:
    """Next part number for this speaker, the row and an empty WAV file."""
    folder = audio_dir(interview_id)
    folder.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        last = db.scalar(
            select(func.max(InterviewAudioPart.part_no)).where(
                InterviewAudioPart.interview_id == interview_id, InterviewAudioPart.role == role
            )
        )
        part_no = (last or 0) + 1
        path = folder / f"{role}_part{part_no}.wav"
        path.write_bytes(wav_header(0))
        part = InterviewAudioPart(
            interview_id=interview_id,
            role=role,
            part_no=part_no,
            file_path=str(path),
            start_offset_s=round(start_offset_s, 3),
        )
        db.add(part)
        db.commit()
        return part.id, path


def _finish_part(part_id: int, data_size: int) -> None:
    with SessionLocal() as db:
        part = db.get(InterviewAudioPart, part_id)
        if part:  # may be gone if the candidate/job was deleted meanwhile
            part.duration_s = round(data_size / BYTES_PER_SECOND, 3)
            part.size_bytes = HEADER_SIZE + data_size
            db.commit()


def delete_interview_audio(interview_ids: list[int]) -> None:
    """Remove the recorded audio of these interviews (the rows go with the DB cascade)."""
    for interview_id in interview_ids:
        folder = audio_dir(interview_id)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
            logger.info("Interview %s: audio files deleted", interview_id)


def part_sizes(part: InterviewAudioPart) -> tuple[float | None, int | None]:
    """Duration and size of a part; read from the file if it was never closed (backend stopped)."""
    if part.duration_s is not None:
        return part.duration_s, part.size_bytes
    path = Path(part.file_path)
    if not path.exists():
        return None, None
    size = path.stat().st_size
    return round(max(size - HEADER_SIZE, 0) / BYTES_PER_SECOND, 3), size


class AudioRecorder:
    """Writes one audio connection of a speaker to <role>_part<N>.wav.
    Pauses (e.g. muted) are filled with silence, so position X in the file is
    start_offset_s + X in the interview. Disk work runs in a background task."""

    def __init__(self, interview_id: int, role: str) -> None:
        self.interview_id = interview_id
        self.role = role
        self.part_id: int | None = None
        self.start_offset_s = 0.0
        self._t0 = 0.0
        self._queued = 0  # bytes queued so far (audio + silence)
        self._data_size = 0  # bytes written so far
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._file = None
        self._failed = False

    async def open(self, started_at: datetime | None) -> None:
        now = datetime.now(timezone.utc)
        self.start_offset_s = max((now - started_at).total_seconds(), 0.0) if started_at else 0.0
        self._t0 = time.monotonic()
        self.part_id, path = await asyncio.to_thread(_create_part, self.interview_id, self.role, self.start_offset_s)
        self._file = await asyncio.to_thread(open, path, "r+b")
        self._file.seek(0, 2)
        self._task = asyncio.create_task(self._run())
        logger.info(
            "Interview %s: %s audio part %s opened (%s, offset %.1f s)",
            self.interview_id,
            self.role,
            self.part_id,
            path.name,
            self.start_offset_s,
        )

    def offset_now(self) -> float:
        """Seconds since the interview started_at, by the recorder's clock."""
        return self.start_offset_s + (time.monotonic() - self._t0)

    def write(self, chunk: bytes) -> None:
        """Queue a chunk (never blocks). A chunk covers the ~100 ms before it arrived."""
        if self._failed or self._task is None:
            return
        expected_start = int((time.monotonic() - self._t0) * BYTES_PER_SECOND) - len(chunk)
        gap = expected_start - self._queued
        if gap > GAP_THRESHOLD_BYTES:
            gap = min(gap, MAX_GAP_BYTES) & ~1  # whole 16-bit samples
            self._queue.put_nowait(gap)
            self._queued += gap
        self._queue.put_nowait(chunk)
        self._queued += len(chunk)

    async def _run(self) -> None:
        last_header = time.monotonic()
        while True:
            try:
                items = [await asyncio.wait_for(self._queue.get(), HEADER_UPDATE_SECONDS)]
            except asyncio.TimeoutError:
                items = []  # quiet (e.g. muted): still bring the header up to date
            while not self._queue.empty():
                items.append(self._queue.get_nowait())
            done = bool(items) and items[-1] is None
            update_header = done or time.monotonic() - last_header >= HEADER_UPDATE_SECONDS
            try:
                await asyncio.to_thread(self._write_items, [i for i in items if i is not None], update_header)
            except OSError:
                logger.exception("Interview %s: %s audio part %s write failed", self.interview_id, self.role, self.part_id)
                self._failed = True
                return
            if update_header:
                last_header = time.monotonic()
            if done:
                return

    def _write_items(self, items: list, update_header: bool) -> None:
        for item in items:
            if isinstance(item, int):  # silence
                remaining = item
                while remaining > 0:
                    block = SILENCE_BLOCK[: min(remaining, len(SILENCE_BLOCK))]
                    self._file.write(block)
                    remaining -= len(block)
                self._data_size += item
            else:
                self._file.write(item)
                self._data_size += len(item)
        if update_header:
            self._file.seek(0)
            self._file.write(wav_header(self._data_size))
            self._file.seek(0, 2)
            self._file.flush()

    async def close(self) -> None:
        if self._task is None:
            return
        self._queue.put_nowait(None)
        await self._task
        await asyncio.to_thread(self._file.close)
        await asyncio.to_thread(_finish_part, self.part_id, self._data_size)
        logger.info(
            "Interview %s: %s audio part %s closed (%.1f s, %d bytes)",
            self.interview_id,
            self.role,
            self.part_id,
            self._data_size / BYTES_PER_SECOND,
            HEADER_SIZE + self._data_size,
        )
