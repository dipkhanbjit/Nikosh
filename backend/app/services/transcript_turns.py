import asyncio
import logging
import time
from bisect import insort
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field

from app.core.config import settings
from app.services.transcription import TranscriptEvent
from app.services.transcripts import list_turns, save_turn

logger = logging.getLogger(__name__)

MERGE_GAP_SECONDS = 1.5  # finals of the same speaker closer than this join one turn
# After the room ended: wait this long for the streams' last turns and their saves
REMOVE_TIMEOUT_SECONDS = 15


def other_role(role: str) -> str:
    return "candidate" if role == "interviewer" else "interviewer"


@dataclass
class Turn:
    """Speaker-attributed, timestamped part of the transcript (times = seconds since started_at)."""

    id: int  # stable per interview; saved as seq
    interview_id: int
    role: str
    text: str
    start_s: float
    end_s: float
    confidence: float | None = None  # weighted by text length
    incomplete: bool = False  # true if any part was cut off by a stream drop
    position: int = 0  # index when all turns are ordered by start_s; can shift on overlap
    closed: bool = False
    _conf_sum: float = field(default=0.0, repr=False)
    _conf_len: int = field(default=0, repr=False)

    def add_part(self, event: TranscriptEvent, text: str) -> None:
        if self.text:
            self.text += " " + text
        else:
            self.text = text
        self.end_s = max(self.end_s, event.end_s)
        self.incomplete = self.incomplete or event.incomplete
        if event.confidence is not None:
            self._conf_sum += event.confidence * len(text)
            self._conf_len += len(text)
            self.confidence = round(self._conf_sum / self._conf_len, 3)

    def to_dict(self) -> dict:
        data = asdict(self)
        del data["_conf_sum"], data["_conf_len"]
        return data


OnTurn = Callable[[Turn], Awaitable[None]]


def _log_turn(action: str, turn: Turn) -> None:
    text = f": {turn.text}" if settings.transcript_log_text else ""
    logger.info(
        "Interview %s: turn %d %s (%s, %.1f-%.1f s, %d chars%s)%s",
        turn.interview_id, turn.id, action, turn.role, turn.start_s, turn.end_s, len(turn.text),
        ", incomplete" if turn.incomplete else "", text,
    )  # fmt: skip


async def log_turn_updated(turn: Turn) -> None:
    """7.3.1 sends the turn to the interviewer; for now only logged."""
    if logger.isEnabledFor(logging.DEBUG):
        _log_turn("updated", turn)


async def log_turn_closed(turn: Turn) -> None:
    _log_turn("closed", turn)


