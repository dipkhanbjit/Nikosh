"""Hiring decision rules and email (no DB; the MCP email tool is mocked).
Run from backend/: python -m unittest tests.test_decisions"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services.decisions import (
    apply_decision,
    can_decide,
    candidate_view,
    decision_email_html,
    decision_email_text,
    notify_candidate,
)
from app.services.mcp_client import MCPToolError

NOW = datetime(2026, 10, 16, 6, 0, tzinfo=timezone.utc)


def candidate(**fields):
    base = dict(id=7, full_name="Jane Doe", email="dipkhan870+jane@gmail.com", decision=None, decision_note=None,
                decision_message=None, decided_at=None, decided_by=None, decision_notified_at=None,
                decision_email_status=None, decision_email_error=None)
    base.update(fields)
    return SimpleNamespace(**base)


class RulesTest(unittest.TestCase):
    def test_can_decide_needs_completed_interview(self):
        self.assertTrue(can_decide(["cancelled", "completed"]))
        self.assertFalse(can_decide(["scheduled", "no_show"]))
        self.assertFalse(can_decide([]))

    def test_apply_sets_fields(self):
        c = candidate()
        apply_decision(c, "selected", "  Strong backend skills ", 3, NOW)
        self.assertEqual((c.decision, c.decision_note, c.decided_at, c.decided_by),
                         ("selected", "Strong backend skills", NOW, 3))
        apply_decision(c, "selected", "   ", 3, NOW)
        self.assertIsNone(c.decision_note)

    def test_changed_decision_clears_notified_state(self):
        c = candidate(decision="selected", decision_notified_at=NOW, decision_message="Welcome",
                      decision_email_status="sent")
        apply_decision(c, "not_selected", None, 3, NOW)
        self.assertIsNone(c.decision_notified_at)
        self.assertIsNone(c.decision_message)
        self.assertIsNone(c.decision_email_status)

    def test_same_decision_keeps_notified_state(self):
        c = candidate(decision="selected", decision_notified_at=NOW, decision_message="Welcome",
                      decision_email_status="sent")
        apply_decision(c, "selected", "updated note", 3, NOW)
        self.assertEqual((c.decision_notified_at, c.decision_message), (NOW, "Welcome"))

    def test_candidate_sees_only_notified_decision(self):
        self.assertEqual(candidate_view(candidate(decision="selected")), (None, None))
        self.assertEqual(candidate_view(candidate(decision="selected", decision_notified_at=NOW,
                                                  decision_message="Hi", decision_note="internal")),
                         ("selected", "Hi"))
        self.assertEqual(candidate_view(candidate()), (None, None))


class EmailTest(unittest.TestCase):
    def test_selected_and_not_selected_wording(self):
        self.assertIn("you have been selected for the Backend Engineer position",
                      decision_email_html("Jane", "Backend Engineer", "selected", None))
        html = decision_email_html("Jane", "Backend Engineer", "not_selected", None)
        self.assertIn("will not be moving forward", html)
        self.assertNotIn("selected for", html)

    def test_message_escaped_with_line_breaks(self):
        html = decision_email_html("<b>Jane</b>", "Dev", "selected", "<script>x</script>\nSee you soon")
        self.assertIn("Message from the interviewer", html)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;<br>See you soon", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>Jane</b>", html)

    def test_no_message_block_when_empty(self):
        self.assertNotIn("Message from the interviewer", decision_email_html("Jane", "Dev", "selected", "   "))
        self.assertNotIn("Message from the interviewer", decision_email_text("Jane", "Dev", "selected", None))
        self.assertIn("Message from the interviewer:\nThanks", decision_email_text("Jane", "Dev", "selected", "Thanks"))

    def test_no_scores_in_email(self):
        for decision in ("selected", "not_selected"):
            content = decision_email_html("Jane", "Dev", decision, None) + decision_email_text("Jane", "Dev", decision, None)
            self.assertNotIn("score", content.lower())
            self.assertNotIn("recommend", content.lower())


class NotifyTest(unittest.TestCase):
    @patch("app.services.decisions.call_tool")
    def test_sent(self, call_tool):
        c = candidate(decision="selected")
        notify_candidate(c, "Dev", " Welcome aboard ", NOW)
        call_tool.assert_called_once()
        self.assertEqual(call_tool.call_args.kwargs["to"], "dipkhan870+jane@gmail.com")
        self.assertEqual((c.decision_email_status, c.decision_email_error), ("sent", None))
        self.assertEqual((c.decision_message, c.decision_notified_at), ("Welcome aboard", NOW))

    @patch("app.services.decisions.call_tool", side_effect=MCPToolError("Error executing tool send_email: quota"))
    def test_failure_keeps_decision(self, _call_tool):
        c = candidate(decision="not_selected")
        notify_candidate(c, "Dev", None, NOW)
        self.assertEqual(c.decision, "not_selected")
        self.assertEqual(c.decision_email_status, "failed")
        self.assertEqual(c.decision_email_error, "quota")
        self.assertEqual(c.decision_notified_at, NOW)  # still shown on the candidate's home page


if __name__ == "__main__":
    unittest.main()
