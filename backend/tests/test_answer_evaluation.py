"""Code-side rules of the answer evaluation. Run from backend/: python -m unittest tests.test_answer_evaluation"""

import unittest

from app.schemas.answer_evaluation import AnswerEvaluationItem, AnswerEvaluationResult
from app.services.answer_evaluation import _build_evaluations, _prompt


def pair(pair_id, answered=True, parent_id=None):
    return {
        "id": pair_id, "type": "follow_up" if parent_id else "main", "parent_id": parent_id,
        "question": f"Question {pair_id}?", "sub_questions": [],
        "answer": f"Answer {pair_id}." if answered else "", "answered": answered, "incomplete": False,
    }


def item(pair_id, scores=(4, 4, 3, 5), verdict="supported", cited=("K1",)):
    r, a, c, q = scores
    return AnswerEvaluationItem(
        pair_id=pair_id, relevance=r, accuracy=a, completeness=c, quality=q,
        accuracy_verdict=verdict, cited_chunks=list(cited), justification=" Good answer. ",
    )


PASSAGES = {
    "K1": {"id": 41, "source": "python.pdf", "kind": "reference", "content": "..."},
    "K2": {"id": 77, "source": "company.pdf", "kind": "company", "content": "..."},
}


class BuildEvaluationsTest(unittest.TestCase):
    def build(self, items, pairs, allowed):
        return _build_evaluations(AnswerEvaluationResult(evaluations=items), pairs, PASSAGES, allowed)

    def test_evaluated_pair(self):
        [e] = self.build([item(1)], [pair(1)], {1: ["K1", "K2"]})
        self.assertEqual(e["status"], "evaluated")
        self.assertEqual(e["scores"], {"relevance": 4, "accuracy": 4, "completeness": 3, "quality": 5})
        self.assertEqual(e["overall"], 4.0)
        self.assertEqual(e["percent"], 75)
        self.assertEqual(e["accuracy_verdict"], "supported")
        self.assertEqual(e["justification"], "Good answer.")
        self.assertEqual(e["evidence"], [{"chunk_id": 41, "source": "python.pdf", "kind": "reference"}])

    def test_unanswered_pair_gets_lowest_scores(self):
        [e] = self.build([item(1)], [pair(1, answered=False)], {})
        self.assertEqual(e["status"], "not_answered")
        self.assertEqual(set(e["scores"].values()), {1})
        self.assertEqual((e["overall"], e["percent"]), (1.0, 0))
        self.assertEqual(e["accuracy_verdict"], "not_answered")

    def test_no_result_when_nothing_answered(self):
        evaluations = _build_evaluations(None, [pair(1, answered=False)], {}, {})
        self.assertEqual([e["status"] for e in evaluations], ["not_answered"])

    def test_missing_pair_is_not_evaluated(self):
        evaluations = self.build([item(1)], [pair(1), pair(2)], {1: ["K1"], 2: ["K1"]})
        self.assertEqual([e["status"] for e in evaluations], ["evaluated", "not_evaluated"])
        self.assertIsNone(evaluations[1]["scores"])
        self.assertIsNone(evaluations[1]["percent"])

    def test_unknown_pair_and_duplicates_ignored(self):
        evaluations = self.build([item(1), item(1, scores=(1, 1, 1, 1)), item(9)], [pair(1)], {1: ["K1"]})
        self.assertEqual(len(evaluations), 1)
        self.assertEqual(evaluations[0]["overall"], 4.0)

    def test_scores_clamped(self):
        [e] = self.build([item(1, scores=(0, 9, 3, -2))], [pair(1)], {1: ["K1"]})
        self.assertEqual(e["scores"], {"relevance": 1, "accuracy": 5, "completeness": 3, "quality": 1})

    def test_invalid_citations_dropped(self):
        # K2 exists but is not allowed for this pair; K9 does not exist.
        [e] = self.build([item(1, cited=("K2", "K9", "K1", "K1"))], [pair(1)], {1: ["K1"]})
        self.assertEqual([x["chunk_id"] for x in e["evidence"]], [41])
        self.assertEqual(e["accuracy_verdict"], "supported")

    def test_verdict_without_valid_citation_not_verifiable(self):
        [e] = self.build([item(1, verdict="contradicted", cited=("K2",))], [pair(1)], {1: ["K1"]})
        self.assertEqual(e["accuracy_verdict"], "not_verifiable")
        self.assertEqual(e["evidence"], [])


class PromptTest(unittest.TestCase):
    def test_prompt_skips_unanswered_and_shows_context(self):
        pairs = [pair(1), pair(2, answered=False), pair(3, parent_id=1)]
        text = _prompt(pairs, PASSAGES, {1: ["K1"], 3: []}, "Python Developer")
        self.assertIn("Job title: Python Developer", text)
        self.assertIn("[K1] (reference: python.pdf)", text)
        self.assertNotIn("pair_id 2", text)
        self.assertIn("Follow-up to: Question 1?", text)
        self.assertIn("Passages: none", text)


if __name__ == "__main__":
    unittest.main()