class TurnBuilder:
    """Groups the final results of both speakers of one interview into turns (no LLM).
    Also keeps each speaker's current interim text as a live preview."""

    def __init__(
        self,
        interview_id: int,
        on_turn_updated: OnTurn = log_turn_updated,
        on_turn_closed: OnTurn = log_turn_closed,
        save: bool = False,
    ) -> None:
        self.interview_id = interview_id
        self.on_turn_updated = on_turn_updated
        self.on_turn_closed = on_turn_closed
        self.save = save  # save closed turns to the database (off in tests and the dev script)
        self.pending: set[asyncio.Task] = set()  # saves still running
        self.streams = 0  # transcription streams using this builder
        self.turns: list[Turn] = []  # ordered by start_s
        self.open: dict[str, Turn] = {}  # role -> its open turn
        self.interims: dict[str, dict] = {}  # role -> {"text", "start_s"}
        self._next_id = 1
        self._lock = asyncio.Lock()  # both speakers' streams call add()

    def restore(self, saved: list) -> None:
        """Continue after a reconnect / restart: saved turns come back closed, ids go on from them."""
        for row in saved:
            self.turns.append(
                Turn(row.seq, self.interview_id, row.speaker, row.text, row.start_s, row.end_s,
                     row.confidence, row.incomplete, closed=True)
            )  # fmt: skip
        self.turns.sort(key=lambda t: t.start_s)
        for i, t in enumerate(self.turns):
            t.position = i
        self._next_id = max((t.id for t in self.turns), default=0) + 1

    async def add(self, event: TranscriptEvent) -> None:
        async with self._lock:
            role = event.role
            text = " ".join(event.text.split())
            if event.utterance_end:
                await self._close(role)
                return
            if not event.is_final:
                if text:
                    self.interims[role] = {"text": text, "start_s": event.start_s}
                return
            self.interims.pop(role, None)
            if not text:
                return
            # The other speaker's turn ends when this speaker starts after it (overlap keeps both open)
            other = self.open.get(other_role(role))
            if other and event.start_s > other.end_s:
                await self._close(other.role)
            turn = self.open.get(role)
            if turn and (
                event.start_s - turn.end_s >= MERGE_GAP_SECONDS or self._other_started_after(role, turn.end_s)
            ):
                await self._close(role)
                turn = None
            if turn:
                turn.add_part(event, text)
                await self.on_turn_updated(turn)
            else:
                await self._new_turn(event, text)

    def _other_started_after(self, role: str, time_s: float) -> bool:
        for turn in reversed(self.turns):
            if turn.start_s <= time_s:
                return False
            if turn.role != role:
                return True
        return False

    async def _new_turn(self, event: TranscriptEvent, text: str) -> None:
        turn = Turn(self._next_id, self.interview_id, event.role, "", event.start_s, event.end_s)
        self._next_id += 1
        turn.add_part(event, text)
        self.open[event.role] = turn
        insort(self.turns, turn, key=lambda t: t.start_s)
        # An overlapping turn can land before others: their position moves too
        shifted = []
        for i, t in enumerate(self.turns):
            if t.position != i or t is turn:
                t.position = i
                if t is not turn:
                    shifted.append(t)
        await self.on_turn_updated(turn)
        for t in shifted:
            await self.on_turn_updated(t)

    async def _close(self, role: str) -> None:
        turn = self.open.pop(role, None)
        if turn:
            turn.closed = True
            await self.on_turn_closed(turn)
            if self.save:  # in a thread, so the lock and the audio path never wait for the database
                task = asyncio.create_task(asyncio.to_thread(save_turn, turn))
                self.pending.add(task)
                task.add_done_callback(self.pending.discard)

    async def speaker_stopped(self, role: str) -> None:
        """The speaker's stream stopped: close the open turn and drop the preview."""
        async with self._lock:
            self.interims.pop(role, None)
            await self._close(role)

    def snapshot(self) -> dict:
        """All turns in order plus each speaker's current interim text (for a reconnect)."""
        return {"turns": [t.to_dict() for t in self.turns], "interims": dict(self.interims)}


class TurnRegistry:
    """In-memory TurnBuilder per interview (single Uvicorn worker, like the room registry).
    A transcription stream keeps its builder, so its last results still arrive after remove()."""

    def __init__(self) -> None:
        self._builders: dict[int, TurnBuilder] = {}
        self._lock = asyncio.Lock()  # both speakers may ask for a new builder at once
        self._removers: set[asyncio.Task] = set()

    async def get(self, interview_id: int) -> TurnBuilder:
        """The interview's builder; a new one starts from the turns already saved."""
        async with self._lock:
            builder = self._builders.get(interview_id)
            if builder is None:
                builder = TurnBuilder(interview_id, save=True)
                try:
                    builder.restore(await asyncio.to_thread(list_turns, interview_id))
                except Exception:
                    logger.exception("Interview %s: saved transcript turns could not be loaded", interview_id)
                if builder.turns:
                    logger.info("Interview %s: transcript resumed (%d saved turns)", interview_id, len(builder.turns))
                self._builders[interview_id] = builder
            return builder

    def remove(self, interview_id: int) -> None:
        """The room ended: drop the builder in the background once its streams have stopped
        (their last turns close then) and the saves are done, or after REMOVE_TIMEOUT_SECONDS."""
        task = asyncio.create_task(self._remove_when_done(interview_id))
        self._removers.add(task)
        task.add_done_callback(self._removers.discard)

    async def _remove_when_done(self, interview_id: int) -> None:
        builder = self._builders.get(interview_id)
        if builder is None:
            return
        deadline = time.monotonic() + REMOVE_TIMEOUT_SECONDS
        while (builder.streams or builder.pending) and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
        if builder.streams or builder.pending:
            logger.warning(
                "Interview %s: transcript builder removed with %d streams and %d saves still running",
                interview_id, builder.streams, len(builder.pending),
            )  # fmt: skip
        async with self._lock:
            if self._builders.get(interview_id) is builder:
                del self._builders[interview_id]
        logger.info("Interview %s: transcript builder removed (%d turns)", interview_id, len(builder.turns))


turns = TurnRegistry()
