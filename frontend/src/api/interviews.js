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
export const getInterview = (id) => apiRequest(`/interviews/${id}`);
// Interviewer joins the room (scheduled → in_progress) / ends the interview (→ completed)
export const startInterview = (id) => apiRequest(`/interviews/${id}/start`, { method: "POST" });
export const endInterview = (id) => apiRequest(`/interviews/${id}/end`, { method: "POST" });
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

// Recorded audio parts (completed interviews); the URL is used directly by an <audio> element
export const listAudioParts = (id) => apiRequest(`/interviews/${id}/audio`);
export const audioPartUrl = (id, partId) => `/api/v1/interviews/${id}/audio/${partId}`;

// Transcript (7.4)
export const getTranscript = (id) => apiRequest(`/interviews/${id}/transcript`);

// Analysis (8.4): POST starts a run in the background, GET is polled for the result
export const getAnalysis = (id) => apiRequest(`/interviews/${id}/analysis`);
export const runAnalysis = (id) => apiRequest(`/interviews/${id}/analysis`, { method: "POST" });

// 312.4 → "05:12"; one hour or more → "1:02:05"
export const formatClock = (seconds) => {
  const total = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(total / 3600);
  const mm = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};

// 312.4 → "5m 12s"; one hour or more → "1h 02m 05s"
export const formatDuration = (seconds) => {
  const total = Math.max(0, Math.round(seconds || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const ss = String(total % 60).padStart(2, "0");
  return h ? `${h}h ${String(m).padStart(2, "0")}m ${ss}s` : `${m}m ${ss}s`;
};
