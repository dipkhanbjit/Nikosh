import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { employmentLabel, formatDeadline, getJob, STATUS_COLORS } from "../api/jobs";
import CandidatesCard from "../components/CandidatesCard";
import JobFormModal from "../components/JobFormModal";
import MarkdownView from "../components/MarkdownView";
import PostingCard from "../components/PostingCard";
import { Alert, Badge, Button, Card, PageHeader, Spinner } from "../components/ui";

const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function RequirementList({ title, items }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</p>
      <ul className="divide-y divide-gray-100">
        {items.map((r, i) => (
          <li key={i} className="flex items-start justify-between gap-3 py-2">
            <div>
              <p className="text-sm text-gray-800">{r.text}</p>
              <p className="text-xs text-gray-500">{capitalize(r.category)}</p>
            </div>
            <span className="shrink-0 text-xs font-medium text-gray-500">Weight {r.weight}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DetailRow({ label, value }) {
  return (
    <div className="flex justify-between py-2 text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-gray-800">{value || "—"}</span>
    </div>
  );
}

function DeadlineRow({ job }) {
  return (
    <div className="flex justify-between py-2 text-sm">
      <span className="text-gray-500">Application Deadline</span>
      {job.application_deadline ? (
        <span className="flex items-center gap-2 font-medium text-gray-800">
          {formatDeadline(job.application_deadline)}
          {job.applications_closed && <Badge color="red">Closed</Badge>}
        </span>
      ) : (
        <span className="font-medium text-gray-800">Set on posting</span>
      )}
    </div>
  );
}

export default function JobDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [editOpen, setEditOpen] = useState(false);

  useEffect(() => {
    getJob(id).then(setJob).catch((err) => setError(err.message));
  }, [id]);

  if (error) return <Alert type="error">{error}</Alert>;
  if (!job) {
    return (
      <div className="flex justify-center py-12 text-indigo-600">
        <Spinner size="lg" />
      </div>
    );
  }

  const mandatory = job.requirements.filter((r) => r.mandatory);
  const preferred = job.requirements.filter((r) => !r.mandatory);
  const canEditJD = job.status === "draft" || job.status === "approved";

  return (
    <div>
      <Link to="/jobs" className="mb-3 inline-block text-sm text-gray-500 hover:text-gray-700">
        ← Back to Jobs
      </Link>
      <PageHeader
        title={job.title}
        subtitle={[job.department, job.location].filter(Boolean).join(" · ")}
        actions={
          <>
            <Button variant="secondary" onClick={() => setEditOpen(true)}>
              Edit Profile
            </Button>
            {canEditJD && (
              <Button onClick={() => navigate(`/jobs/${job.id}/jd`)}>
                {job.description ? "Revise JD" : "Generate JD"}
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Job Description" className="lg:col-span-2">
          {job.description ? (
            <MarkdownView content={job.description} />
          ) : (
            <div className="py-10 text-center">
              <p className="text-sm text-gray-500">No job description yet.</p>
              <p className="mt-1 text-sm text-gray-500">
                Use the JD Assistant to generate one from company documents.
              </p>
            </div>
          )}
        </Card>

        <div className="flex flex-col gap-6">
          <PostingCard job={job} onUpdated={setJob} />

          <Card title="Profile">
            <div className="divide-y divide-gray-100">
              <div className="flex justify-between py-2 text-sm">
                <span className="text-gray-500">Status</span>
                <Badge color={STATUS_COLORS[job.status]}>{capitalize(job.status)}</Badge>
              </div>
              <DetailRow label="Department" value={job.department} />
              <DetailRow label="Location" value={job.location} />
              <DetailRow label="Employment Type" value={employmentLabel(job.employment_type)} />
              <DetailRow
                label="Minimum Experience"
                value={job.min_experience_years != null ? `${job.min_experience_years} years` : null}
              />
              <DeadlineRow job={job} />
            </div>
          </Card>

          <Card title="Requirements">
            {job.requirements.length === 0 ? (
              <p className="text-sm text-gray-500">Extracted when the JD is approved.</p>
            ) : (
              <div className="flex flex-col gap-4">
                <RequirementList title="Mandatory" items={mandatory} />
                <RequirementList title="Preferred" items={preferred} />
              </div>
            )}
          </Card>
        </div>
      </div>

      <div className="mt-6">
        <CandidatesCard job={job} />
      </div>

      <JobFormModal
        open={editOpen}
        job={job}
        onClose={() => setEditOpen(false)}
        onSaved={(saved) => {
          setJob(saved);
          setEditOpen(false);
        }}
      />
    </div>
  );
}