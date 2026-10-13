import { apiRequest } from "./client";

// Candidate login required; the token in the link identifies the interview
export const getJoinInfo = (token) => apiRequest(`/join/${encodeURIComponent(token)}`);

// The logged-in candidate's own interviews
export const getMyInterviews = () => apiRequest("/me/interviews");

// Candidate room: same checks as the join page; 409 ROOM_NOT_OPEN if it is too early
export const getRoomInfo = (token) => apiRequest(`/join/${encodeURIComponent(token)}/room`);
