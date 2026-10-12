export function getUser() {
  const user = localStorage.getItem("user");
  return user ? JSON.parse(user) : null;
}

export function saveUser(user) {
  localStorage.setItem("user", JSON.stringify(user));
}

export function clearUser() {
  localStorage.removeItem("user");
}

export function homePathFor(role) {
  return role === "candidate" ? "/candidate" : "/";
}

// Only allow redirects to a path inside this app (e.g. "/interview/join/abc"), never to another site
export function safeNext(next) {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : null;
}

export function loginPathWithNext(path) {
  return `/login?next=${encodeURIComponent(path)}`;
}
