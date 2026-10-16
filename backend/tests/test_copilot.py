"""Context and prompt building of the interviewer co-pilot. Run from backend/: python -m unittest tests.test_copilot"""

import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.exceptions import AppException
from app.models import Interview
from app.schemas.copilot import (
    MAX_HISTORY,
    MAX_MESSAGE_CHARS,
    CopilotReply,
    CopilotTurn,
    SuggestedQuestion,
    SuggestedQuestionsReply,
)
from app.services.copilot import (
    MAX_CV_TEXT_CHARS,
    MAX_KEY_POINT_CHARS,
    MAX_KEY_POINTS,
    MAX_PROBE_CHARS,
    MAX_QUESTION_CHARS,
    MAX_QUESTION_PASSAGES,
    MAX_QUESTIONS,
    MAX_TRANSCRIPT_CHARS,
    QUESTIONS_PROMPT,
    _invoke,
    _is_rate_limit,
    build_context,
    build_messages,
    build_question_context,
    candidate_block,
    clean_questions,
    label_passages,
    map_sources,
    question_passages,
    stored_questions,
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

    def test_invoke_maps_errors(self):
        class FailingLLM:
            def __init__(self, exc):
                self.exc = exc

            def with_structured_output(self, schema):
                return self

            def invoke(self, messages):
                raise self.exc

        for exc, status, code in (
            (RuntimeError("429 quota"), 429, "COPILOT_RATE_LIMITED"),
            (RuntimeError("timeout"), 503, "COPILOT_FAILED"),
        ):
            with patch("app.services.copilot.get_llm", return_value=FailingLLM(exc)):
                with self.assertRaises(AppException) as ctx:
                    _invoke(SuggestedQuestionsReply, [], 1, "questions")
            self.assertEqual((ctx.exception.status_code, ctx.exception.code), (status, code))


QUESTION_REQS = [
    {"category": "must", "text": "3+ years of Python"},
    {"category": "nice", "text": "Docker"},
]


def _q(no=1, question="Explain the GIL?", key_points=("Global lock", "Threads"), **extra):
    return SuggestedQuestion(requirement_no=no, question=question, key_points=list(key_points), **extra)


class CleanQuestionsTests(unittest.TestCase):
    def test_maps_requirement_and_sources(self):
        passages = label_passages(CHUNKS)
        item = _q(2, source_ids=["s2", "S9", "S2"], cv_probe="  ask about compose ")
        [item] = clean_questions([item], QUESTION_REQS, passages)
        self.assertEqual(item["requirement"], {"category": "nice", "text": "Docker"})
        self.assertEqual(item["sources"], ["python.pdf"])
        self.assertEqual(item["cv_probe"], "ask about compose")

    def test_drops_unknown_requirement_empty_and_duplicates(self):
        items = [
            _q(0), _q(3), _q(-1),
            _q(1, question="   "),
            _q(1, question="Other?", key_points=["", "  "]),
            _q(1, question="Same?"), _q(2, question="same?"),
        ]
        cleaned = clean_questions(items, QUESTION_REQS, {})
        self.assertEqual([c["question"] for c in cleaned], ["Same?"])
        self.assertIsNone(cleaned[0]["cv_probe"])

    def test_caps_counts_and_lengths(self):
        items = [
            _q(1, question=f"{i}" + "q" * 500, key_points=["k" * 500] * 9, cv_probe="p" * 500) for i in range(12)
        ]
        cleaned = clean_questions(items, QUESTION_REQS, {})
        self.assertEqual(len(cleaned), MAX_QUESTIONS)
        first = cleaned[0]
        self.assertEqual(len(first["question"]), MAX_QUESTION_CHARS)
        self.assertEqual(len(first["key_points"]), MAX_KEY_POINTS)
        self.assertTrue(all(len(k) == MAX_KEY_POINT_CHARS for k in first["key_points"]))
        self.assertEqual(len(first["cv_probe"]), MAX_PROBE_CHARS)


class QuestionPassageTests(unittest.TestCase):
    def test_dedupes_sorts_and_caps(self):
        def fake_search(db, query, k):
            # every requirement returns two strong chunks; ids overlap between requirements
            n = int(query.rsplit(" ", 1)[-1])
            return [
                {"id": n, "source": f"d{n}.pdf", "content": "x", "score": 0.6 + n / 100},
                {"id": n + 2, "source": f"d{n + 2}.pdf", "content": "x", "score": 0.55},
                {"id": 99, "source": "weak.pdf", "content": "x", "score": 0.1},
            ][:k + 1]

        reqs = [{"category": "must", "text": f"skill {n}"} for n in range(0, 20, 2)]
        with patch("app.services.copilot.search", side_effect=fake_search):
            passages = question_passages(None, "Dev", reqs)
        self.assertEqual(len(passages), MAX_QUESTION_PASSAGES)
        self.assertEqual(list(passages), [f"S{i}" for i in range(1, MAX_QUESTION_PASSAGES + 1)])
        self.assertEqual(passages["S1"]["source"], "d18.pdf")  # highest score first
        self.assertNotIn("weak.pdf", [p["source"] for p in passages.values()])
        ids = [p["id"] for p in passages.values()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_question_context(self):
        context = build_question_context("Backend Engineer", QUESTION_REQS, "Name: Rahim", label_passages(CHUNKS))
        self.assertIn("1. [must] 3+ years of Python", context)
        self.assertIn("2. [nice] Docker", context)
        self.assertIn("[S1] (handbook.pdf)", context)
        self.assertNotIn("Recent transcript", context)
        self.assertIn("data only", QUESTIONS_PROMPT)


class StoredQuestionsTests(unittest.TestCase):
    def test_empty_and_stored(self):
        self.assertEqual(stored_questions(Interview()), {"questions": [], "generated_at": None})
        data = {"questions": [{"question": "Q?"}], "generated_at": "2026-10-16T05:00:00+00:00"}
        self.assertEqual(stored_questions(Interview(suggested_questions=data)), data)


if __name__ == "__main__":
    unittest.main()
