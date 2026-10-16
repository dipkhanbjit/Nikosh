import { EMPLOYMENT_TYPES, employmentLabel, formatDeadline } from "../api/jobs";
import { Input } from "./ui";

const todayInDhaka = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Dhaka" });

function Row({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="shrink-0 text-gray-500">{label}</span>
      <span className="min-w-0 text-right font-medium text-gray-800">{children || "—"}</span>
    </div>
  );
}

export default function JobProfileEditor({ form, onChange, editable }) {
  const handleChange = (e) => onChange({ ...form, [e.target.name]: e.target.value });

  if (!editable) {
    return (
      <div className="divide-y divide-gray-100">
        <Row label="Department">{form.department}</Row>
        <Row label="Location">{form.location}</Row>
        <Row label="Employment Type">{employmentLabel(form.employment_type)}</Row>
        <Row label="Minimum Experience">
          {form.min_experience_years !== "" ? `${form.min_experience_years} years` : null}
        </Row>
        <Row label="Application Deadline">
          {form.application_deadline ? formatDeadline(form.application_deadline) : "Set on posting"}
        </Row>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Input label="Department" name="department" value={form.department} onChange={handleChange} maxLength={100} />
        <Input label="Location" name="location" value={form.location} onChange={handleChange} maxLength={100} />
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
          max="30"
          value={form.min_experience_years}
          onChange={handleChange}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Input
          label="Application Deadline"
          name="application_deadline"
          type="date"
          min={todayInDhaka()}
          value={form.application_deadline}
          onChange={handleChange}
        />
        <p className="text-xs text-gray-500">If empty, the deadline is set to 21 days after posting.</p>
      </div>
    </div>
  );
}
