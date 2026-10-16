"""Overall interview score formula. Run from backend/: python -m unittest tests.test_interview_evaluation"""

import unittest
from unittest.mock import patch

from app.services.interview_evaluation import band, overall_score, summarize_interview


def ev(pair_id, percent, status="evaluated"):
    return {"pair_id": pair_id, "status": status, "percent": percent, "justification": "Ok."}


def mapping(coverage, status="mapped"):
    return {"status": status, "coverage": coverage}


class OverallScoreTest(unittest.TestCase):
    def test_weighted_answers_and_coverage(self):
        evals = [ev(1, 100), ev(2, 50)]  # answers 75
        maps = [mapping("demonstrated"), mapping("partial"), mapping("not_covered"), mapping("demonstrated")]  # 62.5
        result = overall_score(evals, maps)
        self.assertEqual(result["answer_score"], 75)
        self.assertEqual(result["coverage_score"], 62)  # round(62.5) -> 62 (banker's rounding)
        self.assertEqual(result["score"], round(0.6 * 75 + 0.4 * 62))
        self.assertEqual(result["band"], "moderate")

    def test_unanswered_counts_as_zero(self):
        result = overall_score([ev(1, 100), ev(2, 0, "not_answered")], [])
        self.assertEqual(result["answer_score"], 50)

    def test_not_evaluated_is_skipped(self):
        result = overall_score([ev(1, 80), ev(2, None, "not_evaluated")], [])
        self.assertEqual(result["answer_score"], 80)

    def test_no_requirements_uses_answers_only(self):
        result = overall_score([ev(1, 80)], [])
        self.assertIsNone(result["coverage_score"])
        self.assertEqual(result["score"], 80)
        self.assertEqual(result["band"], "strong")

    def test_not_mapped_requirements_are_skipped(self):
        result = overall_score([ev(1, 100)], [mapping("demonstrated"), mapping(None, "not_mapped")])
        self.assertEqual(result["coverage_score"], 100)

    def test_nothing_evaluated_has_no_score(self):
        result = overall_score([ev(1, None, "not_evaluated")], [mapping("demonstrated")])
        self.assertIsNone(result["score"])
        self.assertIsNone(result["band"])

    def test_band_edges(self):
        self.assertEqual(band(49), "weak")
        self.assertEqual(band(50), "moderate")
        self.assertEqual(band(74), "moderate")
        self.assertEqual(band(75), "strong")

    def test_no_score_skips_llm(self):
        overall = {"score": None, "answer_score": None, "coverage_score": None, "band": None}
        with patch("app.services.interview_evaluation.get_llm") as get_llm:
            summary = summarize_interview(overall, {}, [], "Dev", 1)
        get_llm.assert_not_called()
        self.assertIn("no overall evaluation", summary)


if __name__ == "__main__":
    unittest.main()
