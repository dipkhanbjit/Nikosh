import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { employmentLabel, formatDeadline, getJob, STATUS_COLORS } from "../api/jobs";
import CandidatesCard from "../components/CandidatesCard";
import JobFormModal from "../components/JobFormModal";
import MarkdownView from "../components/MarkdownView";
import PostingCard from "../components/PostingCard";
import ScoringWeightsCard from "../components/ScoringWeightsCard";
import { Alert, Badge, Button, Card, PageHeader, Spinner } from "../components/ui";

const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function RequirementList({ items }) {
  return (
    <ol className="flex flex-col gap-2.5">
      {items.map((r, i) => (
        <li key={i} className="flex gap-3 text-sm text-gray-800">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-xs font-semibold text-indigo-700">
            {i + 1}
          </span>
          <span className="min-w-0 break-words">{r.text}</span>
        </li>
      ))}
    </ol>
  );
}

function DetailRow({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 text-sm">
      <span className="shrink-0 text-gray-500">{label}</span>
      <span className="min-w-0 text-right font-medium text-gray-800">{children || "—"}</span>
    </div>
  );
}

export default function JobDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [scoresVersion, setScoresVersion] = useState(0);

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

  const canEditJD = job.status === "draft" || job.status === "approved";

  return (
    <div className="min-w-0">
      <Button className="mb-4" onClick={() => navigate("/jobs")}>
        ← Back to Jobs
      </Button>

      <PageHeader
        title={job.title}
        subtitle={[job.department, job.location].filter(Boolean).join(" · ")}
        actions={
          <>
            <Button variant="secondary" onClick={() => navigate(`/jobs/${job.id}/comparison`)}>
              Compare candidates
            </Button>
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

      <div className="grid min-w-0 gap-6 lg:grid-cols-3">
        <Card title="Job Description" className="lg:col-span-2">
          {job.description ? (
            <div className="min-w-0 break-words">
              <MarkdownView content={job.description} />
            </div>
          ) : (
            <div className="py-10 text-center">
              <p className="text-sm text-gray-500">No job description yet.</p>
              <p className="mt-1 text-sm text-gray-500">
                Use the JD Assistant to generate one from company documents.
              </p>
            </div>
          )}
        </Card>

        <div className="flex min-w-0 flex-col gap-6">
          <PostingCard job={job} onUpdated={setJob} />

          <Card title="Profile">
            <div className="divide-y divide-gray-100">
              <DetailRow label="Status">
                <Badge color={STATUS_COLORS[job.status]}>{capitalize(job.status)}</Badge>
              </DetailRow>
              <DetailRow label="Department">{job.department}</DetailRow>
              <DetailRow label="Location">{job.location}</DetailRow>
              <DetailRow label="Employment Type">{employmentLabel(job.employment_type)}</DetailRow>
              <DetailRow label="Minimum Experience">
                {job.min_experience_years != null ? `${job.min_experience_years} years` : null}
              </DetailRow>
              <DetailRow label="Application Deadline">
                {job.application_deadline ? (
                  <span className="inline-flex flex-wrap items-center justify-end gap-2">
                    {formatDeadline(job.application_deadline)}
                    {job.applications_closed && <Badge color="red">Closed</Badge>}
                  </span>
                ) : (
                  "Set on posting"
                )}
              </DetailRow>
            </div>
          </Card>

          <Card title="Requirements">
            {job.requirements.length === 0 ? (
              <p className="text-sm text-gray-500">Extracted when the JD is approved.</p>
            ) : (
              <div className="flex flex-col gap-3">
                <p className="text-sm text-gray-500">All requirements are mandatory (gate for eligibility).</p>
                <RequirementList items={job.requirements} />
              </div>
            )}
          </Card>

          {job.requirements.length > 0 && (
            <ScoringWeightsCard job={job} onSaved={() => setScoresVersion((v) => v + 1)} />
          )}
        </div>
      </div>

      <div className="mt-6 min-w-0">
        <CandidatesCard key={scoresVersion} job={job} />
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