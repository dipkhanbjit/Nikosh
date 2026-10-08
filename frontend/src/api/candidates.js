import { apiRequest } from "./client";

export const ACCEPTED_CV_TYPES = ".pdf,.docx";

export const listCandidates = (jobId) => apiRequest(`/jobs/${jobId}/candidates`);

export const countNewApplications = (jobId) => apiRequest(`/jobs/${jobId}/applications/new`);

export const syncApplications = (jobId) =>
  apiRequest(`/jobs/${jobId}/applications/sync`, { method: "POST" });

export const uploadCVs = (jobId, files) => {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return apiRequest(`/jobs/${jobId}/candidates/upload`, { method: "POST", body: form });
};

export const deleteCandidate = (id) => apiRequest(`/candidates/${id}`, { method: "DELETE" });

export const cvUrl = (id) => `/api/v1/candidates/${id}/cv`;

export const extractCVs = (jobId) =>
  apiRequest(`/jobs/${jobId}/candidates/extract`, { method: "POST" });

export const getCVText = (id) => apiRequest(`/candidates/${id}/text`);

export const parseCVs = (jobId) =>
  apiRequest(`/jobs/${jobId}/candidates/parse`, { method: "POST" });