import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { INTERVIEW_STATUS, formatDateTime, formatDuration, getTranscript } from "../api/interviews";
import RecordingsList from "../components/RecordingsList";
import TranscriptBubble from "../components/room/TranscriptBubble";
import { Alert, Badge, Button, Card, PageHeader, Spinner } from "../components/ui";

function Detail({ label, children }) {
  return (
    <div>
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-900">{children}</dd>
    </div>
  );
}

// Interviewer only (7.4.2): saved transcript and recordings of one interview
export default function InterviewTranscript() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null); // { status, message }

  useEffect(() => {
    getTranscript(id)
      .then(setData)
      .catch((err) => setError({ status: err.status, message: err.message }));
  }, [id]);

  const back = (
    <Button variant="secondary" onClick={() => navigate("/interviews")}>
      Back to interviews
    </Button>
  );

  if (error) {
    return (
      <div>
        <PageHeader title="Interview transcript" actions={back} />
        <Alert type="error">{error.status === 404 ? "Interview not found." : error.message}</Alert>
      </div>
    );
  }

  if (!data) return <Spinner />;

  const [statusColor, statusLabel] = INTERVIEW_STATUS[data.status] ?? ["gray", data.status];
  const labels = { interviewer: "Interviewer", candidate: data.candidate_name || "Candidate" };
  const duration =
    data.started_at && data.ended_at ? (new Date(data.ended_at) - new Date(data.started_at)) / 1000 : null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Interview transcript" actions={back} />

      <Card>
        <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Detail label="Candidate">{data.candidate_name || "—"}</Detail>
          <Detail label="Job">{data.job_title}</Detail>
          <Detail label="Status">
            <Badge color={statusColor}>{statusLabel}</Badge>
          </Detail>
          <Detail label="Started">{data.started_at ? formatDateTime(data.started_at) : "—"}</Detail>
          <Detail label="Duration">{duration !== null ? formatDuration(duration) : "—"}</Detail>
          <Detail label="Turns">{data.turn_count}</Detail>
          <div className="col-span-2">
            <Detail label="Talk time">
              Interviewer {formatDuration(data.talk_time_s.interviewer)} · {labels.candidate}{" "}
              {formatDuration(data.talk_time_s.candidate)}
            </Detail>
          </div>
        </dl>
      </Card>

      <Card title="Transcript">
        {data.turns.length === 0 ? (
          <p className="text-sm text-gray-500">No transcript was recorded for this interview.</p>
        ) : (
          <div className="flex h-[60vh] flex-col gap-2 overflow-y-auto rounded-lg bg-gray-50 p-4">
            {data.turns.map((turn) => (
              <TranscriptBubble
                key={turn.seq}
                speaker={turn.speaker}
                label={labels[turn.speaker] || turn.speaker}
                startS={turn.start_s}
                text={turn.text}
                incomplete={turn.incomplete}
              />
            ))}
          </div>
        )}
      </Card>

      <Card title="Recordings">
        <RecordingsList key={data.interview_id} interviewId={data.interview_id} />
      </Card>
    </div>
  );
}
