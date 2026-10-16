import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { getAssessment, reportUrl, runAssessment } from "../api/candidates";
import { formatClock, formatDateTime, getInterview } from "../api/interviews";
import HiringDecisionCard from "../components/HiringDecisionCard";
import { Alert, Badge, Button, Card, Modal, PageHeader, Spinner, Table } from "../components/ui";

const ASSESSMENT_STATUS = {
  pending: ["gray", "Pending"],
  running: ["blue", "Running"],
  completed: ["green", "Completed"],
  failed: ["red", "Failed"],
};
const BAND = { strong: ["green", "Strong"], moderate: ["yellow", "Moderate"], weak: ["red", "Weak"] };
const RECOMMENDATION = {
  recommend: ["green", "Recommend"],
  consider: ["yellow", "Consider with reservations"],
  do_not_recommend: ["red", "Do not recommend"],
};
const RATING = { met: ["green", "Met"], partial: ["yellow", "Partial"], unmet: ["red", "Unmet"] };
const COVERAGE = {
  demonstrated: ["green", "Demonstrated"],
  partial: ["yellow", "Partial"],
  not_covered: ["red", "Not covered"],
};
const BASIS = { both: "CV + interview", cv_only: "CV only" };
const DIMENSION = {
  technical_skills: "Technical Skills",
  experience: "Experience",
  qualifications: "Qualifications",
  cv_jd_match: "CV–JD Match",
};
const POLL_MS = 3000;

const isActive = (assessment) => ["pending", "running"].includes(assessment?.status);
const percent = (weight) => `${Math.round((weight ?? 0) * 100)}%`;

function StatusBadge({ map, value }) {
  if (!value) return <span className="text-gray-400">—</span>;
  const [color, label] = map[value] ?? ["gray", value];
  return <Badge color={color}>{label}</Badge>;
}

function Detail({ label, children }) {
  return (
    <div>
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-900">{children}</dd>
    </div>
  );
}

function Figure({ label, value, large = false }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`font-semibold text-gray-900 ${large ? "text-3xl" : "text-xl"}`}>
        {value ?? "—"}
        {value != null && <span className="text-sm font-normal text-gray-500">/100</span>}
      </p>
    </div>
  );
}

// Short label of one citation; interview answers link to the Q&A on the analysis page
function CitationLabel({ citation, interviewId }) {
  if (citation.type === "cv_requirement") return <span>CV · R{citation.requirement_id}</span>;
  if (citation.type === "cv_dimension") {
    return (
      <span>
        CV score · {DIMENSION[citation.dimension] ?? citation.dimension} {citation.score ?? "—"}
      </span>
    );
  }
  const label = `Q${citation.pair_id} · ${formatClock(citation.start_s)}–${formatClock(citation.end_s)}`;
  if (!interviewId) return <span>{label}</span>;
  return (
    <Link to={`/interviews/${interviewId}/analysis#pair-${citation.pair_id}`} className="text-blue-600 hover:underline">
      {label}
    </Link>
  );
}

function CitationDetail({ citation, interviewId }) {
  let body;
  if (citation.type === "cv_requirement") {
    body = (
      <>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-gray-900">{citation.text}</span>
          <StatusBadge map={RATING} value={citation.rating} />
        </div>
        <p className="mt-1 italic text-gray-700">“{citation.quote}”</p>
      </>
    );
  } else if (citation.type === "cv_dimension") {
    body = <p className="text-gray-700">{citation.justification || "No justification recorded."}</p>;
  } else {
    body = (
      <>
        <p className="font-medium text-gray-900">{citation.question}</p>
        <p className="mt-1 text-gray-700">{citation.answer_excerpt}</p>
      </>
    );
  }
  return (
    <div className="rounded-md bg-gray-50 p-3 text-sm">
      <p className="mb-1 text-xs font-medium text-gray-500">
        <CitationLabel citation={citation} interviewId={interviewId} />
      </p>
      {body}
    </div>
  );
}

// One strength / weakness / gap (or the recommendation) with its evidence, collapsed by default
function Finding({ item, interviewId }) {
  const [open, setOpen] = useState(false);
  const citations = item.citations ?? [];

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-start gap-2">
        <p className="text-sm text-gray-900">{item.text}</p>
        {item.unsupported && <Badge>Unsupported</Badge>}
      </div>
      {citations.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
          <span>Evidence:</span>
          {citations.map((c) => (
            <CitationLabel key={c.ref} citation={c} interviewId={interviewId} />
          ))}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="cursor-pointer text-blue-600 hover:underline"
          >
            {open ? "Hide evidence" : "Show evidence"}
          </button>
        </div>
      )}
      {open && (
        <div className="flex flex-col gap-2">
          {citations.map((c) => (
            <CitationDetail key={c.ref} citation={c} interviewId={interviewId} />
          ))}
        </div>
      )}
    </div>
  );
}

