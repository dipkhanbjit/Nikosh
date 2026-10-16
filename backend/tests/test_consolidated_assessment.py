"""Score formula and requirement combination of the consolidated assessment (no DB, no LLM).
Run from backend/: python -m unittest tests.test_consolidated_assessment"""

import unittest

from app.schemas.candidate_assessment import (
    AssessmentItem,
    AssessmentRecommendation,
    ConsolidatedAssessmentResult,
)
from app.services.consolidated_assessment import (
    attach_citations,
    build_citations,
    clean_result,
    combine_requirement,
    combine_requirements,
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
        self.refs = set(build_citations(self.rows, {"experience": {}}, pairs))

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


SCORES = {"experience": {"score": 70, "justification": "Four years as a backend developer.",
                         "evidence": ["Backend developer, 2021-2025"]}}
PAIRS = [
    {"id": 2, "answered": True, "question": "Tell me about Python.", "answer": "x" * 300,
     "start_s": 12.5, "end_s": 40.0, "question_turns": [3], "answer_turns": [4, 5]},
    {"id": 5, "answered": False, "question": "Any questions?", "answer": "",
     "start_s": 90.0, "end_s": 92.0, "question_turns": [9], "answer_turns": []},
]


class CitationsTest(unittest.TestCase):
    def setUp(self):
        self.citations = build_citations(combine_requirements(SCREENING, MAPPING), SCORES, PAIRS)

    def test_cv_requirement(self):
        self.assertEqual(self.citations["CV-R1"], {
            "type": "cv_requirement", "ref": "CV-R1", "requirement_id": 1, "text": "Python",
            "rating": "met", "quote": "5 years of Python"})
        self.assertNotIn("CV-R3", self.citations)  # no CV evidence text

    def test_cv_dimension(self):
        self.assertEqual(self.citations["CV-D:experience"], {
            "type": "cv_dimension", "ref": "CV-D:experience", "dimension": "experience", "score": 70,
            "justification": "Four years as a backend developer.", "evidence": ["Backend developer, 2021-2025"]})

    def test_interview_answer(self):
        c = self.citations["P2"]
        self.assertEqual((c["type"], c["pair_id"], c["question"]), ("interview_answer", 2, "Tell me about Python."))
        self.assertEqual((c["start_s"], c["end_s"]), (12.5, 40.0))
        self.assertEqual((c["question_turns"], c["answer_turns"]), ([3], [4, 5]))
        self.assertEqual(c["answer_excerpt"], "x" * 200 + "...")

    def test_unanswered_pair_not_citable(self):
        self.assertNotIn("P5", self.citations)

    def test_attach_and_unsupported_flag(self):
        result = ConsolidatedAssessmentResult(
            strengths=[AssessmentItem(text="Python", requirement_ids=[1], evidence_refs=["CV-R1", "P2"])],
            weaknesses=[AssessmentItem(text="Unclear", evidence_refs=["P5", "P99"])],  # none valid
            gaps=[AssessmentItem(text="Docker", requirement_ids=[2])],  # no refs at all
            recommendation=AssessmentRecommendation(text="Consider.", evidence_refs=["X1"]),
        )
        findings = clean_result(result, {1, 2, 3}, set(self.citations))
        attach_citations(findings, self.citations)

        strength = findings["strengths"][0]
        self.assertFalse(strength["unsupported"])
        self.assertEqual([c["ref"] for c in strength["citations"]], ["CV-R1", "P2"])
        for item in (findings["weaknesses"][0], findings["gaps"][0], findings["recommendation"]):
            self.assertTrue(item["unsupported"])  # kept, but marked
            self.assertEqual(item["citations"], [])
        self.assertEqual(findings["weaknesses"][0]["text"], "Unclear")


if __name__ == "__main__":
    unittest.main()
