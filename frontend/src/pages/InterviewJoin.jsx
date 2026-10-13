import { useCallback, useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";

import { apiRequest } from "../api/client";
import { formatDateTime } from "../api/interviews";
import { getJoinInfo } from "../api/join";
import { Alert, Badge, Button, Spinner } from "../components/ui";
import { clearUser, getUser, loginPathWithNext } from "../utils/auth";

const COMPANY_NAME = "Nirvik Technology"; // shown before the API answers or when the link is invalid

function Detail({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="text-right font-medium text-gray-800">{value}</span>
    </div>
  );
}

export default function InterviewJoin() {
  const { token } = useParams();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const loggedIn = Boolean(getUser());
  const [info, setInfo] = useState(null);
  const [invalid, setInvalid] = useState(false);
  const [wrongAccount, setWrongAccount] = useState(""); // message when logged in with the wrong account
  const [error, setError] = useState("");

  const load = useCallback(() => {
    if (!loggedIn) return;
    setError("");
    getJoinInfo(token)
      .then(setInfo)
      .catch((err) => {
        if (err.status === 404 || err.status === 410) setInvalid(true);
        else if (err.code === "NOT_YOUR_INTERVIEW")
          setWrongAccount("This interview belongs to another account. Please log in with the account it was sent to.");
        else if (err.status === 403) setWrongAccount("Please log in with your candidate account to join this interview.");
        else setError("Could not load your interview. Please refresh the page.");
      });
  }, [token, loggedIn]);

  useEffect(load, [load]);

  const switchAccount = async () => {
    await apiRequest("/auth/logout", { method: "POST" }).catch(() => {});
    clearUser();
    navigate(loginPathWithNext(pathname), { replace: true });
  };

  // When the link opens later, check again at the opening time so the page updates by itself
  useEffect(() => {
    if (info?.status !== "too_early") return undefined;
    const wait = new Date(info.opens_at) - new Date();
    if (wait > 2 ** 31 - 1) return undefined; // too far ahead for setTimeout
    const timer = setTimeout(load, Math.max(wait, 0) + 1000);
    return () => clearTimeout(timer);
  }, [info, load]);

  if (!loggedIn) return <Navigate to={loginPathWithNext(pathname)} replace />;

  const loading = !info && !invalid && !wrongAccount && !error;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">
          {info?.company_name || COMPANY_NAME}
        </p>
        <h1 className="mt-1 text-xl font-semibold text-gray-900">Interview</h1>

        <div className="mt-5">
          {loading && (
            <div className="flex justify-center py-6 text-indigo-600">
              <Spinner />
            </div>
          )}

          {error && <Alert type="error">{error}</Alert>}

          {wrongAccount && (
            <div className="flex flex-col gap-3">
              <Alert type="error">{wrongAccount}</Alert>
              <Button variant="secondary" onClick={switchAccount}>
                Log out and switch account
              </Button>
            </div>
          )}

          {invalid && (
            <Alert type="error">
              This link is no longer valid. If you think this is a mistake, please contact the recruiter.
            </Alert>
          )}

          {info && (
            <>
              <div className="divide-y divide-gray-100 border-y border-gray-100">
                <Detail label="Position" value={info.job_title} />
                <Detail label="Candidate" value={info.candidate_name || "—"} />
                <Detail label="Date & time" value={`${formatDateTime(info.scheduled_at)} (GMT+6)`} />
                <Detail label="Duration" value={`${info.duration_minutes} minutes`} />
              </div>

              <div className="mt-5">
                {info.status === "too_early" ? (
                  <Alert type="info">
                    The interview room opens at <span className="font-semibold">{formatDateTime(info.opens_at)}</span>{" "}
                    (10 minutes before the start). Please come back then; this page will update by itself.
                  </Alert>
                ) : (
                  <div className="flex flex-col items-center gap-3 rounded-md border border-green-200 bg-green-50 p-4 text-center">
                    <Badge color="green">Ready</Badge>
                    <p className="text-sm text-green-800">Your interview room is open.</p>
                    <Button onClick={() => navigate(`/interview/join/${token}/room`)}>Enter interview room</Button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
