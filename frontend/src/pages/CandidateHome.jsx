import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiRequest } from "../api/client";
import { INTERVIEW_STATUS, formatDateTime } from "../api/interviews";
import { getMyInterviews } from "../api/join";
import { Alert, Badge, Button, Card, Spinner, Table } from "../components/ui";
import { clearUser, getUser } from "../utils/auth";

const JOINABLE = ["scheduled", "in_progress"];

export default function CandidateHome() {
  const navigate = useNavigate();
  const user = getUser();
  const [interviews, setInterviews] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMyInterviews()
      .then(setInterviews)
      .catch((err) => setError(err.message));
  }, []);

  async function handleLogout() {
    await apiRequest("/auth/logout", { method: "POST" }).catch(() => {});
    clearUser();
    navigate("/login", { replace: true });
  }

  // join_url is a full URL; open it inside the app by its path
  const openInterview = (url) => navigate(new URL(url).pathname);

  const columns = [
    { key: "job_title", label: "Position", render: (iv) => <span className="font-medium text-gray-800">{iv.job_title}</span> },
    { key: "scheduled_at", label: "Date & Time", render: (iv) => `${formatDateTime(iv.scheduled_at)} (GMT+6)` },
    { key: "duration", label: "Duration", render: (iv) => `${iv.duration_minutes} min` },
    {
      key: "status",
      label: "Status",
      render: (iv) => {
        const [color, label] = INTERVIEW_STATUS[iv.status] ?? ["gray", iv.status];
        return <Badge color={color}>{label}</Badge>;
      },
    },
    {
      key: "action",
      label: "",
      render: (iv) =>
        iv.status === "completed" ? (
          <p className="max-w-[16rem] text-sm text-gray-600">
            Thank you for attending. The hiring team will contact you.
          </p>
        ) : (
          <div className="flex justify-end">
            <Button
              className="px-3 py-1"
              onClick={() => openInterview(iv.join_url)}
              disabled={!JOINABLE.includes(iv.status)}
            >
              Join
            </Button>
          </div>
        ),
    },
  ];

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
      <main className="mx-auto max-w-4xl p-6">
        <Card title="My Interviews">
          {error && <Alert type="error">{error}</Alert>}
          {!interviews && !error && (
            <div className="flex justify-center py-6 text-indigo-600">
              <Spinner />
            </div>
          )}
          {interviews && (
            <Table
              columns={columns}
              data={interviews.map((iv) => ({ ...iv, id: iv.join_url }))}
              emptyMessage="No interviews scheduled yet."
            />
          )}
        </Card>
      </main>
    </div>
  );
}
