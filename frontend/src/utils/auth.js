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
