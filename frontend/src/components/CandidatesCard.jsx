import { useCallback, useEffect, useRef, useState } from "react";

import {
  ACCEPTED_CV_TYPES,
  countNewApplications,
  cvUrl,
  deleteCandidate,
  getCVText,
  getScreening,
  listCandidates,
  startScreening,
  syncApplications,
  uploadCVs,
} from "../api/candidates";
import { formatDeadline, getScoreWeights } from "../api/jobs";
import CandidateProfileModal from "./CandidateProfileModal";
import { Alert, Badge, Button, Card, Modal, Table } from "./ui";

const POLL_INTERVAL_MS = 30000;
const PROGRESS_INTERVAL_MS = 2000;
const SOURCE_BADGE = { form: ["blue", "Google Form"], upload: ["gray", "Upload"] };
const STATUS_STYLE = {
  applied: ["bg-green-100 text-green-700", "Applied"],
  excluded: ["bg-amber-100 text-amber-800", "Excluded"],
  rejected: ["bg-red-100 text-red-700", "Rejected"],
};
const TABS = [
  { key: "applied", label: "Applicants", empty: "No eligible candidates yet." },
  { key: "excluded", label: "Excluded", empty: "No candidates were excluded." },
  { key: "rejected", label: "Rejected", empty: "No applications were rejected." },
];

const formatDateTime = (value) =>
  new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

const scoreColor = (score) =>
  score >= 70 ? "bg-green-500" : score >= 40 ? "bg-amber-500" : "bg-red-500";

const pillColor = (score) =>
  score >= 70
    ? "bg-green-100 text-green-800"
    : score >= 40
      ? "bg-amber-100 text-amber-800"
      : "bg-red-100 text-red-700";

function analysisState(c) {
  if (c.extraction_status === "failed") return { color: "red", label: "Text failed", tip: c.extraction_error };
  if (c.extraction_status !== "extracted") return { color: "gray", label: "Pending" };
  if (c.parse_status === "failed") return { color: "red", label: "Parse failed", tip: c.parse_error, clickable: true };
  if (c.parse_status !== "parsed") return { color: "gray", label: "Pending", clickable: true };
  if (c.screening_status === "screened") return { color: "green", label: "Screened", clickable: true };
  if (c.screening_status === "failed")
    return { color: "red", label: "Screening failed", tip: c.screening_error, clickable: true };
  return { color: "blue", label: "Parsed", clickable: true };
}

function StatusBadge({ status }) {
  const [style, label] = STATUS_STYLE[status] ?? ["bg-gray-100 text-gray-700", status];
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>{label}</span>;
}

function ScoreCell({ candidate }) {
  const { match_score: score, match_counts: counts } = candidate;
  if (score == null) return "—";
  return (
    <div className="w-36">
      <div className="flex items-center gap-2">
        <span className="w-12 text-sm font-semibold text-gray-800">{score.toFixed(1)}%</span>
        <div className="h-1.5 flex-1 rounded-full bg-gray-100">
          <div className={`h-1.5 rounded-full ${scoreColor(score)}`} style={{ width: `${score}%` }} />
        </div>
      </div>
      {counts && (
        <p className="mt-1 text-xs text-gray-500">
          {counts.met} met · {counts.partial} partial · {counts.unmet} unmet
        </p>
      )}
    </div>
  );
}

function OverallCell({ candidate }) {
  if (candidate.scoring_status === "failed") {
    return (
      <span className="text-xs font-medium text-red-600" title={candidate.scoring_error || ""}>
        Scoring failed
      </span>
    );
  }
  if (candidate.overall_score == null) return "—";
  return (
    <span className={`inline-block rounded-md px-2 py-1 text-sm font-semibold ${pillColor(candidate.overall_score)}`}>
      {candidate.overall_score.toFixed(1)}
    </span>
  );
}

function ScreeningProgress({ run }) {
  const percent = run.total ? Math.round((run.processed / run.total) * 100) : 0;
  return (
    <div className="rounded-md border border-indigo-100 bg-indigo-50 p-3">
      <div className="flex justify-between text-sm">
        <span className="font-medium text-indigo-800">
          {run.total ? `Screening CVs… ${run.processed} of ${run.total}` : "Preparing screening…"}
        </span>
        {run.total > 0 && <span className="text-indigo-700">{percent}%</span>}
      </div>
      <div className="mt-2 h-2 rounded-full bg-indigo-100">
        <div className="h-2 rounded-full bg-indigo-600 transition-all" style={{ width: `${percent}%` }} />
      </div>
      {run.failed > 0 && <p className="mt-2 text-xs text-red-600">{run.failed} failed so far</p>}
    </div>
  );
}

function ImportResults({ summary, onClose }) {
  const problems = summary.results.filter((r) => r.status !== "imported");
  const type = summary.imported > 0 && problems.length === 0 ? "success" : problems.length ? "error" : "info";
  return (
    <Alert type={type}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium">
            {summary.imported} imported · {summary.rejected} rejected · {summary.failed} failed
          </p>
          {problems.map((r, i) => (
            <p key={i} className="mt-1">
              {r.filename}: {r.reason}
            </p>
          ))}
        </div>
        <button type="button" onClick={onClose} className="text-xs opacity-70 hover:opacity-100">
          Dismiss
        </button>
      </div>
    </Alert>
  );
}

