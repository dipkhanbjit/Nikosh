import asyncio
import json
import logging
import re
import time
from bisect import bisect_right
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Interview
from app.services.audio import BYTES_PER_SECOND
from app.services.transcription import OnEvent, Transcriber, TranscriptEvent, _ignore_event

logger = logging.getLogger(__name__)

DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"
CONNECT_TIMEOUT_SECONDS = 10
KEEPALIVE_SECONDS = 5  # Deepgram closes a stream after ~10 s without audio (e.g. muted)
CLOSE_WAIT_SECONDS = 3  # time for the last results after CloseStream
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
    """One Deepgram live stream for one speaker of one interview."""

    async def start(self, interview_id: int, role: str, on_event: OnEvent = _ignore_event) -> None:
        await super().start(interview_id, role, on_event)
        if not settings.deepgram_api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        try:
            keyterms = await asyncio.to_thread(load_keyterms, interview_id)
        except Exception:
            logger.exception("Interview %s: keyterms could not be loaded", interview_id)
            keyterms = []
        self.time_map = TimeMap()
        self.sent_bytes = 0
        self.results = 0
        self.closed = False
        self._stopping = False
        self._last_send = time.monotonic()
        self.ws: ClientConnection = await connect(
            f"{DEEPGRAM_URL}?{self._query(keyterms)}",
            additional_headers={"Authorization": f"Token {settings.deepgram_api_key}"},
            open_timeout=CONNECT_TIMEOUT_SECONDS,
        )
        self._receiver = asyncio.create_task(self._receive())
        self._keepalive = asyncio.create_task(self._keep_alive())
        logger.info(
            "Interview %s: Deepgram stream opened for %s (%s, %d keyterms)",
            interview_id,
            role,
            settings.deepgram_model,
            len(keyterms),
        )

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
        if self.closed:
            return
        # offset_s is when the chunk arrived, i.e. the end of the audio it holds
        audio_s = self.sent_bytes / BYTES_PER_SECOND
        self.time_map.add_chunk(audio_s, max(offset_s - len(chunk) / BYTES_PER_SECOND, 0.0))
        try:
            await self.ws.send(chunk)
        except ConnectionClosed:
            self._lost()
            return
        self.sent_bytes += len(chunk)
        self._last_send = time.monotonic()

    def _lost(self) -> None:
        if not self.closed:
            self.closed = True
            code = self.ws.close_code
            logger.warning("Interview %s: Deepgram stream for %s closed (code %s)", self.interview_id, self.role, code)

    async def _keep_alive(self) -> None:
        while not self.closed:
            await asyncio.sleep(1)
            if time.monotonic() - self._last_send >= KEEPALIVE_SECONDS:
                try:
                    await self.ws.send(json.dumps({"type": "KeepAlive"}))
                except ConnectionClosed:
                    self._lost()
                    return
                self._last_send = time.monotonic()

    async def _receive(self) -> None:
        try:
            async for message in self.ws:
                if isinstance(message, str):
                    await self._handle(json.loads(message))
        except ConnectionClosed:
            pass
        except Exception:
            logger.exception("Interview %s: Deepgram results for %s failed", self.interview_id, self.role)
        if not self._stopping:
            self._lost()
        self.closed = True

    async def _handle(self, data: dict) -> None:
        if data.get("type") != "Results":
            return
        alternatives = (data.get("channel") or {}).get("alternatives") or []
        if not alternatives or not alternatives[0].get("transcript", "").strip():
            return
        best = alternatives[0]
        start = float(data.get("start", 0.0))
        end = start + float(data.get("duration", 0.0))
        self.results += 1
        event = TranscriptEvent(
            interview_id=self.interview_id,
            role=self.role,
            text=best["transcript"].strip(),
            is_final=bool(data.get("is_final")),
            start_s=self.time_map.to_interview(start),
            end_s=self.time_map.to_interview(end),
            confidence=best.get("confidence"),
        )
        try:
            await self.on_event(event)
        except Exception:
            logger.exception("Interview %s: transcript event handler failed", self.interview_id)

    async def stop(self) -> None:
        self._stopping = True
        self._keepalive.cancel()
        if not self.closed:
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
            except ConnectionClosed:
                pass
        try:
            await asyncio.wait_for(asyncio.shield(self._receiver), CLOSE_WAIT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning("Interview %s: Deepgram gave no final results for %s in time", self.interview_id, self.role)
            self._receiver.cancel()
        await self.ws.close()
        logger.info(
            "Interview %s: Deepgram stream closed for %s (%.1f s audio sent, %d results)",
            self.interview_id,
            self.role,
            self.sent_bytes / BYTES_PER_SECOND,
            self.results,
        )
