import { useState } from "react";

import { postJob } from "../api/jobs";
import { Alert, Button, Card } from "./ui";

export default function PostingCard({ job, onUpdated }) {
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState("");

  if (job.status !== "approved" && job.status !== "posted") return null;

  const handlePost = async () => {
    setPosting(true);
    setError("");
    try {
      onUpdated(await postJob(job.id));
    } catch (err) {
      setError(err.message);
    } finally {
      setPosting(false);
    }
  };

  return (
    <Card title="Job Posting">
      {job.status === "posted" ? (
        <div className="flex flex-col gap-3 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Platform</span>
            <span className="font-medium text-gray-800">Telegram</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Posted</span>
            <span className="font-medium text-gray-800">
              {job.posted_at ? new Date(job.posted_at).toLocaleString() : "—"}
            </span>
          </div>
          {job.posted_url && (
            <a
              href={job.posted_url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex justify-center rounded-md border border-gray-300 px-4 py-2 font-medium text-gray-700 hover:bg-gray-50"
            >
              View Post
            </a>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {job.posting_error ? (
            <Alert type="error">Posting failed: {job.posting_error}</Alert>
          ) : (
            <p className="text-sm text-gray-500">This JD has not been posted yet.</p>
          )}
          {error && <Alert type="error">{error}</Alert>}
          <Button onClick={handlePost} loading={posting}>
            {job.posting_error ? "Retry Posting" : "Post to Telegram"}
          </Button>
        </div>
      )}
    </Card>
  );
}