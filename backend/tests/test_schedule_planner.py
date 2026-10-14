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
    blocked_reasons,
    build_plan,
    match_name,
    name_slug,
    pick_email,
    recheck_item,
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


def plan(shortlist=SHORTLIST, blocked=None, busy=(), **fields):
    fields.setdefault("selection", "all")
    return build_plan(ScheduleIntent(**fields), shortlist, blocked or {}, list(busy), NOW, RULES)


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
        result = plan(date="2026-10-15", start_time="10:00", blocked={2: "Already scheduled"})
        self.assertEqual([(s["candidate_id"], s["reason"]) for s in result["skipped"]],
                         [(2, "Already scheduled")])
        self.assertEqual(len(result["items"]), 2)

    def test_unscheduled_picks_only_free_candidates(self):
        result = plan(selection="unscheduled", date="2026-10-15", start_time="10:00",
                      blocked={1: "Already interviewed", 3: "Marked as no-show"})
        self.assertEqual([i["candidate_id"] for i in result["items"]], [2])
        self.assertEqual(result["skipped"], [])

    def test_unscheduled_with_nobody_left_replies(self):
        blocked = {1: "Already interviewed", 2: "Already scheduled", 3: "Interview in progress"}
        result = plan(selection="unscheduled", date="2026-10-15", start_time="10:00", blocked=blocked)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["question"], "All shortlisted candidates already have an interview.")

    def test_all_with_everyone_blocked_replies(self):
        blocked = {1: "Already interviewed", 2: "Already scheduled", 3: "Marked as no-show"}
        result = plan(date="2026-10-15", start_time="10:00", blocked=blocked)
        self.assertEqual(result["question"], "All shortlisted candidates already have an interview.")
        self.assertEqual(len(result["skipped"]), 3)

    def test_top_n_skips_blocked_without_filling_up(self):
        result = plan(selection="top_n", top_n=2, date="2026-10-15", start_time="10:00",
                      blocked={1: "Already interviewed"})
        self.assertEqual([i["candidate_id"] for i in result["items"]], [2])
        self.assertEqual([s["candidate_id"] for s in result["skipped"]], [1])


class BlockedReasonsTest(unittest.TestCase):
    def test_reason_per_status(self):
        self.assertEqual(blocked_reasons([(1, "scheduled"), (2, "in_progress"), (3, "completed"), (4, "no_show")]), {
            1: "Already scheduled", 2: "Interview in progress", 3: "Already interviewed", 4: "Marked as no-show",
        })

    def test_cancelled_does_not_block(self):
        self.assertEqual(blocked_reasons([(1, "cancelled")]), {})
        self.assertEqual(blocked_reasons([(1, "cancelled"), (1, "completed")]), {1: "Already interviewed"})

    def test_most_relevant_status_wins(self):
        self.assertEqual(blocked_reasons([(1, "completed"), (1, "scheduled")]), {1: "Already scheduled"})
        self.assertEqual(blocked_reasons([(1, "no_show"), (1, "completed")]), {1: "Already interviewed"})

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


OVERRIDE = "dipkhan870+{name}@gmail.com"


class EmailOverrideTest(unittest.TestCase):
    def test_override_uses_first_name_slug(self):
        self.assertEqual(pick_email(RAHIM, override=OVERRIDE), ("dipkhan870+rahim@gmail.com", "test"))

    def test_override_beats_chat_email(self):
        self.assertEqual(pick_email(KARIM, "real@example.com", OVERRIDE), ("dipkhan870+karim@gmail.com", "test"))

    def test_slug_keeps_letters_and_digits_only(self):
        self.assertEqual(name_slug(person(7, "Md. Abdul Karim")), "md")
        self.assertEqual(name_slug(person(8, "O'Neil Smith")), "oneil")

    def test_slug_fallback_without_name(self):
        self.assertEqual(name_slug(person(9, None)), "candidate9")
        self.assertEqual(name_slug(person(10, "...")), "candidate10")

    def test_empty_override_uses_real_email(self):
        self.assertEqual(pick_email(RAHIM, override=""), ("rahim@example.com", "form"))

    def test_plan_items_use_override(self):
        rules = Rules(RULES.working_days, RULES.office_start, RULES.office_end, OVERRIDE)
        result = build_plan(ScheduleIntent(selection="top_n", top_n=2, date="2026-10-15", start_time="10:00"),
                            SHORTLIST, {}, [], NOW, rules)
        self.assertEqual([(i["email"], i["email_source"]) for i in result["items"]], [
            ("dipkhan870+rahim@gmail.com", "test"), ("dipkhan870+karim@gmail.com", "test"),
        ])


def item(cid=1, start=at(15, 10), minutes=30):
    return {"candidate_id": cid, "name": "x", "email": "x@example.com", "email_source": "form",
            "start": start.isoformat(), "duration_min": minutes}


class RecheckTest(unittest.TestCase):
    def test_still_valid(self):
        self.assertIsNone(recheck_item(item(), {1}, {}, [], NOW))

    def test_no_longer_shortlisted(self):
        self.assertEqual(recheck_item(item(), {2}, {}, [], NOW), "No longer shortlisted")

    def test_already_scheduled(self):
        self.assertEqual(recheck_item(item(), {1}, {1: "Already scheduled"}, [], NOW), "Already scheduled")

    def test_completed_or_no_show_blocks(self):
        for reason in ("Already interviewed", "Marked as no-show"):
            self.assertEqual(recheck_item(item(), {1}, {1: reason}, [], NOW), reason)

    def test_start_in_the_past(self):
        self.assertEqual(recheck_item(item(), {1}, {}, [], at(15, 10)), "Start time has passed")

    def test_slot_taken(self):
        busy = [(at(15, 10, 15), at(15, 10, 45))]
        self.assertEqual(recheck_item(item(), {1}, {}, busy, NOW), "Time slot is no longer free")

    def test_adjacent_slot_is_free(self):
        busy = [(at(15, 9, 30), at(15, 10))]
        self.assertIsNone(recheck_item(item(), {1}, {}, busy, NOW))
