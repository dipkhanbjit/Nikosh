import { useState } from "react";

import { postJob } from "../api/jobs";
import { Alert, Button, Card } from "./ui";

function PlatformBlock({ name, postedAt, url }) {
  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex justify-between">
        <span className="text-gray-500">Platform</span>
        <span className="font-medium text-gray-800">{name}</span>
      </div>
      <div className="flex justify-between">
        <span className="text-gray-500">Posted</span>
        <span className="font-medium text-gray-800">
          {postedAt ? new Date(postedAt).toLocaleString() : "—"}
        </span>
      </div>
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="mt-1 inline-flex justify-center rounded-md border border-gray-300 px-4 py-2 font-medium text-gray-700 hover:bg-gray-50"
      >
        View Post
      </a>
    </div>
  );
}

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

  const isPosted = job.status === "posted";

  return (
    <Card title="Job Posting">
      <div className="flex flex-col gap-4">
        {error && <Alert type="error">{error}</Alert>}

        {isPosted ? (
          <PlatformBlock name="Blogger" postedAt={job.posted_at} url={job.posted_url} />
        ) : (
          <div className="flex flex-col gap-3">
            {job.posting_error ? (
              <Alert type="error">Posting failed: {job.posting_error}</Alert>
            ) : (
              <p className="text-sm text-gray-500">This JD has not been posted yet.</p>
            )}
            <Button onClick={handlePost} loading={posting}>
              {job.posting_error ? "Retry Posting" : "Post Job"}
            </Button>
          </div>
        )}

        {isPosted && (
          <div className="border-t border-gray-100 pt-4">
            {job.telegram_url ? (
              <PlatformBlock name="Telegram" postedAt={job.telegram_posted_at} url={job.telegram_url} />
            ) : (
              <div className="flex flex-col gap-3">
                <Alert type="error">
                  Telegram announcement failed{job.telegram_error ? `: ${job.telegram_error}` : "."}
                </Alert>
                <Button variant="secondary" onClick={handlePost} loading={posting}>
                  Retry Telegram
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}