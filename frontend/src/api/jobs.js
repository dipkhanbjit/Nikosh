import { apiRequest } from "./client";

export const EMPLOYMENT_TYPES = [
  { value: "full_time", label: "Full-time" },
  { value: "part_time", label: "Part-time" },
  { value: "contract", label: "Contract" },
  { value: "internship", label: "Internship" },
];

export const STATUS_COLORS = {
  draft: "gray",
  approved: "blue",
  posted: "green",
  closed: "red",
};

export const employmentLabel = (value) =>
  EMPLOYMENT_TYPES.find((t) => t.value === value)?.label ?? value;

export const listJobs = () => apiRequest("/jobs");
export const getJob = (id) => apiRequest(`/jobs/${id}`);
export const createJob = (body) => apiRequest("/jobs", { method: "POST", body });
export const updateJob = (id, body) => apiRequest(`/jobs/${id}`, { method: "PATCH", body });
export const deleteJob = (id) => apiRequest(`/jobs/${id}`, { method: "DELETE" });
export const postJob = (id) => apiRequest(`/jobs/${id}/post`, { method: "POST" });

export const getJD = (id) => apiRequest(`/jobs/${id}/jd`);
export const generateJD = (id, prompt) =>
  apiRequest(`/jobs/${id}/jd/generate`, { method: "POST", body: { prompt } });
export const reviewJD = (id, body) =>
  apiRequest(`/jobs/${id}/jd/review`, { method: "POST", body });
export const formatDeadline = (iso) =>
  new Date(iso).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Dhaka",
  });
export const deadlineInputValue = (iso) =>
  iso ? new Date(iso).toLocaleDateString("en-CA", { timeZone: "Asia/Dhaka" }) : "";
export const SCORE_DIMENSIONS = [
  { key: "technical_skills", label: "Technical Skills" },
  { key: "experience", label: "Experience" },
  { key: "qualifications", label: "Qualifications" },
  { key: "cv_jd_match", label: "CV–JD Match" },
];

export const DEFAULT_SCORE_WEIGHTS = {
  technical_skills: 40,
  experience: 25,
  qualifications: 15,
  cv_jd_match: 20,
};

export const getScoreWeights = (id) => apiRequest(`/jobs/${id}/score-weights`);
export const updateScoreWeights = (id, weights) =>
  apiRequest(`/jobs/${id}/score-weights`, { method: "PUT", body: weights });

export const getComparison = (jobId) => apiRequest(`/jobs/${jobId}/comparison`);
