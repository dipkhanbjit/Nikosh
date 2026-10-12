import { useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { apiRequest } from "../api/client";
import { Alert, Button, Input } from "../components/ui";
import { getUser, homePathFor, safeNext, saveUser } from "../utils/auth";

export default function Login() {
  const navigate = useNavigate();
  const next = safeNext(useSearchParams()[0].get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const user = getUser();
  if (user) return <Navigate to={next || homePathFor(user.role)} replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await apiRequest("/auth/login", {
        method: "POST",
        body: { email, password },
      });
      saveUser(data);
      navigate(next || homePathFor(data.role), { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-gray-200 bg-white p-6 shadow-sm"
      >
        <div>
          <h1 className="text-2xl font-bold text-indigo-600">Nikosh</h1>
          <p className="mt-1 text-sm text-gray-500">Sign in to continue</p>
        </div>
        {error && <Alert type="error">{error}</Alert>}
        <Input
          label="Email"
          name="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          label="Password"
          name="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button type="submit" loading={loading} className="w-full">
          Sign in
        </Button>
      </form>
    </div>
  );
}
