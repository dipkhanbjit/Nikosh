import { clearUser, getUser } from "../utils/auth";

export async function apiRequest(path, { method = "GET", body } = {}) {
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => null);

  if (response.status === 401 && getUser()) {
    clearUser();
    window.location.href = "/login";
  }
  if (!response.ok) {
    throw new Error(data?.error?.message || "Request failed");
  }
  return data;
}
