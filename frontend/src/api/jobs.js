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