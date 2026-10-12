import { apiRequest } from "./client";

export const INTERVIEW_STATUS = {
  scheduled: ["blue", "Scheduled"],
  in_progress: ["yellow", "In progress"],
  completed: ["green", "Completed"],
  cancelled: ["gray", "Cancelled"],
  no_show: ["red", "No-show"],
};

export const ACTIVE_INTERVIEW_STATUSES = ["scheduled", "in_progress"];

const DHAKA_OFFSET = "+06:00";

// "2026-10-14" + "15:00" → "2026-10-14T15:00:00+06:00" (backend needs a timezone offset)
export const toScheduledAt = (date, time) => `${date}T${time}:00${DHAKA_OFFSET}`;

export const isPast = (date, time) => new Date(toScheduledAt(date, time)) <= new Date();

export const formatDateTime = (iso) =>
  new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Dhaka",
  });

// Shortlist (LangGraph review workflow)
export const getShortlist = (jobId) => apiRequest(`/jobs/${jobId}/shortlist`);
export const startShortlist = (jobId, topN) =>
  apiRequest(`/jobs/${jobId}/shortlist`, { method: "POST", body: { top_n: topN } });
export const reviewShortlist = (jobId, body) =>
  apiRequest(`/jobs/${jobId}/shortlist/review`, { method: "POST", body });

// Interviews
export const listJobInterviews = (jobId) => apiRequest(`/jobs/${jobId}/interviews`);
export const listInterviews = (status) =>
  apiRequest(`/interviews${status ? `?status=${status}` : ""}`);
export const scheduleInterview = (jobId, body) =>
  apiRequest(`/jobs/${jobId}/interviews`, { method: "POST", body });
export const cancelInterview = (id, reason) =>
  apiRequest(`/interviews/${id}/cancel`, { method: "POST", body: { reason } });
export const markNoShow = (id) => apiRequest(`/interviews/${id}/no-show`, { method: "POST" });
// New password + email again; retries the calendar event if it failed
export const resendInvitation = (id) => apiRequest(`/interviews/${id}/resend-invitation`, { method: "POST" });

// Schedule / resend response → what the credentials modal shows (once)
export const credentialsFrom = (interview) => ({
  name: interview.candidate_name || "the candidate",
  email: interview.credentials.email,
  password: interview.credentials.password,
  joinUrl: interview.join_url,
  invitationError: interview.invitation_error,
});
