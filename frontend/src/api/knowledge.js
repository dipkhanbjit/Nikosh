import { apiRequest } from "./client";

export const ACCEPTED_TYPES = ".pdf,.docx,.txt,.md";

export const listDocuments = () => apiRequest("/knowledge/documents");

export const DOCUMENT_KINDS = {
  company: { label: "Company", color: "indigo" },
  reference: { label: "Reference", color: "purple" },
};

export const uploadDocument = (file, kind = "company") => {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  return apiRequest("/knowledge/documents", { method: "POST", body: form });
};

export const deleteDocument = (id) =>
  apiRequest(`/knowledge/documents/${id}`, { method: "DELETE" });