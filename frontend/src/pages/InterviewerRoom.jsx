import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { endInterview, formatDateTime, getInterview, startInterview } from "../api/interviews";
import DeviceCheck from "../components/room/DeviceCheck";
import InterviewerPanel from "../components/room/InterviewerPanel";
import RoomLayout from "../components/room/RoomLayout";
import { Alert, Button, Modal, Spinner } from "../components/ui";
import useRoomSocket from "../hooks/useRoomSocket";

function Message({ children }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="flex w-full max-w-md flex-col gap-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        {children}
        <Link to="/interviews" className="text-sm font-medium text-indigo-600 hover:underline">
          Back to interviews
        </Link>
      </div>
    </div>
  );
}

// Kept for the Interviewer Co-pilot chat (F8): ChatPanel goes here
function CopilotPlaceholder() {
  return (
    <div className="flex h-40 shrink-0 items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white text-sm text-gray-500">
      Interviewer Co-pilot (coming soon)
    </div>
  );
}

export default function InterviewerRoom() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [interview, setInterview] = useState(null);
  const [error, setError] = useState("");
  const [stream, setStream] = useState(null);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [ending, setEnding] = useState(false);
  const [endError, setEndError] = useState("");

  const { peer, closed } = useRoomSocket(stream ? `/ws/interviews/${id}` : null, {
    // ended here, in another tab, or cancelled
    onEvent: (message) => message.type === "interview-ended" && navigate("/interviews"),
  });

  useEffect(() => {
    getInterview(id)
      .then(setInterview)
      .catch((err) => setError(err.message));
  }, [id]);

  // The room socket was closed for good (another tab took over, or the room is no longer open)
  let roomClosed = "";
  if (closed?.code === 4000) roomClosed = "This interview room was opened in another tab or window.";
  else if (closed) roomClosed = closed.reason || "The interview room was closed.";

  if (error || roomClosed) {
    return (
      <Message>
        <Alert type={roomClosed ? "info" : "error"}>{error || roomClosed}</Alert>
      </Message>
    );
  }

  if (!interview) {
    return (
      <div className="flex min-h-screen items-center justify-center text-indigo-600">
        <Spinner />
      </div>
    );
  }

  if (!interview.room_open) {
    return (
      <Message>
        <Alert type="info">
          {interview.status === "scheduled"
            ? `The interview room opens 10 minutes before the start (${formatDateTime(interview.scheduled_at)}).`
            : "This interview is no longer open."}
        </Alert>
      </Message>
    );
  }

  const candidate = interview.candidate_name || "the candidate";

  if (!stream) {
    const join = async (s) => {
      setInterview(await startInterview(id)); // scheduled → in_progress
      setStream(s);
    };
    return (
      <DeviceCheck
        title="Check your camera and microphone"
        subtitle={`${interview.job_title} · ${candidate}`}
        onJoin={join}
        onBack={() => navigate("/interviews")}
      />
    );
  }

  const handleEnd = async () => {
    setEnding(true);
    setEndError("");
    try {
      await endInterview(id);
      navigate("/interviews");
    } catch (err) {
      setEndError(err.message);
      setEnding(false);
    }
  };

  return (
    <>
      <RoomLayout
        jobTitle={interview.job_title}
        candidateName={interview.candidate_name}
        startedAt={interview.started_at}
        waitingFor={candidate}
        peerName={peer?.name}
        stream={stream}
        onLeave={() => navigate("/interviews")}
        extraControls={
          <Button variant="danger" onClick={() => setConfirmEnd(true)}>
            End interview
          </Button>
        }
        sidePanel={<InterviewerPanel candidateId={interview.candidate_id} />}
        bottomPanel={<CopilotPlaceholder />}
      />

      <Modal
        open={confirmEnd}
        title="End Interview"
        onClose={() => !ending && setConfirmEnd(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmEnd(false)} disabled={ending}>
              Back
            </Button>
            <Button variant="danger" onClick={handleEnd} loading={ending}>
              End interview
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-gray-700">
            End the interview with <span className="font-semibold">{candidate}</span>? It will be marked as completed
            and cannot be restarted.
          </p>
          {endError && <Alert type="error">{endError}</Alert>}
        </div>
      </Modal>
    </>
  );
}