function FindingsCard({ title, items, interviewId }) {
  return (
    <Card title={title}>
      {(items ?? []).length === 0 ? (
        <p className="text-sm text-gray-500">None identified.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-gray-100">
          {items.map((item, i) => (
            <li key={i} className="py-3 first:pt-0 last:pb-0">
              <Finding item={item} interviewId={interviewId} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ExportActions({ candidateId }) {
  return (
    <div className="flex gap-2">
      {/* Served as an attachment, so the page stays open */}
      <Button variant="secondary" onClick={() => window.location.assign(reportUrl(candidateId, { download: true }))}>
        Download HTML
      </Button>
      <Button variant="secondary" onClick={() => window.open(reportUrl(candidateId, { print: true }), "_blank")}>
        Print / Save as PDF
      </Button>
    </div>
  );
}

function ScoreCard({ score, recommendation, interviewId, candidateId }) {
  return (
    <Card title="Final score" actions={<ExportActions candidateId={candidateId} />}>
      <div className="flex flex-wrap items-end gap-8">
        <Figure label="Final score" value={score.final} large />
        <div className="flex gap-2 pb-1">
          <StatusBadge map={BAND} value={score.band} />
          <StatusBadge map={RECOMMENDATION} value={score.recommendation} />
        </div>
        <Figure label={`CV score (weight ${percent(score.weights?.cv)})`} value={score.cv} />
        <Figure label={`Interview score (weight ${percent(score.weights?.interview)})`} value={score.interview} />
      </div>
      {recommendation?.text && (
        <div className="mt-4">
          <Finding item={recommendation} interviewId={interviewId} />
        </div>
      )}
    </Card>
  );
}

const REQUIREMENT_COLUMNS = [
  {
    key: "text",
    label: "Requirement",
    render: (r) => (
      <div className="flex flex-col items-start gap-1">
        <span className="text-gray-900">{r.text}</span>
        {r.category && <Badge>{r.category}</Badge>}
      </div>
    ),
  },
  { key: "cv_rating", label: "CV rating", render: (r) => <StatusBadge map={RATING} value={r.cv_rating} /> },
  {
    key: "interview_coverage",
    label: "Interview coverage",
    render: (r) => <StatusBadge map={COVERAGE} value={r.interview_coverage} />,
  },
  { key: "final_status", label: "Final status", render: (r) => <StatusBadge map={RATING} value={r.final_status} /> },
  { key: "basis", label: "Basis", render: (r) => BASIS[r.basis] ?? r.basis },
  { key: "conflict", label: "Conflict", render: (r) => (r.conflict ? <Badge color="red">Conflict</Badge> : "—") },
];

// Interviewer only (8.5.3): run the consolidated assessment and show its result
export default function CandidateAssessment() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [assessment, setAssessment] = useState(undefined); // undefined = loading, null = never run
  const [interview, setInterview] = useState(null);
  const [error, setError] = useState(null); // { status, message }: page cannot load
  const [actionError, setActionError] = useState(null); // { code, message }
  const [starting, setStarting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const interviewId = searchParams.get("interview") || assessment?.interview_id || null;

  const fetchAssessment = useCallback(
    () =>
      getAssessment(id)
        .then(setAssessment)
        .catch((err) => {
          if (err.code === "ASSESSMENT_NOT_FOUND") setAssessment(null);
          else setError({ status: err.status, message: err.message });
        }),
    [id],
  );

  useEffect(() => {
    fetchAssessment();
  }, [fetchAssessment]);

  useEffect(() => {
    if (!interviewId) return;
    getInterview(interviewId)
      .then(setInterview)
      .catch(() => {}); // header details only; the assessment still shows without them
  }, [interviewId]);

  // Poll while the background run is pending/running; a failed poll is retried on the next tick
  const active = isActive(assessment);
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => {
      getAssessment(id).then(setAssessment).catch(() => {});
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [active, id]);

  const start = () => {
    setConfirmOpen(false);
    setActionError(null);
    setStarting(true);
    runAssessment(id)
      .then(setAssessment)
      .catch((err) => {
        setActionError({ code: err.code, message: err.message });
        if (err.code === "ASSESSMENT_RUNNING") fetchAssessment();
      })
      .finally(() => setStarting(false));
  };

  const header = (
    <PageHeader
      title="Consolidated assessment"
      actions={
        <>
          {interviewId && (
            <Button variant="secondary" onClick={() => navigate(`/interviews/${interviewId}/analysis`)}>
              Interview analysis
            </Button>
          )}
          <Button variant="secondary" onClick={() => navigate("/candidates")}>
            Back to candidates
          </Button>
        </>
      }
    />
  );

  if (error) {
    return (
      <div>
        {header}
        <Alert type="error">{error.status === 404 ? "Candidate not found." : error.message}</Alert>
      </div>
    );
  }

  if (assessment === undefined) return <Spinner />;

  const [statusColor, statusLabel] = ASSESSMENT_STATUS[assessment?.status] ?? ["gray", "Not run"];
  const hasResult = assessment?.status === "completed";
  const findings = assessment?.findings ?? {};

  const runButton = !active && (
    <Button
      loading={starting}
      onClick={() => (assessment ? setConfirmOpen(true) : start())}
      variant={assessment ? "secondary" : "primary"}
    >
      {assessment ? "Re-run assessment" : "Run assessment"}
    </Button>
  );

  return (
    <div className="flex flex-col gap-6">
      {header}

      <Card actions={runButton}>
        <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Detail label="Candidate">{interview?.candidate_name || "—"}</Detail>
          <Detail label="Job">{interview?.job_title || "—"}</Detail>
          <Detail label="Interview date">
            {interview ? formatDateTime(interview.started_at || interview.scheduled_at) : "—"}
          </Detail>
          <Detail label="Assessment">
            <Badge color={statusColor}>{statusLabel}</Badge>
            {assessment?.finished_at && (
              <span className="ml-2 text-xs text-gray-500">Last run {formatDateTime(assessment.finished_at)}</span>
            )}
          </Detail>
        </dl>
      </Card>

      {assessment && !hasResult && (
        <p className="text-sm text-gray-500">Export is available after the assessment has completed.</p>
      )}

      {actionError && (
        <Alert type="error">
          {actionError.message}
          {actionError.code === "INTERVIEW_NOT_ANALYSED" && interviewId && (
            <>
              {" "}
              <Link to={`/interviews/${interviewId}/analysis`} className="font-medium underline">
                Go to interview analysis
              </Link>
            </>
          )}
        </Alert>
      )}

      {hasResult && assessment.outdated && (
        <div role="alert" className="rounded-md border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
          The interview was re-analysed after this assessment. Re-run it to update.
        </div>
      )}

      {assessment === null && (
        <Card>
          <p className="text-sm text-gray-600">
            This candidate has not been assessed yet. Click <span className="font-medium">Run assessment</span> to
            combine the CV screening, CV score and interview analysis into one assessment.
          </p>
        </Card>
      )}

      {active && (
        <Card>
          <div className="flex items-center gap-3 text-sm text-gray-600">
            <Spinner size="sm" />
            Building the assessment… this can take a minute.
          </div>
        </Card>
      )}

      {assessment?.status === "failed" && (
        <Alert type="error">The assessment failed: {assessment.error || "unknown error"}. Re-run it to try again.</Alert>
      )}

      {hasResult && (
        <>
          {assessment.score && (
            <ScoreCard
              score={assessment.score}
              recommendation={findings.recommendation}
              interviewId={assessment.interview_id}
              candidateId={id}
            />
          )}

          <Card title="Requirements">
            <Table
              columns={REQUIREMENT_COLUMNS}
              data={(assessment.requirements ?? []).map((r) => ({ ...r, id: r.requirement_id }))}
              emptyMessage="No job requirements."
            />
          </Card>

          <FindingsCard title="Strengths" items={findings.strengths} interviewId={assessment.interview_id} />
          <FindingsCard title="Weaknesses" items={findings.weaknesses} interviewId={assessment.interview_id} />
          <FindingsCard title="Gaps" items={findings.gaps} interviewId={assessment.interview_id} />
        </>
      )}

      <HiringDecisionCard candidateId={id} recommendation={assessment?.score?.recommendation} assessed={hasResult} />

      <Modal
        open={confirmOpen}
        title="Re-run assessment"
        onClose={() => setConfirmOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button onClick={start}>Re-run</Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">This replaces the current assessment with a new one. Continue?</p>
      </Modal>
    </div>
  );
}
