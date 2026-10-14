"""Stream all recorded audio parts of an interview (both speakers) through Deepgram in real time,
aligned by their start offsets, and print the transcript turns.

Usage (from backend/, or inside the backend container):
    python -m app.scripts.transcribe_interview <interview_id>
"""

import argparse
import asyncio
import logging
import sys
import wave

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import InterviewAudioPart
from app.services.audio import BYTES_PER_SECOND
from app.services.deepgram_stt import DeepgramTranscriber
from app.services.transcript_turns import Turn, TurnBuilder
from app.services.transcription import TranscriptEvent, TranscriptStatus

CHUNK_BYTES = BYTES_PER_SECOND // 10  # 100 ms, like the browser


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{seconds % 60:04.1f}"


def _line(turn: Turn) -> str:
    flag = " (incomplete)" if turn.incomplete else ""
    return f"[{_clock(turn.start_s)}-{_clock(turn.end_s)}] {turn.role.capitalize()}: {turn.text}{flag}"


def _load_parts(interview_id: int) -> list[tuple[str, int, str, float]]:
    with SessionLocal() as db:
        rows = db.execute(
            select(
                InterviewAudioPart.role,
                InterviewAudioPart.part_no,
                InterviewAudioPart.file_path,
                InterviewAudioPart.start_offset_s,
            )
            .where(InterviewAudioPart.interview_id == interview_id)
            .order_by(InterviewAudioPart.start_offset_s)
        ).all()
    return [tuple(row) for row in rows]


def _read_wav(path: str) -> bytes | None:
    try:
        with wave.open(path, "rb") as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
                print(f"-- skipped {path}: not 16 kHz mono 16-bit")
                return None
            return wav.readframes(wav.getnframes())
    except (OSError, wave.Error) as exc:
        print(f"-- skipped {path}: {exc}")
        return None


async def _print_closed(turn: Turn) -> None:
    print(f"closed #{turn.id} {_line(turn)}", flush=True)


async def _ignore(turn: Turn) -> None:
    pass


async def _speaker(builder: TurnBuilder, role: str, parts: list, t0: float, base: float) -> None:
    """Stream one speaker's parts in order; each part gets its own Deepgram stream, like a reconnect."""
    loop = asyncio.get_running_loop()

    async def on_event(event: TranscriptEvent | TranscriptStatus) -> None:
        if isinstance(event, TranscriptStatus):
            print(f"-- {role} transcription {event.state}", flush=True)
        else:
            await builder.add(event)

    for _, part_no, path, offset in parts:
        audio = await asyncio.to_thread(_read_wav, path)
        if not audio:
            continue
        await asyncio.sleep(max(t0 + offset - base - loop.time(), 0))
        print(f"-- {role} part {part_no} starts at {_clock(offset)} ({len(audio) / BYTES_PER_SECOND:.1f} s)", flush=True)
        transcriber = DeepgramTranscriber()
        await transcriber.start(builder.interview_id, role, on_event)
        for pos in range(0, len(audio), CHUNK_BYTES):
            chunk = audio[pos : pos + CHUNK_BYTES]
            end = offset + (pos + len(chunk)) / BYTES_PER_SECOND
            await asyncio.sleep(max(t0 + end - base - loop.time(), 0))  # as in a live interview
            await transcriber.feed(chunk, end)
        await transcriber.stop()
        await builder.speaker_stopped(role)


async def main(interview_id: int) -> None:
    parts = await asyncio.to_thread(_load_parts, interview_id)
    if not parts:
        sys.exit(f"Interview {interview_id} has no recorded audio parts")
    base = parts[0][3]  # start at the first part, not at started_at
    print(f"Interview {interview_id}: {len(parts)} audio parts, first at {_clock(base)}")

    builder = TurnBuilder(interview_id, on_turn_updated=_ignore, on_turn_closed=_print_closed)
    t0 = asyncio.get_running_loop().time()
    await asyncio.gather(
        *(_speaker(builder, role, [p for p in parts if p[0] == role], t0, base) for role in ("interviewer", "candidate"))
    )

    print(f"\n--- Transcript ({len(builder.turns)} turns)")
    for turn in builder.turns:
        print(_line(turn))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("websockets").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("interview_id", type=int)
    args = parser.parse_args()
    asyncio.run(main(args.interview_id))
