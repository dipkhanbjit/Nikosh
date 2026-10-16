import { useEffect, useState } from "react";

import { createJob, deadlineInputValue, updateJob } from "../api/jobs";
import { Alert, Button, Input, Modal } from "./ui";

const EMPTY = { title: "", application_deadline: "" };

// The JD Assistant fills the other profile fields. Only a posted job shows the
// deadline here, so it can be extended (or the form reopened) after posting.
export default function JobFormModal({ open, job, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const isEdit = Boolean(job);
  const showDeadline = job?.status === "posted";

  useEffect(() => {
    if (!open) return;
    setError("");
    setForm(
      job
        ? { title: job.title, application_deadline: deadlineInputValue(job.application_deadline) }
        : EMPTY
    );
  }, [open, job]);

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    const body = { title: form.title.trim() };
    if (showDeadline) body.application_deadline = form.application_deadline || null;
    try {
      const saved = isEdit ? await updateJob(job.id, body) : await createJob(body);
      onSaved(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title={isEdit ? "Edit Job" : "New Job"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="job-form" loading={saving}>
            {isEdit ? "Save Changes" : "Create Job"}
          </Button>
        </>
      }
    >
      <form id="job-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && <Alert type="error">{error}</Alert>}
        <Input
          label="Job Position"
          name="title"
          value={form.title}
          onChange={handleChange}
          placeholder="e.g. Senior Backend Engineer"
          required
        />
        {!isEdit && (
          <p className="text-xs text-gray-500">
            Department, location, employment type, experience and deadline are set from your
            request in the JD Assistant.
          </p>
        )}
        {showDeadline && (
          <div className="flex flex-col gap-1">
            <Input
              label="Application Deadline"
              name="application_deadline"
              type="date"
              value={form.application_deadline}
              onChange={handleChange}
            />
            <p className="text-xs text-gray-500">
              Applications are accepted until 11:59 PM on this date. Extending it reopens the
              application form.
            </p>
          </div>
        )}
      </form>
    </Modal>
  );
}
