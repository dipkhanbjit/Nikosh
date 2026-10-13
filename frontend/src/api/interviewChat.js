import { apiRequest } from "./client";

// In-call chat (interviewer and the interview's own candidate)
export const CHAT_FILE_TYPES = ".txt,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx";
export const CHAT_MAX_FILE_MB = 10;

export const getChatMessages = (interviewId) => apiRequest(`/interviews/${interviewId}/messages`);

export const uploadChatFile = (interviewId, file) => {
  const form = new FormData();
  form.append("file", file);
  return apiRequest(`/interviews/${interviewId}/files`, { method: "POST", body: form });
};

export const chatFileUrl = (interviewId, messageId) => `/api/v1/interviews/${interviewId}/files/${messageId}`;
