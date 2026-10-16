"""JD Assistant job profile rules (no Gemini, no DB; the LLM and session are mocked).
Run from backend/: python -m unittest tests.test_jd_profile"""

import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from app.schemas.jd import JDDraft, JDReviewRequest, JobProfile
from app.services.deadlines import DHAKA
from app.workflows import jd_generation
from app.workflows.jd_generation import clean_profile, draft, review, save

TODAY = date(2026, 10, 16)


class CleanProfileTest(unittest.TestCase):
    def test_valid_values_pass(self):
        raw = {"department": " Engineering ", "location": "Dhaka", "employment_type": "contract",
               "min_experience_years": 3, "application_deadline": "2026-11-30"}
        self.assertEqual(clean_profile(raw, TODAY), {
            "department": "Engineering", "location": "Dhaka", "employment_type": "contract",
            "min_experience_years": 3, "application_deadline": "2026-11-30",
        })

    def test_nothing_mentioned(self):
        self.assertEqual(clean_profile({}, TODAY), {
            "department": None, "location": None, "employment_type": "full_time",
            "min_experience_years": None, "application_deadline": None,
        })

    def test_blank_text_is_empty(self):
        profile = clean_profile({"department": "  ", "location": ""}, TODAY)
        self.assertIsNone(profile["department"])
        self.assertIsNone(profile["location"])

    def test_long_text_is_cut(self):
        self.assertEqual(len(clean_profile({"location": "x" * 300}, TODAY)["location"]), 100)

    def test_employment_type(self):
        self.assertEqual(clean_profile({"employment_type": "Part-time"}, TODAY)["employment_type"], "part_time")
        self.assertEqual(clean_profile({"employment_type": "freelance"}, TODAY)["employment_type"], "full_time")

    def test_years_range(self):
        for value in (-1, 31, True, "5"):
            self.assertIsNone(clean_profile({"min_experience_years": value}, TODAY)["min_experience_years"])
        self.assertEqual(clean_profile({"min_experience_years": 0}, TODAY)["min_experience_years"], 0)
        self.assertEqual(clean_profile({"min_experience_years": 30}, TODAY)["min_experience_years"], 30)

    def test_deadline(self):
        self.assertIsNone(clean_profile({"application_deadline": "2026-10-15"}, TODAY)["application_deadline"])
        self.assertIsNone(clean_profile({"application_deadline": "next Friday"}, TODAY)["application_deadline"])
        self.assertEqual(clean_profile({"application_deadline": "2026-10-16"}, TODAY)["application_deadline"],
                         "2026-10-16")


class JobProfileSchemaTest(unittest.TestCase):
    def test_rejects_bad_interviewer_values(self):
        for fields in ({"employment_type": "freelance"}, {"min_experience_years": 31},
                       {"min_experience_years": -1}, {"location": "x" * 101}):
            with self.assertRaises(ValidationError):
                JobProfile(**fields)

    def test_review_request_with_profile(self):
        req = JDReviewRequest(action="approve", profile={"application_deadline": "2026-11-30"})
        self.assertEqual(req.profile.application_deadline, date(2026, 11, 30))
        self.assertEqual(req.profile.employment_type, "full_time")


def fake_llm(result: JDDraft):
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = result
    return llm


class DraftNodeTest(unittest.TestCase):
    STATE = {"job_profile": "Title: Backend Engineer", "prompt": "Contract role in Chittagong",
             "context": "[company.md]\nOffice in Dhaka"}

    def run_draft(self, result, **state):
        llm = fake_llm(result)
        with patch.object(jd_generation, "get_llm", return_value=llm), \
                patch.object(jd_generation, "today", return_value=TODAY):
            out = draft({**self.STATE, **state})
        messages = llm.with_structured_output.return_value.invoke.call_args.args[0]
        return out, messages[1].content

    def test_profile_is_cleaned_into_state(self):
        result = JDDraft(description="# JD", requirements=[{"text": "Python"}], location="Chittagong",
                         employment_type="contract", min_experience_years=99, application_deadline="2026-01-01")
        out, prompt = self.run_draft(result)
        self.assertEqual(out["profile"]["location"], "Chittagong")
        self.assertEqual(out["profile"]["employment_type"], "contract")
        self.assertIsNone(out["profile"]["min_experience_years"])
        self.assertIsNone(out["profile"]["application_deadline"])
        self.assertIn("Today's date: 2026-10-16", prompt)
        self.assertNotIn("Current job profile", prompt)

    def test_refine_sends_current_profile(self):
        current = clean_profile({"location": "Dhaka", "min_experience_years": 3}, TODAY)
        result = JDDraft(description="# JD", requirements=[{"text": "Python"}])
        _, prompt = self.run_draft(result, profile=current, feedback="Make it remote",
                                   description="# Old")
        self.assertIn("Current job profile:\ndepartment: not set\nlocation: Dhaka", prompt)
        self.assertIn("min_experience_years: 3", prompt)


class ReviewAndSaveTest(unittest.TestCase):
    def test_review_passes_edited_profile(self):
        edited = {"location": "Remote", "employment_type": "part_time"}
        with patch.object(jd_generation, "interrupt", return_value={"action": "approve", "profile": edited}):
            command = review({"description": "# JD", "requirements": [], "profile": {}})
        self.assertEqual(command.goto, "save")
        self.assertEqual(command.update["profile"], edited)

    def save_job(self, profile):
        job = SimpleNamespace(department="Old", location="Old", employment_type="contract",
                              min_experience_years=9, application_deadline=None)
        db = MagicMock()
        db.get.return_value = job
        session = MagicMock()
        session.return_value.__enter__.return_value = db
        state = {"job_id": 1, "description": "# JD", "requirements": [{"text": "Python"}]}
        if profile is not None:
            state["profile"] = profile
        with patch.object(jd_generation, "SessionLocal", session):
            save(state)
        return job

    def test_save_writes_profile(self):
        job = self.save_job({"department": "Engineering", "location": None, "employment_type": "internship",
                             "min_experience_years": 2, "application_deadline": "2026-11-30"})
        self.assertEqual(job.department, "Engineering")
        self.assertIsNone(job.location)
        self.assertEqual(job.employment_type, "internship")
        self.assertEqual(job.min_experience_years, 2)
        self.assertEqual(job.application_deadline, datetime(2026, 11, 30, 23, 59, 59, tzinfo=DHAKA))
        self.assertEqual(job.status, "approved")

    def test_no_deadline_left_for_posting_default(self):
        job = self.save_job({"employment_type": None})
        self.assertIsNone(job.application_deadline)
        self.assertEqual(job.employment_type, "full_time")

    def test_old_thread_without_profile_keeps_fields(self):
        job = self.save_job(None)
        self.assertEqual(job.department, "Old")
        self.assertEqual(job.employment_type, "contract")


if __name__ == "__main__":
    unittest.main()
