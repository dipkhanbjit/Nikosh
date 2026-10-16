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

export const deleteCandidate = (id, fromDrive = false) =>
  apiRequest(`/candidates/${id}${fromDrive ? "?drive=true" : ""}`, { method: "DELETE" });

export const cvUrl = (id) => `/api/v1/candidates/${id}/cv`;

export const getCVText = (id) => apiRequest(`/candidates/${id}/text`);

export const startScreening = (jobId) =>
  apiRequest(`/jobs/${jobId}/screening`, { method: "POST" });

export const getScreening = (jobId) => apiRequest(`/jobs/${jobId}/screening`);

export const includeCandidate = (id, reason) =>
  apiRequest(`/candidates/${id}/include`, { method: "POST", body: { reason } });

export const excludeCandidate = (id, reason) =>
  apiRequest(`/candidates/${id}/exclude`, { method: "POST", body: { reason } });

export const getAssessment = (id) => apiRequest(`/candidates/${id}/assessment`);
export const runAssessment = (id) => apiRequest(`/candidates/${id}/assessment`, { method: "POST" });

// Standalone HTML report (opened or downloaded directly; the cookie authenticates it)
export const reportUrl = (id, { download = false, print = false } = {}) => {
  const params = new URLSearchParams();
  if (download) params.set("download", "true");
  if (print) params.set("print", "true");
  const query = params.toString();
  return `/api/v1/candidates/${id}/report.html${query ? `?${query}` : ""}`;
};
