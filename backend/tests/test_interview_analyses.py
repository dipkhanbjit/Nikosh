"""Save/status rules of the interview analysis. Run from backend/: python -m unittest tests.test_interview_analyses"""

import unittest

from app.core.exceptions import AppException
from app.models import Interview, InterviewAnalysis
from app.services.interview_analyses import (
    RESULT_FIELDS,
    apply_failure,
    apply_result,
    apply_running,
    check_can_start,
    reset_for_run,
)

RESULT = {
    "pairs": [{"id": 1}], "evaluations": [{"pair_id": 1}], "requirement_mapping": [],
    "gaps": {"counts": {}}, "overall": {"score": 80}, "turns": [{"seq": 1}],
}


def analysis(status="running", version=1):
    return InterviewAnalysis(interview_id=1, status=status, version=version)


def code_of(fn, *args):
    try:
        fn(*args)
    except AppException as exc:
        return exc.code
    return None


class CanStartTest(unittest.TestCase):
    def test_only_completed_interviews(self):
        self.assertEqual(code_of(check_can_start, Interview(status="in_progress"), 5, None), "INTERVIEW_NOT_COMPLETED")

    def test_needs_transcript(self):
        self.assertEqual(code_of(check_can_start, Interview(status="completed"), 0, None), "NO_TRANSCRIPT")

    def test_not_while_running(self):
        for status in ("pending", "running"):
            self.assertEqual(
                code_of(check_can_start, Interview(status="completed"), 5, analysis(status)), "ANALYSIS_RUNNING"
            )

    def test_rerun_allowed_after_end(self):
        for status in ("completed", "failed"):
            self.assertIsNone(code_of(check_can_start, Interview(status="completed"), 5, analysis(status)))


class StatusTest(unittest.TestCase):
    def test_reset_clears_results_and_bumps_version(self):
        a = analysis("completed", version=2)
        for field in RESULT_FIELDS:
            setattr(a, field, RESULT[field])
        a.error = "old"
        reset_for_run(a)
        self.assertEqual((a.status, a.version, a.error), ("pending", 3, None))
        self.assertTrue(all(getattr(a, f) is None for f in RESULT_FIELDS))

    def test_running_only_from_pending_same_version(self):
        self.assertTrue(apply_running(analysis("pending"), 1))
        self.assertFalse(apply_running(analysis("pending", version=2), 1))
        self.assertFalse(apply_running(analysis("failed"), 1))
        self.assertFalse(apply_running(None, 1))

    def test_result_saves_all_fields(self):
        a = analysis()
        self.assertTrue(apply_result(a, 1, RESULT))
        self.assertEqual(a.status, "completed")
        self.assertIsNotNone(a.finished_at)
        for field in RESULT_FIELDS:
            self.assertEqual(getattr(a, field), RESULT[field])

    def test_result_skipped_for_replaced_run(self):
        a = analysis(version=2)
        self.assertFalse(apply_result(a, 1, RESULT))
        self.assertIsNone(a.pairs)
        self.assertEqual(a.status, "running")

    def test_failure_has_no_results(self):
        a = analysis()
        a.pairs = [{"id": 1}]
        self.assertTrue(apply_failure(a, 1, "AI pairing failed (TimeoutError)"))
        self.assertEqual((a.status, a.error), ("failed", "AI pairing failed (TimeoutError)"))
        self.assertTrue(all(getattr(a, f) is None for f in RESULT_FIELDS))

    def test_failure_ignored_for_replaced_or_finished_run(self):
        self.assertFalse(apply_failure(analysis(version=2), 1, "x"))
        self.assertFalse(apply_failure(analysis("completed"), 1, "x"))


if __name__ == "__main__":
    unittest.main()
