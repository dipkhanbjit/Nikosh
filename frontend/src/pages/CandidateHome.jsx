import { useNavigate } from "react-router-dom";

import { apiRequest } from "../api/client";
import { Button, Card } from "../components/ui";
import { clearUser, getUser } from "../utils/auth";

export default function CandidateHome() {
  const navigate = useNavigate();
  const user = getUser();

  async function handleLogout() {
    await apiRequest("/auth/logout", { method: "POST" }).catch(() => {});
    clearUser();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex h-16 items-center justify-between border-b border-gray-200 bg-white px-6">
        <span className="text-xl font-bold text-indigo-600">Nikosh</span>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-600">{user.full_name}</span>
          <Button variant="secondary" onClick={handleLogout}>
            Logout
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-3xl p-6">
        <Card title="My Interviews">
          <p className="text-sm text-gray-500">No interviews scheduled yet.</p>
        </Card>
      </main>
    </div>
  );
}
