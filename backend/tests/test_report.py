"""HTML assessment report (no DB, no LLM).
Run from backend/: python -m unittest tests.test_report"""

import unittest
from datetime import datetime, timezone

from app.services.report import DISCLAIMER, citation_label, render_report, report_filename

GENERATED = datetime(2026, 10, 16, 6, 30, tzinfo=timezone.utc)  # 12:30 PM in Dhaka

SCORE = {"final": 68, "cv": 80.0, "interview": 60, "weights": {"cv": 0.4, "interview": 0.6},
         "band": "moderate", "recommendation": "consider"}
REQUIREMENTS = [
    {"requirement_id": 1, "text": "Python", "cv_rating": "met", "interview_coverage": "demonstrated",
     "final_status": "met", "basis": "both", "conflict": False},
    {"requirement_id": 2, "text": "Docker", "cv_rating": "unmet", "interview_coverage": None,
     "final_status": "unmet", "basis": "cv_only", "conflict": True},
]
CV_CITE = {"type": "cv_requirement", "ref": "CV-R1", "requirement_id": 1}
DIM_CITE = {"type": "cv_dimension", "ref": "CV-D:experience", "dimension": "experience", "score": 72}
QA_CITE = {"type": "interview_answer", "ref": "P5", "pair_id": 5, "start_s": 192, "end_s": 245}
FINDINGS = {
    "strengths": [{"text": "Strong Python", "citations": [CV_CITE, QA_CITE], "unsupported": False}],
    "weaknesses": [{"text": "Vague on testing", "citations": [], "unsupported": True}],
    "gaps": [],
    "recommendation": {"text": "Consider for a second round.", "citations": [DIM_CITE], "unsupported": False},
}
PAIRS = [
    {"id": 1, "type": "main", "question": "Tell me about <script>alert(1)</script>", "answered": True,
     "start_s": 10, "end_s": 70},
    {"id": 2, "type": "follow_up", "question": "And Docker?", "answered": False, "start_s": 70, "end_s": 80},
]
EVALUATIONS = [{"pair_id": 1, "status": "evaluated", "percent": 75, "accuracy_verdict": "supported"}]


def render(**overrides) -> str:
    args = dict(candidate_name="Jane Doe", job_title="Backend Engineer", interview_date=GENERATED,
                generated_at=GENERATED, score=SCORE, requirements=REQUIREMENTS, findings=FINDINGS,
                pairs=PAIRS, evaluations=EVALUATIONS)
    args.update(overrides)
    return render_report(**args)


class RenderReportTest(unittest.TestCase):
    def test_all_sections_present(self):
        html = render()
        for heading in ("Candidate Assessment Report", "Summary", "Requirements", "Strengths", "Weaknesses",
                        "Gaps", "Interview Q&amp;A summary"):
            self.assertIn(heading, html)
        self.assertIn("68/100", html)
        self.assertIn("Consider with reservations", html)
        self.assertIn("CV score (weight 40%)", html)
        self.assertIn("Interview score (weight 60%)", html)
        self.assertIn("16 Oct 2026, 12:30 PM", html)  # Asia/Dhaka

    def test_disclaimer(self):
        self.assertIn(DISCLAIMER.replace("'", "&#x27;"), render())

    def test_values_escaped(self):
        html = render(candidate_name="<b>Eve</b>")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<b>Eve</b>", html)

    def test_citations_and_unsupported(self):
        html = render()
        self.assertIn("[CV · R1]", html)
        self.assertIn("[Q5 · 03:12–04:05]", html)
        self.assertIn("[CV score · Experience 72]", html)
        self.assertIn("Vague on testing <span class=\"flag\">(Unsupported)</span>", html)
        self.assertNotIn("Strong Python <span class=\"flag\">", html)

    def test_requirements_and_qa_rows(self):
        html = render()
        self.assertIn("CV + interview", html)
        self.assertIn("CV only", html)
        self.assertIn('<span class="flag">Conflict</span>', html)
        self.assertIn("<td>75%</td><td>Supported</td>", html)
        self.assertIn("<td>Follow-up</td>", html)
        self.assertIn("<td>No</td><td>—</td><td>—</td>", html)  # not answered, not evaluated

    def test_empty_lists(self):
        self.assertIn("<h2>Gaps</h2><p>None identified.</p>", render())
        html = render(pairs=None, requirements=[])
        self.assertIn("No interview questions recorded.", html)
        self.assertIn("No job requirements.", html)

    def test_outdated_note(self):
        self.assertNotIn("re-analysed", render())
        self.assertIn("re-analysed after this assessment", render(outdated=True))

    def test_print_on_load(self):
        self.assertNotIn("window.print", render())
        self.assertIn("window.print", render(print_on_load=True))


class HelpersTest(unittest.TestCase):
    def test_report_filename(self):
        self.assertEqual(report_filename("Jane O'Doe", GENERATED), "assessment-jane-o-doe-2026-10-16.html")
        self.assertEqual(report_filename(None, GENERATED), "assessment-candidate-2026-10-16.html")
        self.assertEqual(report_filename("রহিম", GENERATED), "assessment-candidate-2026-10-16.html")

    def test_citation_label_long_interview(self):
        self.assertEqual(citation_label({"type": "interview_answer", "pair_id": 3, "start_s": 3725, "end_s": 3790}),
                         "Q3 · 1:02:05–1:03:10")


if __name__ == "__main__":
    unittest.main()
