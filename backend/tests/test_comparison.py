"""Candidate comparison of one job (no DB, no LLM).
Run from backend/: python -m unittest tests.test_comparison"""

import unittest

from app.services.comparison import build_comparison

JOB_REQUIREMENTS = [{"text": "Python", "category": "skill"}, {"text": "Docker", "category": "tool"},
                    {"text": "3 years", "category": "experience"}]


def assessed(candidate_id, name, final, statuses=("met", "partial", "unmet"), status="completed", **extra):
    return {
        "candidate_id": candidate_id,
        "name": name,
        "interview_id": 100 + candidate_id,
        "status": status,
        "score": {"final": final, "band": "moderate", "recommendation": "consider", "cv": 70.0, "interview": 60},
        "requirements": [{"requirement_id": i, "final_status": s, "conflict": i == 2}
                         for i, s in enumerate(statuses, start=1)],
        "findings": {
            "strengths": [{"text": "a", "unsupported": False}, {"text": "b", "unsupported": True}],
            "weaknesses": [{"text": "c", "unsupported": True}],
            "gaps": [],
            "recommendation": {"text": "r", "unsupported": True},  # not counted
        },
        **extra,
    }


class BuildComparisonTest(unittest.TestCase):
    def test_sorted_by_final_score_then_name(self):
        rows = [assessed(1, "Zara", 60), assessed(2, "bob", 75), assessed(3, "Alice", 60)]
        names = [c["name"] for c in build_comparison(JOB_REQUIREMENTS, rows)["candidates"]]
        self.assertEqual(names, ["bob", "Alice", "Zara"])

    def test_missing_final_score_sorts_last(self):
        rows = [assessed(1, "A", None), assessed(2, "B", 10)]
        names = [c["name"] for c in build_comparison(JOB_REQUIREMENTS, rows)["candidates"]]
        self.assertEqual(names, ["B", "A"])

    def test_only_completed_assessments(self):
        rows = [assessed(1, "A", 80), assessed(2, "B", 90, status="failed"), assessed(3, "C", 70, status="running")]
        self.assertEqual([c["candidate_id"] for c in build_comparison([], rows)["candidates"]], [1])

    def test_requirements_numbered_from_one(self):
        reqs = build_comparison(JOB_REQUIREMENTS, [])["requirements"]
        self.assertEqual([r["id"] for r in reqs], [1, 2, 3])
        self.assertEqual(reqs[1], {"id": 2, "text": "Docker", "category": "tool"})

    def test_statuses_and_counts(self):
        row = build_comparison(JOB_REQUIREMENTS, [assessed(1, "A", 80, outdated=True)])["candidates"][0]
        self.assertEqual(row["statuses"], {1: "met", 2: "partial", 3: "unmet"})
        self.assertEqual((row["met"], row["partial"], row["unmet"]), (1, 1, 1))
        self.assertEqual((row["strengths"], row["weaknesses"], row["gaps"]), (2, 1, 0))
        self.assertEqual(row["conflicts"], 1)
        self.assertEqual(row["unsupported"], 2)  # recommendation not counted
        self.assertTrue(row["outdated"])
        self.assertEqual((row["cv_score"], row["interview_score"], row["interview_id"]), (70.0, 60, 101))

    def test_missing_requirement_left_out(self):
        row = build_comparison(JOB_REQUIREMENTS, [assessed(1, "A", 80, statuses=("met",))])["candidates"][0]
        self.assertEqual(row["statuses"], {1: "met"})
        self.assertIsNone(row["statuses"].get(3))

    def test_empty_stored_data(self):
        row = assessed(1, "A", 50)
        row.update(score=None, requirements=None, findings=None)
        out = build_comparison(None, [row])
        self.assertEqual(out["requirements"], [])
        c = out["candidates"][0]
        self.assertIsNone(c["final"])
        self.assertEqual((c["met"], c["strengths"], c["conflicts"], c["unsupported"]), (0, 0, 0, 0))
        self.assertFalse(c["outdated"])

    def test_no_candidates(self):
        self.assertEqual(build_comparison(JOB_REQUIREMENTS, [])["candidates"], [])


if __name__ == "__main__":
    unittest.main()
