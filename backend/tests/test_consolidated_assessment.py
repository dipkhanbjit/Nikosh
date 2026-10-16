"""Score formula and requirement combination of the consolidated assessment (no DB, no LLM).
Run from backend/: python -m unittest tests.test_consolidated_assessment"""

import unittest

from app.schemas.candidate_assessment import (
    AssessmentItem,
    AssessmentRecommendation,
    ConsolidatedAssessmentResult,
)
from app.services.consolidated_assessment import (
    clean_result,
    combine_requirement,
    combine_requirements,
    evidence_ids,
    final_score,
    requirement_gaps,
)


class FinalScoreTest(unittest.TestCase):
    def test_weighted_40_60(self):
        score = final_score(80, 60)
        self.assertEqual(score["final"], 68)  # 32 + 36
        self.assertEqual(score["weights"], {"cv": 0.4, "interview": 0.6})

    def test_rounding(self):
        self.assertEqual(final_score(72.5, 61)["final"], 66)  # 29 + 36.6 = 65.6

    def test_band_edges(self):
        self.assertEqual(final_score(50, 50)["band"], "moderate")
        self.assertEqual(final_score(49, 49)["band"], "weak")
        self.assertEqual(final_score(75, 75)["band"], "strong")
        self.assertEqual(final_score(74, 74)["band"], "moderate")

    def test_recommendation_follows_band(self):
        self.assertEqual(final_score(90, 90)["recommendation"], "recommend")
        self.assertEqual(final_score(60, 60)["recommendation"], "consider")
        self.assertEqual(final_score(20, 30)["recommendation"], "do_not_recommend")


class CombineRequirementTest(unittest.TestCase):
    # (cv_rating, coverage) -> (final_status, basis, conflict)
    CASES = {
        ("met", "demonstrated"): ("met", "both", False),
        ("met", "partial"): ("partial", "both", True),
        ("met", "not_covered"): ("met", "cv_only", False),
        ("met", None): ("met", "cv_only", False),
        ("partial", "demonstrated"): ("met", "both", False),
        ("partial", "partial"): ("partial", "both", False),
        ("partial", "not_covered"): ("partial", "cv_only", False),
        ("partial", None): ("partial", "cv_only", False),
        ("unmet", "demonstrated"): ("met", "both", True),
        ("unmet", "partial"): ("partial", "both", False),
        ("unmet", "not_covered"): ("unmet", "cv_only", False),
        ("unmet", None): ("unmet", "cv_only", False),
    }

    def test_all_combinations(self):
        for (cv, coverage), (status, basis, conflict) in self.CASES.items():
            with self.subTest(cv=cv, coverage=coverage):
                self.assertEqual(
                    combine_requirement(cv, coverage),
                    {"final_status": status, "basis": basis, "conflict": conflict},
                )


SCREENING = [
    {"id": 1, "text": "Python", "category": "skill", "rating": "met", "evidence": "5 years of Python"},
    {"id": 2, "text": "Docker", "category": "skill", "rating": "partial", "evidence": "Used Docker once"},
    {"id": 3, "text": "AWS", "category": "skill", "rating": "met", "evidence": ""},
]
MAPPING = [
    {"requirement_id": 1, "coverage": "demonstrated", "supporting_pairs": [2], "status": "mapped"},
    {"requirement_id": 2, "coverage": "not_covered", "supporting_pairs": [], "status": "mapped"},
    {"requirement_id": 3, "coverage": "partial", "supporting_pairs": [4], "status": "mapped"},
]


class CombineRequirementsTest(unittest.TestCase):
    def test_rows_in_cv_order_matched_by_id(self):
        rows = combine_requirements(SCREENING, list(reversed(MAPPING)))
        self.assertEqual([r["requirement_id"] for r in rows], [1, 2, 3])
        self.assertEqual([r["final_status"] for r in rows], ["met", "partial", "partial"])
        self.assertEqual(rows[0]["supporting_pairs"], [2])
        self.assertTrue(rows[2]["conflict"])

    def test_missing_mapping_keeps_cv_rating(self):
        rows = combine_requirements(SCREENING, [])
        self.assertEqual([r["final_status"] for r in rows], ["met", "partial", "met"])
        self.assertTrue(all(r["basis"] == "cv_only" and r["interview_coverage"] is None for r in rows))

    def test_gaps_are_partial_or_unmet(self):
        gaps = requirement_gaps(combine_requirements(SCREENING, MAPPING))
        self.assertEqual([g["requirement_id"] for g in gaps], [2, 3])


class CleanResultTest(unittest.TestCase):
    def setUp(self):
        self.rows = combine_requirements(SCREENING, MAPPING)
        pairs = [{"id": 2, "answered": True}, {"id": 4, "answered": True}, {"id": 5, "answered": False}]
        self.refs = evidence_ids(self.rows, {"experience": {}}, pairs)

    def test_evidence_ids(self):
        # CV-R3 has no evidence text, P5 was not answered
        self.assertEqual(self.refs, {"CV-R1", "CV-R2", "CV-D:experience", "P2", "P4"})

    def test_drops_unknown_ids_and_refs(self):
        result = ConsolidatedAssessmentResult(
            strengths=[AssessmentItem(text=" Strong Python ", requirement_ids=[1, 9],
                                      evidence_refs=["CV-R1", "P2", "P99", "CV-R1"])],
            weaknesses=[AssessmentItem(text="  ", requirement_ids=[2])],
            gaps=[AssessmentItem(text=f"Gap {i}", requirement_ids=[2]) for i in range(7)],
            recommendation=AssessmentRecommendation(text="Consider.", evidence_refs=["P4", "X1"]),
        )
        findings = clean_result(result, {r["requirement_id"] for r in self.rows}, self.refs)
        self.assertEqual(findings["strengths"],
                         [{"text": "Strong Python", "requirement_ids": [1], "evidence_refs": ["CV-R1", "P2"]}])
        self.assertEqual(findings["weaknesses"], [])
        self.assertEqual(len(findings["gaps"]), 5)
        self.assertEqual(findings["recommendation"], {"text": "Consider.", "evidence_refs": ["P4"]})


if __name__ == "__main__":
    unittest.main()
