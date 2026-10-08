import { useCallback, useEffect, useRef, useState } from "react";

import {
  ACCEPTED_CV_TYPES,
  countNewApplications,
  cvUrl,
  deleteCandidate,
  extractCVs,
  getCVText,
  listCandidates,
  parseCVs,
  syncApplications,
  uploadCVs,
} from "../api/candidates";
import CandidateProfileModal from "./CandidateProfileModal";
import { Alert, Badge, Button, Card, Modal, Table } from "./ui";

const POLL_INTERVAL_MS = 30000;
const SOURCE_BADGE = { form: ["blue", "Google Form"], upload: ["gray", "Upload"] };
const STATUS_BADGE = { applied: ["green", "Applied"], rejected: ["red", "Rejected"] };

const formatDateTime = (value) =>
  new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

function analysisState(c) {
  if (c.extraction_status === "failed") return { color: "red", label: "Text failed", tip: c.extraction_error };
  if (c.extraction_status !== "extracted") return { color: "gray", label: "Pending" };
  if (c.parse_status === "parsed") return { color: "green", label: "Parsed", clickable: true };
  if (c.parse_status === "failed") return { color: "red", label: "Parse failed", tip: c.parse_error, clickable: true };
  return { color: "gray", label: "Pending", clickable: true };
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

export default function CandidatesCard({ job }) {
  const fileInput = useRef(null);
  const [candidates, setCandidates] = useState([]);
  const [newCount, setNewCount] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [summary, setSummary] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [viewing, setViewing] = useState(null);

  const canIntake = job.status === "approved" || job.status === "posted";
  const needsProcessing = candidates.some(
    (c) => c.status === "applied" && (c.extraction_status !== "extracted" || c.parse_status !== "parsed")
  );

  const refresh = useCallback(() => {
    listCandidates(job.id).then(setCandidates).catch((err) => setError(err.message));
    if (canIntake) {
      countNewApplications(job.id)
        .then((r) => setNewCount(r.count))
        .catch(() => {});
    }
  }, [job.id, canIntake]);

  useEffect(() => {
    refresh();
    if (!canIntake) return undefined;
    const timer = setInterval(() => {
      countNewApplications(job.id)
        .then((r) => setNewCount(r.count))
        .catch(() => {});
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [job.id, canIntake, refresh]);

  const run = async (setBusy, action) => {
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

  const handleSync = () => run(setSyncing, async () => setSummary(await syncApplications(job.id)));

  const handleFiles = (e) => {
    const files = Array.from(e.target.files);
    e.target.value = "";
    if (files.length === 0) return;
    run(setUploading, async () => setSummary(await uploadCVs(job.id, files)));
  };

  const handleProcess = () =>
    run(setProcessing, async () => {
      const text = await extractCVs(job.id);
      const parsed = await parseCVs(job.id);
      const failed = text.failed + parsed.failed;
      setNotice(
        `Text extracted: ${text.extracted} · Profiles parsed: ${parsed.parsed}${failed ? ` · Failed: ${failed}` : ""}`
      );
    });

  const openProfile = async (candidate) => {
    setViewing({ candidate, data: null });
    try {
      setViewing({ candidate, data: await getCVText(candidate.id) });
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

  const columns = [
    {
      key: "name",
      label: "Candidate",
      render: (c) => (
        <div>
          <p className="font-medium text-gray-800">{c.full_name || "Name not found"}</p>
          <p className="text-xs text-gray-500">{c.email || c.cv_filename}</p>
        </div>
      ),
    },
    { key: "phone", label: "Phone", render: (c) => c.phone || "—" },
    {
      key: "cv",
      label: "CV",
      render: (c) =>
        c.status !== "rejected" && c.cv_filename ? (
          <a
            href={cvUrl(c.id)}
            target="_blank"
            rel="noreferrer"
            className="block max-w-[14rem] truncate text-indigo-600 hover:underline"
            title={c.cv_filename}
          >
            {c.cv_filename}
          </a>
        ) : (
          "—"
        ),
    },
    {
      key: "analysis",
      label: "CV Analysis",
      render: (c) => {
        if (c.status === "rejected") return "—";
        const s = analysisState(c);
        const badge = <Badge color={s.color}>{s.label}</Badge>;
        return s.clickable ? (
          <button type="button" onClick={() => openProfile(c)} title={s.tip || "View profile"}>
            {badge}
          </button>
        ) : (
          <span title={s.tip || ""}>{badge}</span>
        );
      },
    },
    {
      key: "source",
      label: "Source",
      render: (c) => {
        const [color, label] = SOURCE_BADGE[c.source] ?? ["gray", c.source];
        return <Badge color={color}>{label}</Badge>;
      },
    },
    {
      key: "status",
      label: "Status",
      render: (c) => {
        const [color, label] = STATUS_BADGE[c.status] ?? ["gray", c.status];
        return <Badge color={color}>{label}</Badge>;
      },
    },
    {
      key: "applied_at",
      label: "Applied",
      render: (c) => (c.applied_at ? formatDateTime(c.applied_at) : "—"),
    },
    {
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
  ];

  return (
    <Card
      title={`Candidates (${candidates.length})`}
      actions={
        canIntake && (
          <div className="flex gap-2">
            {needsProcessing && (
              <Button variant="secondary" onClick={handleProcess} loading={processing}>
                {processing ? "Processing…" : "Process CVs"}
              </Button>
            )}
            <Button variant="secondary" onClick={() => fileInput.current.click()} loading={uploading}>
              Upload CVs
            </Button>
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
        {error && <Alert type="error">{error}</Alert>}
        {notice && <Alert type="success">{notice}</Alert>}
        {summary && <ImportResults summary={summary} onClose={() => setSummary(null)} />}
        <Table columns={columns} data={candidates} emptyMessage="No candidates yet." />
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