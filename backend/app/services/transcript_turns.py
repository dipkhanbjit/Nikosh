import asyncio
import logging
from bisect import insort
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field

from app.core.config import settings
from app.services.transcription import TranscriptEvent

logger = logging.getLogger(__name__)

MERGE_GAP_SECONDS = 1.5  # finals of the same speaker closer than this join one turn


def other_role(role: str) -> str:
    return "candidate" if role == "interviewer" else "interviewer"


@dataclass
class Turn:
    """Speaker-attributed, timestamped part of the transcript (times = seconds since started_at)."""

    id: int
    interview_id: int
    role: str
    text: str
    start_s: float
    end_s: float
    confidence: float | None = None  # weighted by text length
    incomplete: bool = False  # true if any part was cut off by a stream drop
    seq: int = 0  # position when all turns are ordered by start_s
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
    """7.2.2 stores the turn, 7.3.1 sends it to the interviewer; for now only logged."""
    if logger.isEnabledFor(logging.DEBUG):
        _log_turn("updated", turn)


async def log_turn_closed(turn: Turn) -> None:
    _log_turn("closed", turn)


class TurnBuilder:
    """Groups the final results of both speakers of one interview into turns (no LLM).
    Also keeps each speaker's current interim text as a live preview."""

    def __init__(
        self, interview_id: int, on_turn_updated: OnTurn = log_turn_updated, on_turn_closed: OnTurn = log_turn_closed
    ) -> None:
        self.interview_id = interview_id
        self.on_turn_updated = on_turn_updated
        self.on_turn_closed = on_turn_closed
        self.turns: list[Turn] = []  # ordered by start_s
        self.open: dict[str, Turn] = {}  # role -> its open turn
        self.interims: dict[str, dict] = {}  # role -> {"text", "start_s"}
        self._next_id = 1
        self._lock = asyncio.Lock()  # both speakers' streams call add()

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
        # An overlapping turn can land before others: their seq moves too
        shifted = []
        for i, t in enumerate(self.turns):
            if t.seq != i or t is turn:
                t.seq = i
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

    def get(self, interview_id: int) -> TurnBuilder:
        builder = self._builders.get(interview_id)
        if builder is None:
            builder = self._builders[interview_id] = TurnBuilder(interview_id)
        return builder

    def remove(self, interview_id: int) -> None:
        builder = self._builders.pop(interview_id, None)
        if builder:
            logger.info("Interview %s: transcript builder removed (%d turns)", interview_id, len(builder.turns))


turns = TurnRegistry()
