import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { deleteJob, employmentLabel, listJobs, STATUS_COLORS } from "../api/jobs";
import JobFormModal from "../components/JobFormModal";
import { Alert, Badge, Button, Modal, PageHeader, Spinner, Table } from "../components/ui";

export default function Jobs() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editingJob, setEditingJob] = useState(null);
  const [deletingJob, setDeletingJob] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    listJobs()
      .then(setJobs)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const openCreate = () => {
    setEditingJob(null);
    setFormOpen(true);
  };

  const openEdit = (job) => {
    setEditingJob(job);
    setFormOpen(true);
  };

  const handleSaved = (saved) => {
    setFormOpen(false);
    if (editingJob) {
      setJobs(jobs.map((j) => (j.id === saved.id ? saved : j)));
    } else {
      navigate(`/jobs/${saved.id}`);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteJob(deletingJob.id);
      setJobs(jobs.filter((j) => j.id !== deletingJob.id));
      setDeletingJob(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting(false);
    }
  };

  const columns = [
    {
      key: "title",
      label: "Job Title",
      render: (job) => (
        <div>
          <Link to={`/jobs/${job.id}`} className="font-medium text-indigo-600 hover:underline">
            {job.title}
          </Link>
          {job.department && <p className="text-xs text-gray-500">{job.department}</p>}
        </div>
      ),
    },
    { key: "location", label: "Location", render: (job) => job.location || "—" },
    { key: "employment_type", label: "Type", render: (job) => employmentLabel(job.employment_type) },
    {
      key: "min_experience_years",
      label: "Experience",
      render: (job) => (job.min_experience_years != null ? `${job.min_experience_years}+ yrs` : "—"),
    },
    {
      key: "status",
      label: "Status",
      render: (job) => (
        <Badge color={STATUS_COLORS[job.status]}>
          {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
        </Badge>
      ),
    },
    {
      key: "created_at",
      label: "Created",
      render: (job) => new Date(job.created_at).toLocaleDateString(),
    },
    {
      key: "actions",
      label: "",
      render: (job) => (
        <div className="flex justify-end gap-2">
          <Button variant="secondary" className="px-3 py-1" onClick={() => openEdit(job)}>
            Edit
          </Button>
          <Button variant="secondary" className="px-3 py-1 text-red-600" onClick={() => setDeletingJob(job)}>
            Delete
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Jobs"
        subtitle="Manage job profiles and generate job descriptions."
        actions={<Button onClick={openCreate}>New Job</Button>}
      />

      {error && (
        <div className="mb-4">
          <Alert type="error">{error}</Alert>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12 text-indigo-600">
          <Spinner size="lg" />
        </div>
      ) : (
        <Table columns={columns} data={jobs} emptyMessage="No jobs yet. Create your first job profile." />
      )}

      <JobFormModal
        open={formOpen}
        job={editingJob}
        onClose={() => setFormOpen(false)}
        onSaved={handleSaved}
      />

      <Modal
        open={Boolean(deletingJob)}
        title="Delete Job"
        onClose={() => setDeletingJob(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeletingJob(null)}>
              Cancel
            </Button>
            <Button variant="danger" loading={deleting} onClick={handleDelete}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">
          Delete <span className="font-semibold">{deletingJob?.title}</span>? All its candidates
          and their CV files will be permanently removed.
        </p>
      </Modal>
    </div>
  );
}