"""Grouping rules of the TurnBuilder. Run from backend/: python -m unittest tests.test_transcript_turns"""

import unittest
from types import SimpleNamespace

from app.services.transcript_turns import TurnBuilder
from app.services.transcription import TranscriptEvent

I, C = "interviewer", "candidate"


def final(role, text, start, end, conf=None, incomplete=False):
    return TranscriptEvent(1, role, text, True, start, end, conf, incomplete)


def interim(role, text, start, end):
    return TranscriptEvent(1, role, text, False, start, end)


def utterance_end(role, at):
    return TranscriptEvent(1, role, "", True, at, at, utterance_end=True)


class TurnBuilderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.closed = []
        self.updated = []

        async def on_updated(turn):
            self.updated.append(turn.id)

        async def on_closed(turn):
            self.closed.append(turn.id)

        self.builder = TurnBuilder(1, on_updated, on_closed)

    async def feed(self, *events):
        for event in events:
            await self.builder.add(event)
        return self.builder.turns

    def texts(self):
        return [(t.role, t.text) for t in self.builder.turns]

    async def test_same_speaker_merge(self):
        turns = await self.feed(
            final(I, " Tell me ", 0.0, 1.0, 0.9),
            final(I, "about yourself.", 1.4, 2.4, 0.6),
        )
        self.assertEqual(self.texts(), [(I, "Tell me about yourself.")])
        self.assertEqual((turns[0].start_s, turns[0].end_s), (0.0, 2.4))
        # length-weighted: 7 chars at 0.9, 15 chars at 0.6
        self.assertAlmostEqual(turns[0].confidence, (7 * 0.9 + 15 * 0.6) / 22, places=3)
        self.assertFalse(turns[0].closed)

    async def test_speaker_switch_closes_turn(self):
        turns = await self.feed(
            final(I, "Any questions?", 0.0, 1.0),
            final(C, "Yes, one.", 1.5, 2.2),
            final(I, "Go ahead.", 2.5, 3.0),
        )
        self.assertEqual([t.role for t in turns], [I, C, I])
        self.assertEqual([t.position for t in turns], [0, 1, 2])
        self.assertEqual(self.closed, [1, 2])
        self.assertTrue(turns[0].closed and turns[1].closed)
        self.assertFalse(turns[2].closed)

    async def test_long_pause_starts_new_turn(self):
        await self.feed(final(C, "First answer.", 0.0, 2.0), final(C, "Second answer.", 4.0, 5.0))
        self.assertEqual(self.texts(), [(C, "First answer."), (C, "Second answer.")])
        self.assertEqual(self.closed, [1])

    async def test_utterance_end_closes_turn(self):
        await self.feed(final(C, "Done.", 0.0, 1.0), utterance_end(C, 1.0), final(C, "Also this.", 1.8, 2.5))
        self.assertEqual(self.texts(), [(C, "Done."), (C, "Also this.")])
        self.assertEqual(self.closed, [1])

    async def test_other_speaker_in_between_blocks_merge(self):
        # The candidate starts and ends within the gap: the interviewer's next words are a new turn
        await self.feed(
            final(I, "So", 0.0, 1.0),
            final(C, "Mm.", 1.1, 1.3),
            final(I, "next question.", 1.4, 2.0),
        )
        self.assertEqual(self.texts(), [(I, "So"), (C, "Mm."), (I, "next question.")])

    async def test_overlap_keeps_both_open(self):
        turns = await self.feed(
            final(I, "And what about", 0.0, 2.0),
            final(C, "Sorry,", 1.5, 2.2),  # starts before the interviewer's turn ends
        )
        self.assertEqual(self.closed, [])  # both open while they overlap
        await self.feed(final(I, "testing?", 2.3, 2.8))  # merges: the candidate started before 2.0
        self.assertEqual(self.texts(), [(I, "And what about testing?"), (C, "Sorry,")])
        self.assertEqual(self.closed, [2])  # the interviewer went on after the candidate's end
        self.assertEqual([t.position for t in turns], [0, 1])

    async def test_late_overlapping_turn_is_ordered_by_start(self):
        await self.feed(final(C, "Answer.", 2.0, 3.0), final(I, "Question?", 1.0, 2.5))
        self.assertEqual(self.texts(), [(I, "Question?"), (C, "Answer.")])
        self.assertEqual([t.position for t in self.builder.turns], [0, 1])
        self.assertIn(1, self.updated[-1:])  # the shifted candidate turn was reported

    async def test_incomplete_part(self):
        turns = await self.feed(
            final(C, "I worked on", 0.0, 1.0, 0.9, incomplete=True),
            final(C, "a payment system.", 1.2, 2.5, 0.9),
        )
        self.assertEqual(self.texts(), [(C, "I worked on a payment system.")])
        self.assertTrue(turns[0].incomplete)

    async def test_empty_text_is_ignored(self):
        await self.feed(final(I, "   ", 0.0, 1.0), final(I, "", 1.0, 1.5))
        self.assertEqual(self.builder.turns, [])

    async def test_interim_preview_and_stop(self):
        await self.feed(interim(C, "I think", 0.0, 0.5))
        self.assertEqual(self.builder.snapshot()["interims"], {C: {"text": "I think", "start_s": 0.0}})
        await self.feed(final(C, "I think so.", 0.0, 1.0))
        self.assertEqual(self.builder.snapshot()["interims"], {})
        await self.feed(interim(C, "and", 1.2, 1.4))
        await self.builder.speaker_stopped(C)
        snapshot = self.builder.snapshot()
        self.assertEqual(snapshot["interims"], {})
        self.assertTrue(snapshot["turns"][0]["closed"])
        self.assertNotIn("_conf_sum", snapshot["turns"][0])

    async def test_restore_continues_ids(self):
        saved = [
            SimpleNamespace(seq=2, speaker=C, text="Yes.", start_s=3.0, end_s=4.0, confidence=0.9, incomplete=False),
            SimpleNamespace(seq=1, speaker=I, text="Ready?", start_s=0.0, end_s=1.0, confidence=None, incomplete=True),
        ]
        self.builder.restore(saved)
        await self.feed(final(I, "Let's start.", 5.0, 6.0))
        snapshot = self.builder.snapshot()["turns"]
        self.assertEqual([t["id"] for t in snapshot], [1, 2, 3])
        self.assertEqual([t["position"] for t in snapshot], [0, 1, 2])
        self.assertEqual([t["closed"] for t in snapshot], [True, True, False])
        self.assertTrue(snapshot[0]["incomplete"])


if __name__ == "__main__":
    unittest.main()
