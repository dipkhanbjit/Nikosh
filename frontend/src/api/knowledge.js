import { apiRequest } from "./client";

export const ACCEPTED_TYPES = ".pdf,.docx,.txt,.md";

export const listDocuments = () => apiRequest("/knowledge/documents");

export const uploadDocument = (file) => {
  const form = new FormData();
  form.append("file", file);
  return apiRequest("/knowledge/documents", { method: "POST", body: form });
};

export const deleteDocument = (id) =>
  apiRequest(`/knowledge/documents/${id}`, { method: "DELETE" });