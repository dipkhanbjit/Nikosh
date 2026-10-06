import { useEffect, useState } from "react";

import { createJob, EMPLOYMENT_TYPES, updateJob } from "../api/jobs";
import { Alert, Button, Input, Modal } from "./ui";

const EMPTY = {
  title: "",
  department: "",
  location: "",
  employment_type: "full_time",
  min_experience_years: "",
};

export default function JobFormModal({ open, job, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const isEdit = Boolean(job);

  useEffect(() => {
    if (!open) return;
    setError("");
    setForm(
      job
        ? {
            title: job.title,
            department: job.department ?? "",
            location: job.location ?? "",
            employment_type: job.employment_type,
            min_experience_years: job.min_experience_years ?? "",
          }
        : EMPTY
    );
  }, [open, job]);

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    const body = {
      title: form.title.trim(),
      department: form.department.trim() || null,
      location: form.location.trim() || null,
      employment_type: form.employment_type,
      min_experience_years:
        form.min_experience_years === "" ? null : Number(form.min_experience_years),
    };
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
      title={isEdit ? "Edit Job Profile" : "New Job Profile"}
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
          label="Job Title"
          name="title"
          value={form.title}
          onChange={handleChange}
          placeholder="e.g. Senior Backend Engineer"
          required
        />
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Department"
            name="department"
            value={form.department}
            onChange={handleChange}
            placeholder="e.g. Engineering"
          />
          <Input
            label="Location"
            name="location"
            value={form.location}
            onChange={handleChange}
            placeholder="e.g. Dhaka"
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="employment_type" className="text-sm font-medium text-gray-700">
              Employment Type
            </label>
            <select
              id="employment_type"
              name="employment_type"
              value={form.employment_type}
              onChange={handleChange}
              className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {EMPLOYMENT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <Input
            label="Minimum Experience (years)"
            name="min_experience_years"
            type="number"
            min="0"
            max="50"
            value={form.min_experience_years}
            onChange={handleChange}
          />
        </div>
      </form>
    </Modal>
  );
}