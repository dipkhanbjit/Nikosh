import { useCallback, useEffect, useState } from "react";

import {
  INTERVIEW_STATUS,
  cancelInterview,
  formatDateTime,
  listInterviews,
  markNoShow,
} from "../api/interviews";
import { Alert, Badge, Button, Card, Modal, PageHeader, Table, Textarea } from "../components/ui";
import { copyText } from "../utils/clipboard";

const MIN_REASON_LENGTH = 3;

export default function Interviews() {
  const [interviews, setInterviews] = useState([]);
  const [status, setStatus] = useState("");
  const [action, setAction] = useState(null); // { interview, type: "cancel" | "no_show" }
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [manualLink, setManualLink] = useState(null); // { name, url } when automatic copy failed
  const [error, setError] = useState("");

  const load = useCallback(() => {
    listInterviews(status).then(setInterviews).catch((err) => setError(err.message));
  }, [status]);

  useEffect(load, [load]);

  const openAction = (interview, type) => {
    setReason("");
    setAction({ interview, type });
  };

  const cancelling = action?.type === "cancel";
  const name = action?.interview.candidate_name || "this candidate";

  const handleCopy = async (iv) => {
    setError("");
    setManualLink(null);
    const name = iv.candidate_name || "the candidate";
    if (await copyText(iv.join_url)) {
      setNotice(`Interview link for ${name} copied.`);
    } else {
      setNotice("");
      setManualLink({ name, url: iv.join_url });
    }
  };

  const handleAction = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      if (cancelling) {
        await cancelInterview(action.interview.id, reason.trim());
        setNotice(`Interview with ${name} was cancelled.`);
      } else {
        await markNoShow(action.interview.id);
        setNotice(`${name} was marked as no-show.`);
      }
      setAction(null);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const columns = [
    {
      key: "candidate",
      label: "Candidate",
      render: (iv) => (
        <div>
          <p className="font-medium text-gray-800">{iv.candidate_name || "Name not found"}</p>
          <p className="text-xs text-gray-500">{iv.candidate_email}</p>
        </div>
      ),
    },
    { key: "job_title", label: "Job" },
    { key: "scheduled_at", label: "Date & Time", render: (iv) => formatDateTime(iv.scheduled_at) },
    { key: "duration", label: "Duration", render: (iv) => `${iv.duration_minutes} min` },
    {
      key: "status",
      label: "Status",
      render: (iv) => {
        const [color, label] = INTERVIEW_STATUS[iv.status] ?? ["gray", iv.status];
        return (
          <div>
            <Badge color={color}>{label}</Badge>
            {iv.cancel_reason && (
              <p className="mt-1 max-w-[14rem] text-xs text-gray-500" title={iv.cancel_reason}>
                {iv.cancel_reason}
              </p>
            )}
          </div>
        );
      },
    },
    {
      key: "notes",
      label: "Notes",
      render: (iv) => <p className="max-w-[16rem] text-sm text-gray-600">{iv.notes || "—"}</p>,
    },
    {
      key: "actions",
      label: "",
      render: (iv) =>
        iv.status === "scheduled" && (
          <div className="flex justify-end gap-2">
            <Button variant="secondary" className="px-3 py-1" onClick={() => handleCopy(iv)}>
              Copy link
            </Button>
            {new Date(iv.scheduled_at) <= new Date() && (
              <Button variant="secondary" className="px-3 py-1" onClick={() => openAction(iv, "no_show")}>
                No-show
              </Button>
            )}
            <Button variant="secondary" className="px-3 py-1 text-red-600" onClick={() => openAction(iv, "cancel")}>
              Cancel
            </Button>
          </div>
        ),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Interviews" subtitle="Scheduled interview sessions and their status." />

      {error && <Alert type="error">{error}</Alert>}
      {notice && <Alert type="success">{notice}</Alert>}
      {manualLink && (
        <Alert type="info">
          <div className="flex items-start justify-between gap-3">
            <p>Could not copy automatically. Copy the interview link for {manualLink.name}:</p>
            <button type="button" onClick={() => setManualLink(null)} className="text-xs opacity-70 hover:opacity-100">
              Dismiss
            </button>
          </div>
          <input
            readOnly
            value={manualLink.url}
            onFocus={(e) => e.target.select()}
            autoFocus
            className="mt-2 w-full rounded-md border border-blue-200 bg-white px-3 py-2 font-mono text-xs text-gray-800"
          />
        </Alert>
      )}

      <Card
        title={`Sessions (${interviews.length})`}
        actions={
          <select
            aria-label="Filter by status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All statuses</option>
            {Object.entries(INTERVIEW_STATUS).map(([value, [, label]]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        }
      >
        <Table columns={columns} data={interviews} emptyMessage="No interviews found." />
      </Card>

      <Modal
        open={Boolean(action)}
        title={cancelling ? "Cancel Interview" : "Mark as No-show"}
        onClose={() => setAction(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setAction(null)} disabled={saving}>
              Back
            </Button>
            <Button
              variant="danger"
              onClick={handleAction}
              loading={saving}
              disabled={cancelling && reason.trim().length < MIN_REASON_LENGTH}
            >
              {cancelling ? "Cancel interview" : "Mark no-show"}
            </Button>
          </>
        }
      >
        {action && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-gray-700">
              {cancelling ? "Cancel the interview with " : "Mark "}
              <span className="font-semibold">{name}</span>
              {cancelling
                ? ` on ${formatDateTime(action.interview.scheduled_at)}?`
                : " as no-show? This cannot be undone."}
            </p>
            {cancelling && (
              <Textarea
                label="Reason *"
                name="cancel_reason"
                rows={3}
                maxLength={255}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why is this interview cancelled?"
              />
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
