"""Scheduling assistant rules (no Gemini). Run from backend/: python -m unittest tests.test_schedule_planner"""

import unittest
from datetime import datetime, time
from types import SimpleNamespace

from app.services.ics import DHAKA
from app.services.schedule_planner import (
    CandidateRequest,
    PlanQuestion,
    Rules,
    ScheduleIntent,
    build_plan,
    match_name,
    pick_email,
)

RULES = Rules(frozenset({0, 1, 2, 3, 4}), time(9, 0), time(18, 0))
NOW = datetime(2026, 10, 14, 8, 0, tzinfo=DHAKA)  # Wednesday


def person(cid, name, email=None, source="form", cv_email=None):
    return SimpleNamespace(id=cid, full_name=name, email=email, source=source, profile={"email": cv_email})


RAHIM = person(1, "Rahim Uddin", "rahim@example.com")
KARIM = person(2, "Karim Ahmed", "karim@example.com")
RAHIMA = person(3, "Rahima Khan", "rahima@example.com")
SHORTLIST = [RAHIM, KARIM, RAHIMA]  # rank order


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=DHAKA)


def plan(shortlist=SHORTLIST, active=(), busy=(), **fields):
    fields.setdefault("selection", "all")
    return build_plan(ScheduleIntent(**fields), shortlist, set(active), list(busy), NOW, RULES)


def starts(result):
    return [(item["name"], item["start"]) for item in result["items"]]


class NameMatchingTest(unittest.TestCase):
    def test_exact_name_wins_over_prefix(self):
        self.assertIs(match_name("rahim uddin", SHORTLIST), RAHIM)

    def test_unique_first_name(self):
        self.assertIs(match_name("Karim", SHORTLIST), KARIM)

    def test_ambiguous_name_asks(self):
        with self.assertRaises(PlanQuestion) as ctx:
            match_name("Rahi", SHORTLIST)
        self.assertIn("Which one", str(ctx.exception))

    def test_unknown_name_asks(self):
        with self.assertRaises(PlanQuestion):
            match_name("Jamal", SHORTLIST)


class EmailOrderTest(unittest.TestCase):
    def test_chat_email_first(self):
        self.assertEqual(pick_email(RAHIM, " New@Example.com "), ("new@example.com", "chat"))

    def test_form_email_before_cv(self):
        candidate = person(9, "A", "form@example.com", "form", "cv@example.com")
        self.assertEqual(pick_email(candidate), ("form@example.com", "form"))

    def test_cv_email_for_upload(self):
        candidate = person(9, "A", "stored@example.com", "upload", "cv@example.com")
        self.assertEqual(pick_email(candidate), ("cv@example.com", "cv"))

    def test_no_email(self):
        self.assertEqual(pick_email(person(9, "A", None, "upload")), (None, None))


class SlotAssignmentTest(unittest.TestCase):
    def test_consecutive_slots_with_gap(self):
        result = plan(date="2026-10-15", start_time="10:00", duration_min=30, gap_min=10)
        self.assertIsNone(result["question"])
        self.assertEqual(
            [item["start"] for item in result["items"]],
            [at(15, 10).isoformat(), at(15, 10, 40).isoformat(), at(15, 11, 20).isoformat()],
        )
        self.assertTrue(result["items"][0]["start"].endswith("+06:00"))

    def test_default_duration_and_no_gap(self):
        result = plan(date="2026-10-15", start_time="10:00")
        self.assertEqual(result["items"][1]["start"], at(15, 10, 30).isoformat())
        self.assertEqual(result["items"][0]["duration_min"], 30)

    def test_top_n_uses_rank_order(self):
        result = plan(selection="top_n", top_n=2, date="2026-10-15", start_time="10:00")
        self.assertEqual([item["candidate_id"] for item in result["items"]], [1, 2])

    def test_per_candidate_time_first_others_fill_around(self):
        result = plan(
            date="2026-10-15", start_time="10:00",
            candidates=[CandidateRequest(name="Rahim Uddin", start_time="10:30")],
        )
        self.assertEqual(starts(result), [
            ("Karim Ahmed", at(15, 10).isoformat()),
            ("Rahim Uddin", at(15, 10, 30).isoformat()),
            ("Rahima Khan", at(15, 11).isoformat()),
        ])

    def test_per_candidate_other_day(self):
        result = plan(
            selection="names", names=["Karim"],
            candidates=[CandidateRequest(name="Karim", date="2026-10-19", start_time="11:00")],
        )
        self.assertEqual(starts(result), [("Karim Ahmed", at(19, 11).isoformat())])


