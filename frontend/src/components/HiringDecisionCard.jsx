import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { deleteCandidate, getDecision, saveDecision } from "../api/candidates";
import { formatDateTime } from "../api/interviews";
import DeleteCandidateModal from "./DeleteCandidateModal";
import { Alert, Badge, Button, Card, Modal, Spinner, Textarea } from "./ui";

const DECISION = { selected: ["green", "Selected"], not_selected: ["red", "Not selected"] };
const RECOMMENDATION = {
  recommend: "Recommend",
  consider: "Consider with reservations",
  do_not_recommend: "Do not recommend",
};
const CHECKBOX = "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500";

// Interviewer's final decision (8.6.3), separate from the AI recommendation; optionally sent to the candidate
export default function HiringDecisionCard({ candidateId, recommendation, assessed }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ decision: "", note: "", notify: false, message: "" });
  const [confirm, setConfirm] = useState(null); // the request body waiting for confirmation
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deletingBusy, setDeletingBusy] = useState(false);

  const load = (result) => {
    setData(result);
    setForm({ decision: result.decision || "", note: result.decision_note || "", notify: false, message: "" });
  };

  useEffect(() => {
    getDecision(candidateId)
      .then(load)
      .catch((err) => setError(err.message));
  }, [candidateId]);

  const save = () => {
    const body = confirm;
    setConfirm(null);
    setError("");
    setNotice("");
    setSaving(true);
    saveDecision(candidateId, body)
      .then((result) => {
        load(result);
        if (body.notify && result.decision_email_status === "sent") {
          setNotice(`Decision saved and emailed to ${result.contact_email}.`);
        } else if (!body.notify) {
          setNotice("Decision saved.");
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setSaving(false));
  };

  const handleDelete = (fromDrive) => {
    setDeletingBusy(true);
    deleteCandidate(candidateId, fromDrive)
      .then(() => navigate("/candidates"))
      .catch((err) => {
        setDeleting(false);
        setError(err.message);
      })
      .finally(() => setDeletingBusy(false));
  };

  if (!data) {
    return <Card title="Hiring decision">{error ? <Alert type="error">{error}</Alert> : <Spinner />}</Card>;
  }

  if (!data.can_decide) {
    return (
      <Card title="Hiring decision">
        <p className="text-sm text-gray-600">A decision can be made after a completed interview.</p>
      </Card>
    );
  }

  const [decisionColor, decisionLabel] = DECISION[data.decision] ?? [];
  const notified = Boolean(data.decision_notified_at);
  const changing = notified && form.decision !== data.decision;
  const request = {
    decision: form.decision,
    note: form.note,
    notify: form.notify,
    message: form.notify ? form.message : null,
  };
  const resend = {
    decision: data.decision,
    note: data.decision_note,
    notify: true,
    message: data.decision_message,
  };

  return (
    <Card title="Hiring decision">
      <div className="flex flex-col gap-4">
        {data.decision && (
          <div className="flex flex-col gap-1 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge color={decisionColor}>{decisionLabel}</Badge>
              <span className="text-gray-500">
                by {data.decided_by_name || "—"} on {formatDateTime(data.decided_at)}
              </span>
            </div>
            {notified ? (
              <p className="text-gray-600">
                Candidate notified on {formatDateTime(data.decision_notified_at)}
                {data.decision_email_status === "sent" && " (email sent)."}
              </p>
            ) : (
              <p className="text-gray-500">Not shared with the candidate.</p>
            )}
            {data.decision_email_status === "failed" && (
              <div className="flex flex-wrap items-center gap-2 text-red-700">
                <span>Email failed: {data.decision_email_error || "unknown error"}.</span>
                <Button variant="secondary" className="px-3 py-1" onClick={() => setConfirm(resend)} disabled={saving}>
                  Resend
                </Button>
              </div>
            )}
          </div>
        )}

        {error && <Alert type="error">{error}</Alert>}
        {notice && <Alert type="success">{notice}</Alert>}

        <p className="text-sm text-gray-500">
          {assessed && recommendation
            ? `AI recommendation: ${RECOMMENDATION[recommendation] ?? recommendation} (for reference only; the decision is yours).`
            : "No assessment yet: the decision will be made without it."}
        </p>

        <div className="flex flex-wrap gap-6">
          {Object.entries(DECISION).map(([value, [, label]]) => (
            <label key={value} className="flex items-center gap-2 text-sm text-gray-800">
              <input
                type="radio"
                name="decision"
                value={value}
                checked={form.decision === value}
                onChange={() => setForm({ ...form, decision: value })}
                className="h-4 w-4 border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              {label}
            </label>
          ))}
        </div>

        <Textarea
          label="Internal note (not shown to the candidate)"
          name="decision_note"
          rows={3}
          maxLength={2000}
          value={form.note}
          onChange={(e) => setForm({ ...form, note: e.target.value })}
        />

        <label className="flex items-center gap-2 text-sm text-gray-800">
          <input
            type="checkbox"
            checked={form.notify}
            onChange={(e) => setForm({ ...form, notify: e.target.checked })}
            className={CHECKBOX}
          />
          Notify the candidate (email to {data.contact_email || "—"} and their home page)
        </label>

        {form.notify && (
          <Textarea
            label="Message to the candidate (optional)"
            name="decision_message"
            rows={4}
            maxLength={2000}
            value={form.message}
            onChange={(e) => setForm({ ...form, message: e.target.value })}
            placeholder="Added below the standard outcome text"
          />
        )}

        <div className="flex flex-wrap justify-between gap-2">
          <Button onClick={() => setConfirm(request)} loading={saving} disabled={!form.decision}>
            Save decision
          </Button>
          {data.decision && (
            <Button variant="danger" onClick={() => setDeleting(true)} disabled={saving}>
              Delete candidate data
            </Button>
          )}
        </div>
      </div>

      <Modal
        open={Boolean(confirm)}
        title="Confirm decision"
        onClose={() => setConfirm(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button onClick={save}>Confirm</Button>
          </>
        }
      >
        {confirm && (
          <div className="flex flex-col gap-2 text-sm text-gray-700">
            <p>
              Save the decision <span className="font-semibold">{DECISION[confirm.decision]?.[1]}</span>
              {confirm.notify ? (
                <>
                  {" "}
                  and email it to <span className="font-semibold">{data.contact_email}</span>? The candidate will
                  also see it on their home page.
                </>
              ) : (
                "? The candidate will not be notified."
              )}
            </p>
            {changing && !confirm.notify && (
              <p>The candidate will no longer see the previous decision on their home page.</p>
            )}
          </div>
        )}
      </Modal>

      <DeleteCandidateModal
        candidate={deleting ? data : null}
        busy={deletingBusy}
        onCancel={() => setDeleting(false)}
        onDelete={handleDelete}
        note="The hiring decision is deleted too, and the candidate will no longer see it on their home page (an email already sent stays in their inbox)."
      />
    </Card>
  );
}
