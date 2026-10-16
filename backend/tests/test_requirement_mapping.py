"""Code-side rules of the requirement mapping. Run from backend/: python -m unittest tests.test_requirement_mapping"""

import unittest

from app.schemas.requirement_mapping import RequirementMappingItem, RequirementMappingResult
from app.services.requirement_mapping import SYSTEM_PROMPT, _build_mapping, _prompt, summarize_gaps

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


def item(requirement_id, coverage="demonstrated", support=(1,), follow_up=""):
    return RequirementMappingItem(
        requirement_id=requirement_id, coverage=coverage,
        supporting_pairs=list(support), justification=" Clear example. ",
        follow_up_question=follow_up,
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

    def test_follow_up_cleared_on_demonstrated(self):
        m = self.build([item(1, follow_up="Why?"), item(2)], [pair(1)])
        self.assertEqual(m[0]["follow_up_question"], "")

    def test_follow_up_kept_on_partial_and_not_covered(self):
        m = self.build([item(1, "partial", follow_up=" How did you test it? "),
                        item(2, "not_covered", (), "Have you designed a REST API?")], [pair(1)])
        self.assertEqual(m[0]["follow_up_question"], "How did you test it?")
        self.assertEqual(m[1]["follow_up_question"], "Have you designed a REST API?")

    def test_empty_follow_up_stays_empty(self):
        m = self.build([item(1, "partial"), item(2, "not_covered", ())], [pair(1)])
        self.assertEqual([x["follow_up_question"] for x in m], ["", ""])

    def test_follow_up_kept_after_downgrade(self):
        # Demonstrated with no valid support becomes not_covered, so the follow-up stays.
        m = self.build([item(1, support=(9,), follow_up="Give an example?"), item(2)], [pair(1)])
        self.assertEqual((m[0]["coverage"], m[0]["follow_up_question"]), ("not_covered", "Give an example?"))

    def test_follow_up_empty_when_not_mapped_or_no_answers(self):
        m = self.build([item(1)], [pair(1)])
        self.assertEqual(m[1]["follow_up_question"], "")
        m = _build_mapping(None, REQUIREMENTS, [pair(1, answered=False)])
        self.assertEqual([x["follow_up_question"] for x in m], ["", ""])


class SummarizeGapsTest(unittest.TestCase):
    def test_counts_and_lists(self):
        requirements = REQUIREMENTS + [{"text": "Docker"}, {"text": "SQL"}, {"text": "Git"}]
        m = _build_mapping(RequirementMappingResult(mappings=[
            item(1), item(2, "partial", follow_up="Which status codes?"),
            item(3, "not_covered", (), "Used Docker?"), item(4, "not_covered", ()),
        ]), requirements, [pair(1)])
        gaps = summarize_gaps(m)
        self.assertEqual(gaps["counts"], {"demonstrated": 1, "partial": 1, "not_covered": 2, "not_mapped": 1})
        self.assertEqual(gaps["partial"], [
            {"requirement_id": 2, "text": "REST API design", "follow_up_question": "Which status codes?"},
        ])
        self.assertEqual(gaps["not_covered"], [
            {"requirement_id": 3, "text": "Docker", "follow_up_question": "Used Docker?"},
            {"requirement_id": 4, "text": "SQL", "follow_up_question": ""},
        ])

    def test_empty_mapping(self):
        self.assertEqual(summarize_gaps([]), {
            "counts": {"demonstrated": 0, "partial": 0, "not_covered": 0, "not_mapped": 0},
            "not_covered": [], "partial": [],
        })


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

    def test_system_prompt_asks_for_follow_up(self):
        self.assertIn("follow-up question", SYSTEM_PROMPT)
        self.assertIn("Leave it empty for demonstrated", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
