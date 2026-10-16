"""Start/save/status rules of the consolidated assessment.
Run from backend/: python -m unittest tests.test_candidate_assessments"""

import unittest

from app.core.exceptions import AppException
from app.models import Candidate, CandidateAssessment, InterviewAnalysis
from app.services.candidate_assessments import (
    RESULT_FIELDS,
    apply_failure,
    apply_result,
    apply_running,
    check_can_start,
    is_outdated,
    reset_for_run,
)

RESULT = {"score": {"final": 70}, "requirements": [], "findings": {"strengths": []}, "inputs": {"x": 1}}


def candidate(screening="screened", scoring="scored", score=80.0):
    return Candidate(screening_status=screening, scoring_status=scoring, overall_score=score)


def analysis(status="completed", score=70, version=1):
    return InterviewAnalysis(interview_id=1, status=status, version=version, overall={"score": score})


def assessment(status="running", version=1, analysis_version=1):
    return CandidateAssessment(candidate_id=1, status=status, version=version, analysis_version=analysis_version)


def code_of(fn, *args):
    try:
        fn(*args)
    except AppException as exc:
        return exc.code
    return None


class CanStartTest(unittest.TestCase):
    def test_needs_screened_and_scored_cv(self):
        self.assertEqual(code_of(check_can_start, candidate(screening="pending"), analysis(), None), "CANDIDATE_NOT_SCORED")
        self.assertEqual(code_of(check_can_start, candidate(scoring="failed"), analysis(), None), "CANDIDATE_NOT_SCORED")
        self.assertEqual(code_of(check_can_start, candidate(score=None), analysis(), None), "CANDIDATE_NOT_SCORED")

    def test_needs_completed_interview_analysis(self):
        for a in (None, analysis(status="running"), analysis(status="failed"), analysis(score=None)):
            with self.subTest(analysis=a and a.status):
                self.assertEqual(code_of(check_can_start, candidate(), a, None), "INTERVIEW_NOT_ANALYSED")

    def test_not_while_running(self):
        for status in ("pending", "running"):
            self.assertEqual(code_of(check_can_start, candidate(), analysis(), assessment(status)), "ASSESSMENT_RUNNING")

    def test_rerun_allowed(self):
        for status in ("completed", "failed"):
            self.assertIsNone(code_of(check_can_start, candidate(), analysis(), assessment(status)))


class OutdatedTest(unittest.TestCase):
    def test_same_analysis_version(self):
        self.assertFalse(is_outdated(assessment("completed"), analysis(version=1)))

    def test_reanalysed_or_gone(self):
        self.assertTrue(is_outdated(assessment("completed"), analysis(version=2)))
        self.assertTrue(is_outdated(assessment("completed"), analysis(status="running")))
        self.assertTrue(is_outdated(assessment("completed"), None))


class StatusRulesTest(unittest.TestCase):
    def test_reset_for_run(self):
        a = assessment("completed", version=2)
        for field in RESULT_FIELDS:
            setattr(a, field, {"old": 1})
        reset_for_run(a, interview_id=7, analysis_version=3)
        self.assertEqual((a.version, a.status, a.interview_id, a.analysis_version), (3, "pending", 7, 3))
        self.assertTrue(all(getattr(a, f) is None for f in RESULT_FIELDS))

    def test_running_only_from_pending_same_version(self):
        self.assertTrue(apply_running(assessment("pending"), 1))
        self.assertFalse(apply_running(assessment("pending", version=2), 1))
        self.assertFalse(apply_running(None, 1))

    def test_result_saves_only_result_fields(self):
        a = assessment("running")
        self.assertTrue(apply_result(a, 1, RESULT))
        self.assertEqual(a.status, "completed")
        self.assertEqual(a.score, {"final": 70})
        self.assertFalse(hasattr(a, "inputs"))

    def test_old_version_does_not_overwrite(self):
        a = assessment("running", version=2)
        self.assertFalse(apply_result(a, 1, RESULT))
        self.assertIsNone(a.score)

    def test_failure_clears_results(self):
        a = assessment("running")
        a.score = {"final": 1}
        self.assertTrue(apply_failure(a, 1, "boom"))
        self.assertEqual((a.status, a.error, a.score), ("failed", "boom", None))
        self.assertFalse(apply_failure(assessment("completed"), 1, "late"))


if __name__ == "__main__":
    unittest.main()