function Tabs({ active, counts, onChange }) {
  return (
    <div className="flex gap-1 border-b border-gray-200">
      {TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          onClick={() => onChange(t.key)}
          className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
            active === t.key
              ? "border-indigo-600 text-indigo-700"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          {t.label} <span className="ml-1 rounded-full bg-gray-100 px-2 text-xs text-gray-600">{counts[t.key]}</span>
        </button>
      ))}
    </div>
  );
}

export default function CandidatesCard({ job }) {
  const fileInput = useRef(null);
  const [candidates, setCandidates] = useState([]);
  const [tab, setTab] = useState("applied");
  const [newCount, setNewCount] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [run, setRun] = useState(null);
  const [summary, setSummary] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [viewing, setViewing] = useState(null);

  const canIntake = job.status === "approved" || job.status === "posted";
  const closed = job.applications_closed;
  const screening = run?.status === "running";
  const needsProcessing = candidates.some(
    (c) =>
      c.status === "applied" &&
      (c.extraction_status !== "extracted" ||
        c.parse_status !== "parsed" ||
        c.screening_status !== "screened" ||
        c.scoring_status !== "scored")
  );

  const byStatus = (status) => candidates.filter((c) => c.status === status);
  const lists = {
    applied: byStatus("applied"),
    excluded: byStatus("excluded").sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1)),
    rejected: byStatus("rejected"),
  };
  const counts = Object.fromEntries(TABS.map((t) => [t.key, lists[t.key].length]));
  const activeTab = TABS.find((t) => t.key === tab);

  const loadCandidates = useCallback(() => {
    listCandidates(job.id).then(setCandidates).catch((err) => setError(err.message));
  }, [job.id]);

  const refresh = useCallback(() => {
    loadCandidates();
    if (canIntake) {
      countNewApplications(job.id)
        .then((r) => setNewCount(r.count))
        .catch(() => {});
    }
  }, [job.id, canIntake, loadCandidates]);

  // Initial load + polling for new form applications
  useEffect(() => {
    refresh();
    getScreening(job.id).then(setRun).catch(() => {});
    if (!canIntake) return undefined;
    const timer = setInterval(() => {
      countNewApplications(job.id)
        .then((r) => setNewCount(r.count))
        .catch(() => {});
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [job.id, canIntake, refresh]);

  // While a screening run is in progress, poll its status and refresh the table
  useEffect(() => {
    if (!screening) return undefined;
    const timer = setInterval(async () => {
      try {
        const latest = await getScreening(job.id);
        setRun(latest);
        loadCandidates();
        if (latest && latest.status === "completed") {
          setNotice(
            `Screening finished: ${latest.succeeded} processed` + (latest.failed ? ` · ${latest.failed} failed` : "")
          );
        } else if (latest && latest.status === "failed") {
          setError(latest.error || "Screening failed");
        }
      } catch {
        // keep polling; a temporary network error should not stop progress updates
      }
    }, PROGRESS_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [screening, job.id, loadCandidates]);

  const runAction = async (setBusy, action) => {
    setBusy(true);
    setError("");
    setNotice("");
    setSummary(null);
    try {
      await action();
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleSync = () => runAction(setSyncing, async () => setSummary(await syncApplications(job.id)));

  const handleFiles = (e) => {
    const files = Array.from(e.target.files);
    e.target.value = "";
    if (files.length === 0) return;
    runAction(setUploading, async () => setSummary(await uploadCVs(job.id, files)));
  };

  const handleProcess = async () => {
    setError("");
    setNotice("");
    setSummary(null);
    try {
      setRun(await startScreening(job.id));
    } catch (err) {
      setError(err.message);
    }
  };

  const openProfile = async (candidate) => {
    setViewing({ candidate, data: null });
    try {
      const [data, weights] = await Promise.all([getCVText(candidate.id), getScoreWeights(job.id)]);
      setViewing({ candidate, data: { ...data, weights: weights.weights } });
    } catch (err) {
      setViewing(null);
      setError(err.message);
    }
  };

  const handleDelete = async () => {
    try {
      await deleteCandidate(deleting.id);
      setDeleting(null);
      refresh();
    } catch (err) {
      setError(err.message);
    }
  };

  const allColumns = {
    rank: {
      key: "rank",
      label: "Rank",
      render: (c) =>
        c.rank != null ? <span className="text-sm font-bold text-indigo-700">#{c.rank}</span> : "—",
    },
    name: {
      key: "name",
      label: "Candidate",
      render: (c) => (
        <div>
          <p className="font-medium text-gray-800">{c.full_name || "Name not found"}</p>
          <p className="text-xs text-gray-500">{c.email || c.cv_filename}</p>
          {c.phone && <p className="text-xs text-gray-500">{c.phone}</p>}
        </div>
      ),
    },
    score: { key: "score", label: "Match Score", render: (c) => <ScoreCell candidate={c} /> },
    overall: { key: "overall", label: "Candidate Score", render: (c) => <OverallCell candidate={c} /> },
    analysis: {
      key: "analysis",
      label: "CV Analysis",
      render: (c) => {
        const s = analysisState(c);
        const badge = <Badge color={s.color}>{s.label}</Badge>;
        return s.clickable ? (
          <button type="button" onClick={() => openProfile(c)} title={s.tip || "View details"}>
            {badge}
          </button>
        ) : (
          <span title={s.tip || ""}>{badge}</span>
        );
      },
    },
    cv: {
      key: "cv",
      label: "CV",
      render: (c) =>
        c.cv_filename && c.status !== "rejected" ? (
          <a
            href={cvUrl(c.id)}
            target="_blank"
            rel="noreferrer"
            className="block max-w-[10rem] truncate text-indigo-600 hover:underline"
            title={c.cv_filename}
          >
            {c.cv_filename}
          </a>
        ) : (
          "—"
        ),
    },
    status: { key: "status", label: "Status", render: (c) => <StatusBadge status={c.status} /> },
    reason: {
      key: "reason",
      label: "Reason",
      render: (c) => (
        <p className={`max-w-[18rem] text-sm ${c.status === "excluded" ? "text-amber-700" : "text-red-600"}`}>
          {c.rejection_reason || "—"}
        </p>
      ),
    },
    source: {
      key: "source",
      label: "Source",
      render: (c) => {
        const [color, label] = SOURCE_BADGE[c.source] ?? ["gray", c.source];
        return <Badge color={color}>{label}</Badge>;
      },
    },
    applied_at: {
      key: "applied_at",
      label: "Applied",
      render: (c) => (c.applied_at ? formatDateTime(c.applied_at) : "—"),
    },
    actions: {
      key: "actions",
      label: "",
      render: (c) => (
        <div className="flex justify-end">
          <Button variant="secondary" className="px-3 py-1 text-red-600" onClick={() => setDeleting(c)}>
            Delete
          </Button>
        </div>
      ),
    },
  };

  const TAB_COLUMNS = {
    applied: ["rank", "name", "score", "overall", "analysis", "cv", "status", "source", "applied_at", "actions"],
    excluded: ["name", "score", "reason", "analysis", "cv", "source", "applied_at", "actions"],
    rejected: ["name", "reason", "source", "applied_at", "actions"],
  };
  const columns = TAB_COLUMNS[tab].map((key) => allColumns[key]);

  return (
    <Card
      title={`Candidates (${candidates.length})`}
      actions={
        canIntake && (
          <div className="flex gap-2">
            {(needsProcessing || screening) && (
              <Button variant="secondary" onClick={handleProcess} loading={screening}>
                {screening ? `Screening ${run.processed}/${run.total || "…"}` : "Process CVs"}
              </Button>
            )}
            {!closed && (
              <Button variant="secondary" onClick={() => fileInput.current.click()} loading={uploading}>
                Upload CVs
              </Button>
            )}
            <Button variant={newCount > 0 ? "danger" : "primary"} onClick={handleSync} loading={syncing}>
              {syncing ? "Syncing…" : newCount > 0 ? `Sync Applications (${newCount} new)` : "Sync Applications"}
            </Button>
          </div>
        )
      }
    >
      <input
        ref={fileInput}
        type="file"
        accept={ACCEPTED_CV_TYPES}
        multiple
        onChange={handleFiles}
        className="hidden"
      />

      <div className="flex flex-col gap-4">
        {!canIntake && (
          <p className="text-sm text-gray-500">CV collection opens once the JD is approved.</p>
        )}
        {canIntake && closed && (
          <Alert type="info">
            Applications closed on {formatDeadline(job.application_deadline)}. Form submissions after the
            deadline are rejected automatically during sync.
          </Alert>
        )}
        {screening && <ScreeningProgress run={run} />}
        {error && <Alert type="error">{error}</Alert>}
        {notice && <Alert type="success">{notice}</Alert>}
        {summary && <ImportResults summary={summary} onClose={() => setSummary(null)} />}
        <Tabs active={tab} counts={counts} onChange={setTab} />
        {tab === "applied" && counts.applied > 0 && (
          <p className="text-sm text-gray-500">
            Rank follows the requirement Match Score. Candidate Score is the separate weighted assessment
            (see Scoring Weights).
          </p>
        )}
        {tab === "excluded" && counts.excluded > 0 && (
          <p className="text-sm text-gray-500">
            These candidates did not meet at least one mandatory requirement, so they are not ranked or scored.
          </p>
        )}
        <Table columns={columns} data={lists[tab]} emptyMessage={activeTab.empty} />
      </div>

      <CandidateProfileModal viewing={viewing} onClose={() => setViewing(null)} />

      <Modal
        open={Boolean(deleting)}
        title="Delete Candidate"
        onClose={() => setDeleting(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">
          Delete <span className="font-semibold">{deleting?.full_name || deleting?.cv_filename}</span>?
          Their record and CV file will be permanently removed.
        </p>
      </Modal>
    </Card>
  );
}