class OfficeHoursTest(unittest.TestCase):
    def test_overflow_continues_next_working_day(self):
        result = plan(date="2026-10-15", start_time="17:00", duration_min=30)
        self.assertEqual(result["items"][2]["start"], at(16, 9).isoformat())
        self.assertIn("next working day", result["message"])

    def test_friday_overflow_skips_weekend(self):
        result = plan(date="2026-10-16", start_time="17:30", duration_min=30)
        self.assertEqual(result["items"][1]["start"], at(19, 9).isoformat())

    def test_weekend_date_asks_with_next_working_day(self):
        result = plan(date="2026-10-17", start_time="10:00")
        self.assertIn("not a working day", result["question"])
        self.assertIn("Monday 19 Oct", result["question"])

    def test_start_before_office_hours_asks(self):
        self.assertIn("office hours", plan(date="2026-10-15", start_time="08:00")["question"])

    def test_end_after_office_hours_asks(self):
        result = plan(date="2026-10-15", start_time="17:45", duration_min=30)
        self.assertIn("office hours", result["question"])

    def test_past_time_asks(self):
        self.assertIn("already passed", plan(date="2026-10-13", start_time="10:00")["question"])

    def test_missing_date_or_time_asks(self):
        self.assertIn("date", plan(start_time="10:00")["question"])
        self.assertIn("time", plan(date="2026-10-15")["question"])


class OverlapTest(unittest.TestCase):
    def test_slots_skip_existing_interviews(self):
        result = plan(date="2026-10-15", start_time="10:00", busy=[(at(15, 10), at(15, 10, 30))])
        self.assertEqual(result["items"][0]["start"], at(15, 10, 30).isoformat())
        self.assertIn("moved", result["message"])

    def test_per_candidate_time_overlapping_busy_asks(self):
        result = plan(
            selection="names", names=["Karim"], busy=[(at(15, 11), at(15, 12))],
            candidates=[CandidateRequest(name="Karim", date="2026-10-15", start_time="11:30")],
        )
        self.assertIn("overlaps", result["question"])

    def test_two_per_candidate_times_overlapping_asks(self):
        result = plan(
            selection="names", names=["Karim", "Rahim Uddin"], date="2026-10-15",
            candidates=[CandidateRequest(name="Karim", start_time="11:00"),
                        CandidateRequest(name="Rahim Uddin", start_time="11:15")],
        )
        self.assertIn("overlaps", result["question"])


class SelectionTest(unittest.TestCase):
    def test_already_scheduled_is_skipped(self):
        result = plan(date="2026-10-15", start_time="10:00", active={2})
        self.assertEqual([s["candidate_id"] for s in result["skipped"]], [2])
        self.assertEqual(len(result["items"]), 2)

    def test_no_email_is_skipped_unless_given_in_chat(self):
        no_email = person(4, "Jamal Hossain", None, "upload")
        result = plan(shortlist=[no_email], date="2026-10-15", start_time="10:00")
        self.assertEqual(len(result["skipped"]), 1)
        result = plan(
            shortlist=[no_email], date="2026-10-15", start_time="10:00",
            candidates=[CandidateRequest(name="Jamal", email="jamal@example.com")],
        )
        self.assertEqual(result["items"][0]["email_source"], "chat")

    def test_invalid_chat_email_asks(self):
        result = plan(
            date="2026-10-15", start_time="10:00",
            candidates=[CandidateRequest(name="Karim", email="not-an-email")],
        )
        self.assertIn("not a valid email", result["question"])

    def test_unknown_name_in_selection_asks(self):
        result = plan(selection="names", names=["Jamal"], date="2026-10-15", start_time="10:00")
        self.assertIn("No shortlisted candidate", result["question"])


if __name__ == "__main__":
    unittest.main()
