import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { endInterview, formatDateTime, getInterview, startInterview } from "../api/interviews";
import DeviceCheck from "../components/room/DeviceCheck";
import InterviewerPanel from "../components/room/InterviewerPanel";
import { TranscriptIcon } from "../components/room/icons";
import RoomChat from "../components/room/RoomChat";
import RoomLayout from "../components/room/RoomLayout";
import { Alert, Button, Modal, Spinner } from "../components/ui";
import useAudioCapture from "../hooks/useAudioCapture";
import usePeerConnection from "../hooks/usePeerConnection";
import useRoomChat from "../hooks/useRoomChat";
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

// Interviewer only; filled by live transcription in Module 7
function TranscriptPlaceholder() {
  return (
    <section className="flex h-28 shrink-0 flex-col rounded-2xl border border-gray-200 bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-gray-100 px-4 py-2 text-sm font-semibold text-gray-900">
        <TranscriptIcon className="h-4 w-4 text-gray-500" />
        Live transcript
      </div>
      <p className="flex flex-1 items-center justify-center text-sm text-gray-500">Live transcript will appear here</p>
    </section>
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
  const [chatOpen, setChatOpen] = useState(false);
  const chat = useRoomChat(id, { ownRole: "interviewer", open: chatOpen });

  const room = useRoomSocket(stream ? `/ws/interviews/${id}` : null, {
    onSignal: (data) => call.handleSignal(data),
    onEvent: (message) => {
      call.handleEvent(message);
      if (message.type === "chat") chat.receive(message.message);
      else if (message.type === "room-state") chat.reload(); // catch up after a reconnect
      // ended here, in another tab, or cancelled
      if (message.type === "interview-ended") navigate("/interviews");
    },
  });

  // The call stops when the room is closed
  const { peer, closed, sendSignal, sendChat } = room;
  const call = usePeerConnection({ role: "interviewer", stream: closed ? null : stream, sendSignal });

  // Own microphone to the backend while the interview is running (joining starts it)
  const capturing = stream && interview?.status === "in_progress" && !closed;
  const audio = useAudioCapture({
    path: capturing ? `/ws/audio/interviews/${id}` : null,
    track: stream?.getAudioTracks()[0] || null,
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
        remoteStream={call.remoteStream}
        connectionState={call.connectionState}
        remoteMedia={call.remoteMedia}
        onMediaChange={call.sendMediaState}
        sharing={call.sharing}
        onToggleShare={call.toggleShare}
        onLeave={() => navigate("/interviews")}
        recording={audio.recording}
        connection={{ online: room.online, connected: room.connected, peerReconnecting: room.peerReconnecting }}
        onRetry={() => {
          room.restart();
          audio.restart();
        }}
        endControl={
          <Button variant="danger" onClick={() => setConfirmEnd(true)} className="h-11 rounded-full px-5">
            End interview
          </Button>
        }
        leftPanel={{ title: "Interview tools", content: <InterviewerPanel candidateId={interview.candidate_id} /> }}
        chat={{
          open: chatOpen,
          onToggle: () => setChatOpen(!chatOpen),
          unread: chat.unread,
          content: (
            <RoomChat
              interviewId={id}
              ownRole="interviewer"
              messages={chat.messages}
              loadError={chat.error}
              onSend={sendChat}
              onUploaded={chat.receive}
              offline={!room.online || !room.connected}
              readOnly={!interview.room_open || Boolean(closed)}
            />
          ),
        }}
        bottomPanel={<TranscriptPlaceholder />}
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
