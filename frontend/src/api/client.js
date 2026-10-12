import { clearUser, getUser, loginPathWithNext } from "../utils/auth";

export async function apiRequest(path, { method = "GET", body } = {}) {
  const isForm = body instanceof FormData;
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: isForm ? undefined : { "Content-Type": "application/json" },
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => null);

  if (response.status === 401 && getUser()) {
    clearUser();
    // come back to the same page after logging in again
    window.location.href = loginPathWithNext(window.location.pathname + window.location.search);
  }
  if (!response.ok) {
    const error = new Error(data?.error?.message || "Request failed");
    error.status = response.status;
    error.code = data?.error?.code;
    throw error;
  }
  return data;
}