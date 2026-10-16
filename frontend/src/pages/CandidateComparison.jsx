import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { reportUrl } from "../api/candidates";
import { getComparison } from "../api/jobs";
import { Alert, Badge, Button, Card, PageHeader, Spinner, Table } from "../components/ui";

const BAND = { strong: ["green", "Strong"], moderate: ["yellow", "Moderate"], weak: ["red", "Weak"] };
const RECOMMENDATION = {
  recommend: ["green", "Recommend"],
  consider: ["yellow", "Consider with reservations"],
  do_not_recommend: ["red", "Do not recommend"],
};
const DECISION = { selected: ["green", "Selected"], not_selected: ["red", "Not selected"] };
const STATUS = { met: ["green", "Met"], partial: ["yellow", "Partial"], unmet: ["red", "Unmet"] };
const SHOW_OPTIONS = [
  { value: "3", label: "Top 3" },
  { value: "5", label: "Top 5" },
  { value: "all", label: "All" },
];

const assessmentPath = (c) =>
  `/candidates/${c.candidate_id}/assessment${c.interview_id ? `?interview=${c.interview_id}` : ""}`;

function StatusBadge({ map, value }) {
  if (!value) return <span className="text-gray-400">—</span>;
  const [color, label] = map[value] ?? ["gray", value];
  return <Badge color={color}>{label}</Badge>;
}

const score = (value) => (value != null ? <span className="font-semibold text-gray-900">{value}</span> : "—");

// Interviewer only (8.6.2): assessed candidates of one job side by side (stored data, no LLM)
export default function CandidateComparison() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null); // { status, message }
  const [show, setShow] = useState("all");

  useEffect(() => {
    getComparison(id)
      .then(setData)
      .catch((err) => setError({ status: err.status, message: err.message }));
  }, [id]);

  const header = (
    <PageHeader
      title={data ? `Candidate comparison — ${data.job_title}` : "Candidate comparison"}
      subtitle="Candidates with a completed assessment, best final score first."
      actions={
        <Button variant="secondary" onClick={() => navigate(`/jobs/${id}`)}>
          Back to job
        </Button>
      }
    />
  );

  if (error) {
    return (
      <div>
        {header}
        <Alert type="error">{error.status === 404 ? "Job not found." : error.message}</Alert>
      </div>
    );
  }

  if (!data) return <Spinner />;

  const { candidates, requirements } = data;

  if (candidates.length < 2) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <Card>
          <p className="text-sm text-gray-600">
            At least two candidates need a completed assessment to compare. Assessed so far: {candidates.length}.
          </p>
          {candidates.length === 1 && (
            <p className="mt-2 text-sm">
              <Link to={assessmentPath(candidates[0])} className="text-blue-600 hover:underline">
                Open the assessment of {candidates[0].name || "the candidate"}
              </Link>
            </p>
          )}
        </Card>
      </div>
    );
  }

  const summaryColumns = [
    { key: "rank", label: "#" },
    {
      key: "name",
      label: "Candidate",
      render: (c) => (
        <div className="flex flex-col items-start gap-1">
          <span className="font-medium text-gray-900">{c.name || "—"}</span>
          {c.outdated && <Badge color="yellow">Outdated</Badge>}
        </div>
      ),
    },
    {
      key: "final",
      label: "Final score",
      render: (c) => (
        <div className="flex items-center gap-2">
          {score(c.final)}
          <StatusBadge map={BAND} value={c.band} />
        </div>
      ),
    },
    { key: "recommendation", label: "Recommendation", render: (c) => <StatusBadge map={RECOMMENDATION} value={c.recommendation} /> },
    { key: "cv", label: "CV score", render: (c) => score(c.cv_score) },
    { key: "interview", label: "Interview score", render: (c) => score(c.interview_score) },
    {
      key: "requirements",
      label: "Met / Partial / Unmet",
      render: (c) => `${c.met} / ${c.partial} / ${c.unmet}`,
    },
    {
      key: "findings",
      label: "Strengths / Weaknesses / Gaps",
      render: (c) => `${c.strengths} / ${c.weaknesses} / ${c.gaps}`,
    },
    {
      key: "conflicts",
      label: "Conflicts",
      render: (c) => (c.conflicts > 0 ? <Badge color="red">{c.conflicts}</Badge> : "—"),
    },
    { key: "decision", label: "Decision", render: (c) => <StatusBadge map={DECISION} value={c.decision} /> },
    {
      key: "actions",
      label: "",
      render: (c) => (
        <div className="flex justify-end gap-2">
          <Button variant="secondary" className="px-3 py-1" onClick={() => navigate(assessmentPath(c))}>
            Assessment
          </Button>
          <Button
            variant="secondary"
            className="px-3 py-1"
            onClick={() => window.open(reportUrl(c.candidate_id), "_blank")}
          >
            Report
          </Button>
        </div>
      ),
    },
  ];

  const shown = show === "all" ? candidates : candidates.slice(0, Number(show));
  const matrixColumns = [
    { key: "text", label: "Requirement", render: (r) => <span className="text-gray-900">{r.text}</span> },
    ...shown.map((c) => ({
      key: `c-${c.candidate_id}`,
      label: (
        <span>
          {c.name || "—"}
          <span className="block text-xs font-normal text-gray-500">Final {c.final ?? "—"}</span>
        </span>
      ),
      render: (r) => <StatusBadge map={STATUS} value={c.statuses[r.id]} />,
    })),
  ];

  return (
    <div className="flex flex-col gap-6">
      {header}

      <Card title="Summary">
        <Table columns={summaryColumns} data={candidates.map((c, i) => ({ ...c, id: c.candidate_id, rank: i + 1 }))} />
      </Card>

      <Card
        title="Requirements"
        actions={
          <div className="flex items-center gap-2">
            <label htmlFor="show" className="text-sm text-gray-600">
              Show
            </label>
            <select
              id="show"
              value={show}
              onChange={(e) => setShow(e.target.value)}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {SHOW_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        }
      >
        <Table columns={matrixColumns} data={requirements} emptyMessage="No job requirements." />
      </Card>
    </div>
  );
}
