import { useState } from "react";

import { postJob } from "../api/jobs";
import { Alert, Badge, Button, Card } from "./ui";

function Row({ label, children }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-gray-800">{children}</span>
    </div>
  );
}

function LinkButton({ href, children }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="mt-1 inline-flex justify-center rounded-md border border-gray-300 px-4 py-2 font-medium text-gray-700 hover:bg-gray-50"
    >
      {children}
    </a>
  );
}

function PlatformBlock({ name, postedAt, url }) {
  return (
    <div className="flex flex-col gap-2 text-sm">
      <Row label="Platform">{name}</Row>
      <Row label="Posted">{postedAt ? new Date(postedAt).toLocaleString() : "—"}</Row>
      <LinkButton href={url}>View Post</LinkButton>
    </div>
  );
}

function FormBlock({ job }) {
  const closed = Boolean(job.form_closed_at);
  return (
    <div className="flex flex-col gap-2 text-sm">
      <Row label="Application Form">
        <Badge color={closed ? "red" : "green"}>{closed ? "Closed" : "Open"}</Badge>
      </Row>
      {closed && <Row label="Closed">{new Date(job.form_closed_at).toLocaleString()}</Row>}
      <LinkButton href={job.form_url}>Open Form</LinkButton>
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
  const failure = job.form_error
    ? `Application form could not be created: ${job.form_error}`
    : job.posting_error
      ? `Posting failed: ${job.posting_error}`
      : "";

  return (
    <Card title="Job Posting">
      <div className="flex flex-col gap-4">
        {error && <Alert type="error">{error}</Alert>}

        {job.form_url && <FormBlock job={job} />}

        {isPosted ? (
          <div className={job.form_url ? "border-t border-gray-100 pt-4" : ""}>
            <PlatformBlock name="Blogger" postedAt={job.posted_at} url={job.posted_url} />
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {failure ? (
              <Alert type="error">{failure}</Alert>
            ) : (
              <p className="text-sm text-gray-500">This JD has not been posted yet.</p>
            )}
            <Button onClick={handlePost} loading={posting}>
              {failure ? "Retry Posting" : "Post Job"}
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