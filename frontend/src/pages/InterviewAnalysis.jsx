import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { formatClock, formatDateTime, getAnalysis, getInterview, runAnalysis } from "../api/interviews";
import { Alert, Badge, Button, Card, Modal, PageHeader, Spinner } from "../components/ui";

const ANALYSIS_STATUS = {
  pending: ["gray", "Pending"],
  running: ["blue", "Running"],
  completed: ["green", "Completed"],
  failed: ["red", "Failed"],
};
const BAND = { strong: ["green", "Strong"], moderate: ["yellow", "Moderate"], weak: ["red", "Weak"] };
const VERDICT = {
  supported: ["green", "Supported"],
  contradicted: ["red", "Contradicted"],
  not_verifiable: ["gray", "Not verifiable"],
};
const COVERAGE = {
  demonstrated: ["green", "Demonstrated"],
  partial: ["yellow", "Partial"],
  not_covered: ["red", "Not covered"],
};
const CRITERIA = ["relevance", "accuracy", "completeness", "quality"];
const POLL_MS = 3000;

const isActive = (analysis) => ["pending", "running"].includes(analysis?.status);
const timeRange = (start, end) => `${formatClock(start)}–${formatClock(end)}`;
const scrollToPair = (pairId) =>
  document.getElementById(`pair-${pairId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

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

function OverallCard({ overall }) {
  const [bandColor, bandLabel] = BAND[overall.band] ?? ["gray", "—"];
  return (
    <Card title="Overall">
      <div className="flex flex-wrap items-end gap-8">
        <Figure label="Overall score" value={overall.score} large />
        <div className="pb-1">
          <Badge color={bandColor}>{bandLabel}</Badge>
        </div>
        <Figure label="Answer score" value={overall.answer_score} />
        <Figure label="Coverage score" value={overall.coverage_score} />
      </div>
      {overall.summary && <p className="mt-4 text-sm leading-relaxed text-gray-700">{overall.summary}</p>}
    </Card>
  );
}

function QAPairCard({ pair, evaluation }) {
  const followUp = pair.type === "follow_up";
  const evaluated = evaluation?.status === "evaluated";
  const [verdictColor, verdictLabel] = VERDICT[evaluation?.accuracy_verdict] ?? [];

  return (
    <div id={`pair-${pair.id}`} className={`scroll-mt-4 rounded-lg border border-gray-200 p-4 ${followUp ? "ml-6" : ""}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-gray-900">Q{pair.id}</span>
        <Badge color={followUp ? "purple" : "indigo"}>{followUp ? "Follow-up" : "Main"}</Badge>
        <span className="text-xs text-gray-500">{timeRange(pair.start_s, pair.end_s)}</span>
        {!pair.answered && <Badge color="red">Not answered</Badge>}
        {pair.incomplete && <Badge color="gray">Incomplete</Badge>}
        {evaluated && verdictLabel && <Badge color={verdictColor}>Accuracy: {verdictLabel}</Badge>}
        {evaluation?.status === "not_evaluated" && <Badge color="gray">Not evaluated</Badge>}
      </div>

      <p className="text-sm font-medium text-gray-900">{pair.question}</p>
      {pair.sub_questions?.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-sm text-gray-700">
          {pair.sub_questions.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ul>
      )}

      <div className="mt-3 rounded-md bg-gray-50 p-3 text-sm text-gray-700">
        {pair.answered ? pair.answer : <span className="italic text-gray-500">No answer given.</span>}
      </div>

      {evaluated && (
        <div className="mt-3 flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            {CRITERIA.map((c) => (
              <div key={c} className="rounded-md border border-gray-200 px-3 py-1.5 text-center">
                <p className="text-xs capitalize text-gray-500">{c}</p>
                <p className="text-sm font-semibold text-gray-900">{evaluation.scores?.[c] ?? "—"}/5</p>
              </div>
            ))}
            <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5 text-center">
              <p className="text-xs text-gray-500">Overall</p>
              <p className="text-sm font-semibold text-gray-900">{evaluation.percent ?? "—"}%</p>
            </div>
          </div>
          {evaluation.justification && <p className="text-sm text-gray-700">{evaluation.justification}</p>}
          {evaluation.evidence?.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-gray-500">Evidence:</span>
              {evaluation.evidence.map((e) => (
                <Badge key={e.chunk_id}>
                  {e.source}
                  {e.kind ? ` (${e.kind})` : ""}
                </Badge>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RequirementRow({ mapping }) {
  const [color, label] =
    mapping.status === "not_mapped" ? ["gray", "Not assessed"] : (COVERAGE[mapping.coverage] ?? ["gray", "—"]);
  const isGap = ["partial", "not_covered"].includes(mapping.coverage);

  return (
    <div className="flex flex-col gap-2 border-b border-gray-100 py-4 last:border-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm font-medium text-gray-900">{mapping.text}</p>
        <div className="flex gap-2">
          {mapping.category && <Badge>{mapping.category}</Badge>}
          <Badge color={color}>{label}</Badge>
        </div>
      </div>
      {mapping.justification && <p className="text-sm text-gray-700">{mapping.justification}</p>}
      {mapping.citations?.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-gray-500">Cited:</span>
          {mapping.citations.map((c) => (
            <button
              key={c.pair_id}
              type="button"
              onClick={() => scrollToPair(c.pair_id)}
              className="cursor-pointer text-blue-600 hover:underline"
            >
              Q{c.pair_id} · {timeRange(c.start_s, c.end_s)}
            </button>
          ))}
        </div>
      )}
      {isGap && mapping.follow_up_question && (
        <p className="rounded-md bg-yellow-50 px-3 py-2 text-sm text-yellow-900">
          <span className="font-medium">Suggested follow-up:</span> {mapping.follow_up_question}
        </p>
      )}
    </div>
  );
}

// Interviewer only (8.4.2): run the interview analysis and show its result
export default function InterviewAnalysis() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { hash } = useLocation();
  const [interview, setInterview] = useState(null);
  const [analysis, setAnalysis] = useState(undefined); // undefined = loading, null = never run
  const [error, setError] = useState(null); // { status, message }: page cannot load
  const [actionError, setActionError] = useState(null);
  const [starting, setStarting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const fetchAnalysis = useCallback(
    () =>
      getAnalysis(id)
        .then(setAnalysis)
        .catch((err) => {
          if (err.code === "ANALYSIS_NOT_FOUND") setAnalysis(null);
          else setError({ status: err.status, message: err.message });
        }),
    [id],
  );

  useEffect(() => {
    getInterview(id)
      .then(setInterview)
      .catch((err) => setError({ status: err.status, message: err.message }));
    fetchAnalysis();
  }, [id, fetchAnalysis]);

  // Poll while the background run is pending/running; a failed poll is retried on the next tick
  const active = isActive(analysis);
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => {
      getAnalysis(id).then(setAnalysis).catch(() => {});
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [active, id]);

  // Citation links from the assessment page (#pair-N): scroll once the result is shown
  const resultShown = Boolean(interview) && analysis?.status === "completed";
  useEffect(() => {
    const match = hash.match(/^#pair-(\d+)$/);
    if (resultShown && match) scrollToPair(match[1]);
  }, [hash, resultShown]);

  const start = () => {
    setConfirmOpen(false);
    setActionError(null);
    setStarting(true);
    runAnalysis(id)
      .then(setAnalysis)
      .catch((err) => setActionError(err.message))
      .finally(() => setStarting(false));
  };

  const header = (
    <PageHeader
      title="Interview analysis"
      actions={
        <>
          {resultShown && analysis.overall?.score != null && (
            <Button
              variant="secondary"
              onClick={() => navigate(`/candidates/${interview.candidate_id}/assessment?interview=${id}`)}
            >
              Assessment
            </Button>
          )}
          <Button variant="secondary" onClick={() => navigate(`/interviews/${id}/transcript`)}>
            View transcript
          </Button>
          <Button variant="secondary" onClick={() => navigate("/interviews")}>
            Back to interviews
          </Button>
        </>
      }
    />
  );

  if (error) {
    return (
      <div>
        {header}
        <Alert type="error">{error.status === 404 ? "Interview not found." : error.message}</Alert>
      </div>
    );
  }

  if (!interview || analysis === undefined) return <Spinner />;

  const completed = interview.status === "completed";
  const [statusColor, statusLabel] = ANALYSIS_STATUS[analysis?.status] ?? ["gray", "Not run"];
  const hasResult = analysis?.status === "completed";
  const evaluations = new Map((analysis?.evaluations ?? []).map((e) => [e.pair_id, e]));
  const counts = analysis?.gaps?.counts ?? {};

  const runButton = completed && !active && (
    <Button
      loading={starting}
      onClick={() => (analysis ? setConfirmOpen(true) : start())}
      variant={analysis ? "secondary" : "primary"}
    >
      {analysis ? "Re-run analysis" : "Run analysis"}
    </Button>
  );

  return (
    <div className="flex flex-col gap-6">
      {header}

      <Card actions={runButton}>
        <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Detail label="Candidate">{interview.candidate_name || "—"}</Detail>
          <Detail label="Job">{interview.job_title}</Detail>
          <Detail label="Interview date">{formatDateTime(interview.started_at || interview.scheduled_at)}</Detail>
          <Detail label="Analysis">
            <Badge color={statusColor}>{statusLabel}</Badge>
            {analysis?.finished_at && (
              <span className="ml-2 text-xs text-gray-500">Last run {formatDateTime(analysis.finished_at)}</span>
            )}
          </Detail>
        </dl>
      </Card>

      {!completed && <Alert>Analysis is available only for completed interviews.</Alert>}
      {actionError && <Alert type="error">{actionError}</Alert>}

      {completed && analysis === null && (
        <Card>
          <p className="text-sm text-gray-600">
            This interview has not been analysed yet. Click <span className="font-medium">Run analysis</span> to
            evaluate the answers and map them to the job requirements.
          </p>
        </Card>
      )}

      {active && (
        <Card>
          <div className="flex items-center gap-3 text-sm text-gray-600">
            <Spinner size="sm" />
            Analysing interview… this can take a minute.
          </div>
        </Card>
      )}

      {analysis?.status === "failed" && (
        <Alert type="error">The analysis failed: {analysis.error || "unknown error"}. Re-run it to try again.</Alert>
      )}

      {hasResult && (
        <>
          {analysis.overall && <OverallCard overall={analysis.overall} />}

          <Card title="Questions and answers">
            {(analysis.pairs ?? []).length === 0 ? (
              <p className="text-sm text-gray-500">No question-answer pairs were found.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {analysis.pairs.map((p) => (
                  <QAPairCard key={p.id} pair={p} evaluation={evaluations.get(p.id)} />
                ))}
              </div>
            )}
          </Card>
          <Card title="Requirements">
            <div className="mb-2 flex flex-wrap gap-2">
              <Badge color="green">Demonstrated {counts.demonstrated ?? 0}</Badge>
              <Badge color="yellow">Partial {counts.partial ?? 0}</Badge>
              <Badge color="red">Not covered {counts.not_covered ?? 0}</Badge>
              {counts.not_mapped > 0 && <Badge>Not assessed {counts.not_mapped}</Badge>}
            </div>
            {(analysis.requirement_mapping ?? []).length === 0 ? (
              <p className="text-sm text-gray-500">No job requirements to map.</p>
            ) : (
              analysis.requirement_mapping.map((m) => <RequirementRow key={m.requirement_id} mapping={m} />)
            )}
          </Card>

        </>
      )}

      <Modal
        open={confirmOpen}
        title="Re-run analysis"
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
        <p className="text-sm text-gray-700">
          This replaces the current analysis result with a new one. Continue?
        </p>
      </Modal>
    </div>
  );
}
