"""Code-side rules of the requirement mapping. Run from backend/: python -m unittest tests.test_requirement_mapping"""

import unittest

from app.schemas.requirement_mapping import RequirementMappingItem, RequirementMappingResult
from app.services.requirement_mapping import _build_mapping, _prompt

REQUIREMENTS = [
    {"text": "3+ years of Python", "category": "experience"},
    {"text": "REST API design", "category": "skill"},
]


def pair(pair_id, answered=True, parent_id=None):
    return {
        "id": pair_id, "type": "follow_up" if parent_id else "main", "parent_id": parent_id,
        "question": f"Question {pair_id}?", "sub_questions": [],
        "answer": f"Answer {pair_id}." if answered else "", "answered": answered, "incomplete": False,
        "question_turns": [pair_id * 10], "answer_turns": [pair_id * 10 + 1] if answered else [],
        "start_s": pair_id * 60.0, "end_s": pair_id * 60.0 + 30,
    }


def item(requirement_id, coverage="demonstrated", support=(1,)):
    return RequirementMappingItem(
        requirement_id=requirement_id, coverage=coverage,
        supporting_pairs=list(support), justification=" Clear example. ",
    )


class BuildMappingTest(unittest.TestCase):
    def build(self, items, pairs, requirements=REQUIREMENTS):
        return _build_mapping(RequirementMappingResult(mappings=items), requirements, pairs)

    def test_mapped_requirement_with_citations(self):
        m = self.build([item(1, support=(2,)), item(2, "partial", (1,))], [pair(1), pair(2)])
        self.assertEqual([x["requirement_id"] for x in m], [1, 2])
        first = m[0]
        self.assertEqual(first["text"], "3+ years of Python")
        self.assertEqual(first["category"], "experience")
        self.assertEqual((first["status"], first["coverage"]), ("mapped", "demonstrated"))
        self.assertEqual(first["supporting_pairs"], [2])
        self.assertEqual(first["justification"], "Clear example.")
        self.assertEqual(first["citations"], [{
            "pair_id": 2, "question": "Question 2?", "speaker": "candidate",
            "start_s": 120.0, "end_s": 150.0, "question_turns": [20], "answer_turns": [21],
        }])
        self.assertEqual(m[1]["coverage"], "partial")

    def test_invalid_pairs_dropped_and_downgraded(self):
        # Pair 2 is unanswered, pair 9 does not exist.
        m = self.build([item(1, support=(9, 2)), item(2, support=(3, 1, 1, 9))],
                       [pair(1), pair(2, answered=False), pair(3)])
        self.assertEqual((m[0]["coverage"], m[0]["supporting_pairs"], m[0]["citations"]),
                         ("not_covered", [], []))
        self.assertEqual(m[1]["coverage"], "demonstrated")
        self.assertEqual(m[1]["supporting_pairs"], [1, 3])

    def test_not_covered_clears_pairs(self):
        [m, _] = self.build([item(1, "not_covered", (1,)), item(2)], [pair(1)])
        self.assertEqual((m["coverage"], m["supporting_pairs"], m["citations"]), ("not_covered", [], []))

    def test_missing_requirement_not_mapped(self):
        m = self.build([item(1)], [pair(1)])
        self.assertEqual(m[1]["status"], "not_mapped")
        self.assertIsNone(m[1]["coverage"])
        self.assertEqual(m[1]["citations"], [])

    def test_unknown_and_duplicate_requirements_ignored(self):
        m = self.build([item(1), item(1, "not_covered", ()), item(2), item(7)], [pair(1)])
        self.assertEqual(len(m), 2)
        self.assertEqual(m[0]["coverage"], "demonstrated")

    def test_no_answers_means_not_covered(self):
        m = _build_mapping(None, REQUIREMENTS, [pair(1, answered=False)])
        self.assertEqual([x["coverage"] for x in m], ["not_covered", "not_covered"])
        self.assertEqual({x["status"] for x in m}, {"mapped"})

    def test_no_requirements(self):
        self.assertEqual(self.build([item(1)], [pair(1)], requirements=[]), [])


class PromptTest(unittest.TestCase):
    def test_prompt_numbers_requirements_and_shows_scores(self):
        pairs = [pair(1), pair(2, answered=False), pair(3, parent_id=1)]
        evaluations = [
            {"pair_id": 1, "percent": 75, "accuracy_verdict": "supported"},
            {"pair_id": 3, "percent": None, "accuracy_verdict": None},
        ]
        text = _prompt(REQUIREMENTS, pairs, evaluations, "Python Developer")
        self.assertIn("Job title: Python Developer", text)
        self.assertIn("[R1] (experience) 3+ years of Python", text)
        self.assertIn("[R2] (skill) REST API design", text)
        self.assertNotIn("pair_id 2", text)
        self.assertIn("Follow-up to: Question 1?", text)
        self.assertIn("Evaluation: 75% (accuracy: supported)", text)
        self.assertIn("Evaluation: none", text)


if __name__ == "__main__":
    unittest.main()
