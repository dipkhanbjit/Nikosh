import { apiRequest } from "./client";

// Interviewer co-pilot (interviewer only)
export const copilotChat = (interviewId, message, history) =>
  apiRequest(`/interviews/${interviewId}/copilot/chat`, { method: "POST", body: { message, history } });

export const getSuggestedQuestions = (interviewId) => apiRequest(`/interviews/${interviewId}/copilot/questions`);

export const generateSuggestedQuestions = (interviewId) =>
  apiRequest(`/interviews/${interviewId}/copilot/questions`, { method: "POST" });
