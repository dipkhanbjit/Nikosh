"""Standalone HTML assessment report (8.6.1): built from stored data only, no LLM.
The browser prints it or saves it as PDF (print stylesheet inline)."""

import re
from datetime import datetime, timedelta, timezone
from html import escape

DHAKA = timezone(timedelta(hours=6), "Asia/Dhaka")  # Bangladesh has no daylight saving
MAX_QUESTION_CHARS = 160

BAND = {"strong": "Strong", "moderate": "Moderate", "weak": "Weak"}
RECOMMENDATION = {"recommend": "Recommend", "consider": "Consider with reservations",
                  "do_not_recommend": "Do not recommend"}
RATING = {"met": "Met", "partial": "Partial", "unmet": "Unmet"}
COVERAGE = {"demonstrated": "Demonstrated", "partial": "Partial", "not_covered": "Not covered"}
BASIS = {"both": "CV + interview", "cv_only": "CV only"}
VERDICT = {"supported": "Supported", "contradicted": "Contradicted", "not_verifiable": "Not verifiable"}
DIMENSION = {"technical_skills": "Technical Skills", "experience": "Experience",
             "qualifications": "Qualifications", "cv_jd_match": "CV–JD Match"}

CONFLICT = '<span class="flag">Conflict</span>'
DISCLAIMER = ("This report was generated with AI assistance from the CV and interview data. It supports, "
              "but does not replace, the interviewer's judgement; the final hiring decision is the interviewer's.")

STYLE = """
body { font-family: Arial, Helvetica, sans-serif; color: #111827; margin: 0; background: #fff; }
main { max-width: 900px; margin: 0 auto; padding: 32px 24px; }
h1 { font-size: 22px; margin: 0 0 16px; }
h2 { font-size: 16px; margin: 28px 0 10px; padding-bottom: 4px; border-bottom: 1px solid #d1d5db; }
dl { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 0; }
dt { font-size: 11px; color: #6b7280; }
dd { margin: 2px 0 0; font-size: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #f3f4f6; }
ul { margin: 0; padding-left: 20px; font-size: 14px; }
li { margin-bottom: 6px; }
p { font-size: 14px; line-height: 1.5; }
.scores { display: flex; gap: 32px; align-items: flex-end; flex-wrap: wrap; }
.big { font-size: 30px; font-weight: bold; }
.mid { font-size: 20px; font-weight: bold; }
.muted { color: #6b7280; font-size: 12px; }
.cite { color: #4b5563; font-size: 12px; }
.flag { color: #b91c1c; font-weight: bold; }
.note { background: #fefce8; border: 1px solid #fde68a; padding: 8px 12px; font-size: 13px; }
.disclaimer { margin-top: 32px; border-top: 1px solid #d1d5db; padding-top: 12px; font-size: 12px; color: #4b5563; }
@media print {
  main { padding: 0; max-width: none; }
  h2 { break-after: avoid; }
  tr, li { break-inside: avoid; }
  @page { size: A4; margin: 15mm; }
}
"""


def _e(value) -> str:
    return escape("" if value is None else str(value))


def _label(mapping: dict, value) -> str:
    return mapping.get(value, value) if value else "—"


