"""Stream a recorded interview audio part through Deepgram in real time and print the final results.

Usage (from backend/, or inside the backend container):
    python -m app.scripts.transcribe_wav storage/interview_audio/<interview_id>/<role>_part<N>.wav
"""

import argparse
import asyncio
import logging
import re
import sys
import wave
from pathlib import Path

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import InterviewAudioPart
from app.services.audio import BYTES_PER_SECOND
from app.services.deepgram_stt import DeepgramTranscriber
from app.services.transcription import TranscriptEvent

CHUNK_BYTES = BYTES_PER_SECOND // 10  # 100 ms, like the browser
PART_NAME = re.compile(r"^(interviewer|candidate)_part(\d+)\.wav$")


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{seconds % 60:04.1f}"


def _start_offset(interview_id: int, role: str, part_no: int) -> float:
    with SessionLocal() as db:
        offset = db.scalar(
            select(InterviewAudioPart.start_offset_s).where(
                InterviewAudioPart.interview_id == interview_id,
                InterviewAudioPart.role == role,
                InterviewAudioPart.part_no == part_no,
            )
        )
    return offset or 0.0


async def _print_final(event: TranscriptEvent) -> None:
    if event.is_final:
        conf = f"{event.confidence:.2f}" if event.confidence is not None else "-"
        print(f"[{_clock(event.start_s)}-{_clock(event.end_s)}] {event.role}: {event.text} ({conf})", flush=True)


async def main(path: Path) -> None:
    match = PART_NAME.match(path.name)
    if not match or not path.parent.name.isdigit():
        sys.exit("Expected a path like storage/interview_audio/<interview_id>/<role>_part<N>.wav")
    interview_id, role, part_no = int(path.parent.name), match[1], int(match[2])
    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            sys.exit("Expected 16 kHz mono 16-bit audio")
        audio = wav.readframes(wav.getnframes())
    offset = await asyncio.to_thread(_start_offset, interview_id, role, part_no)
    print(f"Interview {interview_id}, {role} part {part_no}: {len(audio) / BYTES_PER_SECOND:.1f} s, starts at {_clock(offset)}")

    transcriber = DeepgramTranscriber()
    await transcriber.start(interview_id, role, _print_final)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    for pos in range(0, len(audio), CHUNK_BYTES):
        chunk = audio[pos : pos + CHUNK_BYTES]
        # wait until the chunk has "arrived", as in a live interview
        end = (pos + len(chunk)) / BYTES_PER_SECOND
        await asyncio.sleep(max(t0 + end - loop.time(), 0))
        await transcriber.feed(chunk, offset + end)
    await transcriber.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("websockets").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path, help="WAV part from storage/interview_audio")
    asyncio.run(main(parser.parse_args().path))
