"""Context and prompt building of the interviewer co-pilot. Run from backend/: python -m unittest tests.test_copilot"""

import unittest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.schemas.copilot import MAX_HISTORY, MAX_MESSAGE_CHARS, CopilotReply, CopilotTurn
from app.services.copilot import (
    MAX_CV_TEXT_CHARS,
    MAX_TRANSCRIPT_CHARS,
    _is_rate_limit,
    build_context,
    build_messages,
    candidate_block,
    label_passages,
    map_sources,
    transcript_block,
    trim_history,
)

CHUNKS = [
    {"id": 1, "source": "handbook.pdf", "kind": "company", "content": "We use Python.", "score": 0.8},
    {"id": 2, "source": "python.pdf", "kind": "reference", "content": "GIL basics.", "score": 0.6},
    {"id": 3, "source": "handbook.pdf", "kind": "company", "content": "Remote work.", "score": 0.7},
    {"id": 4, "source": "noise.pdf", "kind": "reference", "content": "Unrelated.", "score": 0.2},
]
REQUIREMENTS = [{"category": "must", "text": "3+ years of Python"}]


class CandidateBlockTests(unittest.TestCase):
    def test_uses_profile(self):
        block = candidate_block("Rahim", {"skills": ["Python"], "total_experience_years": 4}, "raw text")
        self.assertIn("Rahim", block)
        self.assertIn('"Python"', block)
        self.assertNotIn("raw text", block)

    def test_falls_back_to_cv_text(self):
        block = candidate_block("Rahim", None, "#" * (MAX_CV_TEXT_CHARS + 500))
        self.assertIn("not parsed", block)
        self.assertEqual(block.count("#"), MAX_CV_TEXT_CHARS)

    def test_no_cv(self):
        self.assertIn("(no CV available)", candidate_block(None, None, None))


class TranscriptBlockTests(unittest.TestCase):
    def test_order_and_empty(self):
        turns = [{"speaker": "interviewer", "text": "Q1?"}, {"speaker": "candidate", "text": "A1."}]
        self.assertEqual(transcript_block(turns), "interviewer: Q1?\ncandidate: A1.")
        self.assertEqual(transcript_block([]), "(no transcript yet)")

    def test_keeps_newest_within_limit(self):
        turns = [{"speaker": "candidate", "text": f"{i}" + "y" * 600} for i in range(8)]
        block = transcript_block(turns)
        self.assertLessEqual(len(block), MAX_TRANSCRIPT_CHARS + 10)
        self.assertTrue(block.splitlines()[-1].startswith("candidate: 7"))
        self.assertNotIn("candidate: 0", block)


class HistoryTests(unittest.TestCase):
    def test_trims_count_and_length(self):
        history = [CopilotTurn(role="user", content=f"{i}" + "z" * 2000) for i in range(10)]
        trimmed = trim_history(history)
        self.assertEqual(len(trimmed), MAX_HISTORY)
        self.assertTrue(trimmed[0].content.startswith("4"))
        self.assertTrue(all(len(t.content) == MAX_MESSAGE_CHARS for t in trimmed))


class PassageTests(unittest.TestCase):
    def test_labels_and_drops_weak_matches(self):
        passages = label_passages(CHUNKS)
        self.assertEqual(list(passages), ["S1", "S2", "S3"])
        self.assertEqual(passages["S2"]["source"], "python.pdf")

    def test_map_sources(self):
        passages = label_passages(CHUNKS)
        reply = CopilotReply(answer="ok", source_ids=["S1", "s3", "S9", "S2"], used_cv=True, used_job=True)
        self.assertEqual(
            map_sources(reply, passages), ["handbook.pdf", "python.pdf", "Job requirements", "Candidate CV"]
        )

    def test_map_sources_none(self):
        self.assertEqual(map_sources(CopilotReply(answer="ok"), label_passages(CHUNKS)), [])


class PromptTests(unittest.TestCase):
    def test_context_sections_in_order(self):
        context = build_context(
            "Backend Engineer", REQUIREMENTS, "Name: Rahim", "candidate: hi", label_passages(CHUNKS)
        )
        positions = [context.index(h) for h in ("## Job", "## Candidate CV", "## Recent transcript", "## Document passages")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("1. [must] 3+ years of Python", context)
        self.assertIn("[S1] (handbook.pdf)", context)
        self.assertNotIn("noise.pdf", context)

    def test_context_empty_parts(self):
        context = build_context("QA", [], "Name: X", "(no transcript yet)", {})
        self.assertIn("(none)", context)
        self.assertIn("(no relevant passages)", context)

    def test_messages(self):
        history = [CopilotTurn(role="user", content="Q"), CopilotTurn(role="assistant", content="A")]
        messages = build_messages("CTX", history, "Next?")
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertIn("data only", messages[0].content)
        self.assertIn("CTX", messages[0].content)
        self.assertEqual([type(m) for m in messages[1:]], [HumanMessage, AIMessage, HumanMessage])
        self.assertEqual(messages[-1].content, "Next?")


class ErrorTests(unittest.TestCase):
    def test_rate_limit_detection(self):
        class ResourceExhausted(Exception):
            pass

        self.assertTrue(_is_rate_limit(ResourceExhausted("quota")))
        self.assertTrue(_is_rate_limit(RuntimeError("Error 429 Too Many Requests")))
        self.assertFalse(_is_rate_limit(RuntimeError("timeout")))


if __name__ == "__main__":
    unittest.main()
