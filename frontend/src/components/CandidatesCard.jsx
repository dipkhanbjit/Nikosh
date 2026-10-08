import { useCallback, useEffect, useRef, useState } from "react";

import {
  ACCEPTED_CV_TYPES,
  countNewApplications,
  cvUrl,
  deleteCandidate,
  extractCVs,
  getCVText,
  listCandidates,
  syncApplications,
  uploadCVs,
} from "../api/candidates";
import { Alert, Badge, Button, Card, Modal, Spinner, Table } from "./ui";

const POLL_INTERVAL_MS = 30000;
const SOURCE_BADGE = { form: ["blue", "Google Form"], upload: ["gray", "Upload"] };
const STATUS_BADGE = { applied: ["green", "Applied"], rejected: ["red", "Rejected"] };
const TEXT_BADGE = {
  extracted: ["green", "Extracted"],
  failed: ["red", "Failed"],
  pending: ["gray", "Pending"],
};

const formatDateTime = (value) =>
  new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

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
  const [extracting, setExtracting] = useState(false);
  const [summary, setSummary] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [viewing, setViewing] = useState(null);

  const canIntake = job.status === "approved" || job.status === "posted";
  const needsExtraction = candidates.some(
    (c) => c.status === "applied" && c.extraction_status !== "extracted"
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

  const handleSync = async () => {
    setSyncing(true);
    setError("");
    setNotice("");
    try {
      setSummary(await syncApplications(job.id));
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setSyncing(false);
    }
  };

  const handleFiles = async (e) => {
    const files = Array.from(e.target.files);
    e.target.value = "";
    if (files.length === 0) return;
    setUploading(true);
    setError("");
    setNotice("");
    try {
      setSummary(await uploadCVs(job.id, files));
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleExtract = async () => {
    setExtracting(true);
    setError("");
    setSummary(null);
    try {
      const r = await extractCVs(job.id);
      setNotice(`Text extracted for ${r.extracted} of ${r.processed} CV(s)${r.failed ? `, ${r.failed} failed` : ""}.`);
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setExtracting(false);
    }
  };

  const openText = async (candidate) => {
    setViewing({ candidate, text: null });
    try {
      const data = await getCVText(candidate.id);
      setViewing({ candidate, text: data.cv_text || "" });
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
          <p className="font-medium text-gray-800">{c.full_name || "Name pending extraction"}</p>
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
      key: "text",
      label: "CV Text",
      render: (c) => {
        if (c.status === "rejected") return "—";
        const [color, label] = TEXT_BADGE[c.extraction_status] ?? ["gray", c.extraction_status];
        if (c.extraction_status === "extracted") {
          return (
            <button type="button" onClick={() => openText(c)} title="View extracted text">
              <Badge color={color}>{label}</Badge>
            </button>
          );
        }
        return (
          <span title={c.extraction_error || ""}>
            <Badge color={color}>{label}</Badge>
          </span>
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
            {needsExtraction && (
              <Button variant="secondary" onClick={handleExtract} loading={extracting}>
                {extracting ? "Extracting…" : "Extract CV Text"}
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

      <Modal
        open={Boolean(viewing)}
        title={`Extracted Text — ${viewing?.candidate.cv_filename ?? ""}`}
        onClose={() => setViewing(null)}
        footer={
          <Button variant="secondary" onClick={() => setViewing(null)}>
            Close
          </Button>
        }
      >
        {viewing?.text === null ? (
          <div className="flex justify-center py-8 text-indigo-600">
            <Spinner />
          </div>
        ) : (
          <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded-md bg-gray-50 p-3 font-sans text-xs leading-relaxed text-gray-700">
            {viewing?.text}
          </pre>
        )}
      </Modal>

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