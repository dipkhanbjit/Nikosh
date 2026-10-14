import { apiRequest } from "./client";

// Scheduling assistant (6.6): one open plan or question per job
export const getAssistant = (jobId) => apiRequest(`/jobs/${jobId}/schedule-assistant`);
export const sendAssistantMessage = (jobId, text) =>
  apiRequest(`/jobs/${jobId}/schedule-assistant/messages`, { method: "POST", body: { text } });
export const cancelAssistant = (jobId) =>
  apiRequest(`/jobs/${jobId}/schedule-assistant/cancel`, { method: "POST" });
export const confirmAssistant = (jobId) =>
  apiRequest(`/jobs/${jobId}/schedule-assistant/confirm`, { method: "POST" });