def _clock(seconds) -> str:
    total = max(0, int(seconds or 0))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _short(text, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def format_dhaka(value: datetime | None) -> str:
    return value.astimezone(DHAKA).strftime("%d %b %Y, %I:%M %p") if value else "—"


def report_filename(candidate_name: str | None, generated_at: datetime) -> str:
    """ASCII-only download name, e.g. assessment-jane-doe-2026-10-16.html."""
    slug = re.sub(r"[^a-z0-9]+", "-", (candidate_name or "candidate").lower()).strip("-") or "candidate"
    return f"assessment-{slug}-{generated_at.astimezone(DHAKA):%Y-%m-%d}.html"


def citation_label(citation: dict) -> str:
    if citation.get("type") == "cv_requirement":
        return f"CV · R{citation.get('requirement_id')}"
    if citation.get("type") == "cv_dimension":
        name = DIMENSION.get(citation.get("dimension"), citation.get("dimension"))
        score = citation.get("score")
        return f"CV score · {name} {score if score is not None else '—'}"
    return f"Q{citation.get('pair_id')} · {_clock(citation.get('start_s'))}–{_clock(citation.get('end_s'))}"


def _finding(item: dict) -> str:
    cites = " ".join(f"[{_e(citation_label(c))}]" for c in item.get("citations") or [])
    flag = ' <span class="flag">(Unsupported)</span>' if item.get("unsupported") else ""
    cites_html = f' <span class="cite">{cites}</span>' if cites else ""
    return f"{_e(item.get('text'))}{flag}{cites_html}"


def _findings_section(title: str, items: list | None) -> str:
    if not items:
        body = "<p>None identified.</p>"
    else:
        body = "<ul>" + "".join(f"<li>{_finding(i)}</li>" for i in items) + "</ul>"
    return f"<h2>{_e(title)}</h2>{body}"


def _summary(score: dict, recommendation: dict | None) -> str:
    weights = score.get("weights") or {}
    rec = f"<p>{_finding(recommendation)}</p>" if recommendation and recommendation.get("text") else ""
    return (
        "<h2>Summary</h2><div class=\"scores\">"
        f"<div><div class=\"muted\">Final score</div><div class=\"big\">{_e(score.get('final'))}/100</div></div>"
        f"<div><div class=\"muted\">Band</div><div class=\"mid\">{_e(_label(BAND, score.get('band')))}</div></div>"
        f"<div><div class=\"muted\">Recommendation</div>"
        f"<div class=\"mid\">{_e(_label(RECOMMENDATION, score.get('recommendation')))}</div></div>"
        f"<div><div class=\"muted\">CV score (weight {round((weights.get('cv') or 0) * 100)}%)</div>"
        f"<div class=\"mid\">{_e(score.get('cv'))}/100</div></div>"
        f"<div><div class=\"muted\">Interview score (weight {round((weights.get('interview') or 0) * 100)}%)</div>"
        f"<div class=\"mid\">{_e(score.get('interview'))}/100</div></div>"
        f"</div>{rec}"
    )


def _requirements(rows: list | None) -> str:
    if not rows:
        return "<h2>Requirements</h2><p>No job requirements.</p>"
    body = "".join(
        "<tr>"
        f"<td>{_e(r.get('text'))}</td>"
        f"<td>{_e(_label(RATING, r.get('cv_rating')))}</td>"
        f"<td>{_e(_label(COVERAGE, r.get('interview_coverage')))}</td>"
        f"<td>{_e(_label(RATING, r.get('final_status')))}</td>"
        f"<td>{_e(_label(BASIS, r.get('basis')))}</td>"
        f"<td>{CONFLICT if r.get('conflict') else '—'}</td>"
        "</tr>"
        for r in rows
    )
    return ("<h2>Requirements</h2><table><thead><tr><th>Requirement</th><th>CV rating</th>"
            "<th>Interview coverage</th><th>Final status</th><th>Basis</th><th>Conflict</th></tr></thead>"
            f"<tbody>{body}</tbody></table>")


def _qa_summary(pairs: list | None, evaluations: list | None) -> str:
    if not pairs:
        return "<h2>Interview Q&amp;A summary</h2><p>No interview questions recorded.</p>"
    by_pair = {e.get("pair_id"): e for e in evaluations or []}
    rows = []
    for p in pairs:
        ev = by_pair.get(p.get("id")) or {}
        evaluated = ev.get("status") == "evaluated"
        percent = f"{ev.get('percent')}%" if evaluated and ev.get("percent") is not None else "—"
        verdict = _label(VERDICT, ev.get("accuracy_verdict")) if evaluated else "—"
        rows.append(
            "<tr>"
            f"<td>Q{_e(p.get('id'))}</td>"
            f"<td>{'Follow-up' if p.get('type') == 'follow_up' else 'Main'}</td>"
            f"<td>{_clock(p.get('start_s'))}–{_clock(p.get('end_s'))}</td>"
            f"<td>{_e(_short(p.get('question'), MAX_QUESTION_CHARS))}</td>"
            f"<td>{'Yes' if p.get('answered') else 'No'}</td>"
            f"<td>{_e(percent)}</td>"
            f"<td>{_e(verdict)}</td>"
            "</tr>"
        )
    return ("<h2>Interview Q&amp;A summary</h2><table><thead><tr><th>No.</th><th>Type</th><th>Time</th>"
            "<th>Question</th><th>Answered</th><th>Score</th><th>Accuracy</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


def render_report(*, candidate_name: str | None, job_title: str | None, interview_date: datetime | None,
                  generated_at: datetime, score: dict, requirements: list | None, findings: dict | None,
                  pairs: list | None, evaluations: list | None, outdated: bool = False,
                  print_on_load: bool = False) -> str:
    """The whole report as one HTML document (inline CSS, no external assets)."""
    findings = findings or {}
    name = candidate_name or "Unknown candidate"
    outdated_note = (
        '<p class="note">The interview was re-analysed after this assessment. The scores and findings may not '
        "match the current interview analysis shown in the Q&amp;A summary.</p>" if outdated else ""
    )
    script = "<script>window.addEventListener('load', () => window.print());</script>" if print_on_load else ""
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>Assessment report – {_e(name)}</title><style>{STYLE}</style></head><body><main>"
        "<h1>Candidate Assessment Report</h1><dl>"
        f"<div><dt>Candidate</dt><dd>{_e(name)}</dd></div>"
        f"<div><dt>Job</dt><dd>{_e(job_title or '—')}</dd></div>"
        f"<div><dt>Interview date</dt><dd>{_e(format_dhaka(interview_date))}</dd></div>"
        f"<div><dt>Generated</dt><dd>{_e(format_dhaka(generated_at))}</dd></div>"
        f"</dl>{outdated_note}"
        f"{_summary(score or {}, findings.get('recommendation'))}"
        f"{_requirements(requirements)}"
        f"{_findings_section('Strengths', findings.get('strengths'))}"
        f"{_findings_section('Weaknesses', findings.get('weaknesses'))}"
        f"{_findings_section('Gaps', findings.get('gaps'))}"
        f"{_qa_summary(pairs, evaluations)}"
        f"<p class=\"disclaimer\">{_e(DISCLAIMER)}</p>"
        f"</main>{script}</body></html>"
    )
