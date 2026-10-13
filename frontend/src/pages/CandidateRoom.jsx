import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";

import { getRoomInfo } from "../api/join";
import DeviceCheck from "../components/room/DeviceCheck";
import RoomChat from "../components/room/RoomChat";
import RoomLayout from "../components/room/RoomLayout";
import { Alert, Spinner } from "../components/ui";
import usePeerConnection from "../hooks/usePeerConnection";
import useRoomChat from "../hooks/useRoomChat";
import useRoomSocket from "../hooks/useRoomSocket";
import { getUser } from "../utils/auth";

const ENDED_MESSAGES = {
  completed: "The interview has ended. Thank you for attending.",
  cancelled: "This interview was cancelled.",
  no_show: "The interview time has passed.",
};

function roomError(err) {
  if (err.status === 410) return "This interview has ended or the link is no longer valid.";
  if (err.code === "ROOM_NOT_OPEN") return "The interview room is not open yet.";
  if (err.code === "NOT_YOUR_INTERVIEW") return "This interview belongs to another account.";
  if (err.status === 404) return "This interview link is not valid.";
  return "Could not open the interview room. Please try again.";
}

// The room socket was closed for good (not by an "interview-ended" message)
function closedMessage({ code, reason }) {
  if (code === 4000) return "The interview room was opened in another tab or window.";
  if (code === 4410 || code === 1000) return ENDED_MESSAGES.completed;
  if (code === 4409) return "The interview room is not open.";
  return reason || "The connection to the interview room was closed.";
}

function Message({ token, children }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="flex w-full max-w-md flex-col gap-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        {children}
        <Link to={`/interview/join/${token}`} className="text-sm font-medium text-indigo-600 hover:underline">
          Back to interview details
        </Link>
      </div>
    </div>
  );
}

export default function CandidateRoom() {
  const { token } = useParams();
  const navigate = useNavigate();
  const loggedIn = Boolean(getUser());
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [stream, setStream] = useState(null);
  const [endedReason, setEndedReason] = useState("");
  const [chatOpen, setChatOpen] = useState(false);
  const chat = useRoomChat(info?.interview_id, { ownRole: "candidate", open: chatOpen });

  const { peer, closed, sendSignal, sendChat } = useRoomSocket(stream ? `/ws/join/${token}` : null, {
    onSignal: (data) => call.handleSignal(data),
    onEvent: (message) => {
      call.handleEvent(message);
      if (message.type === "chat") chat.receive(message.message);
      if (message.type === "room-state") chat.reload(); // catch up after a reconnect
      if (message.type === "room-state" || message.type === "interview-started") {
        setInfo((current) => ({ ...current, started_at: message.started_at, status: message.status || "in_progress" }));
      } else if (message.type === "interview-ended") {
        setEndedReason(message.reason || "completed");
      }
    },
  });

  // The call stops when the interview ends or the room is closed
  const call = usePeerConnection({ role: "candidate", stream: endedReason || closed ? null : stream, sendSignal });

  useEffect(() => {
    if (!loggedIn) return;
    getRoomInfo(token)
      .then(setInfo)
      .catch((err) => setError(roomError(err)));
  }, [token, loggedIn]);

  // The join page handles logging in and coming back
  if (!loggedIn) return <Navigate to={`/interview/join/${token}`} replace />;

  const roomClosed = endedReason
    ? ENDED_MESSAGES[endedReason] || ENDED_MESSAGES.completed
    : closed && closedMessage(closed);

  if (error || roomClosed) {
    return (
      <Message token={token}>
        <Alert type={roomClosed ? "info" : "error"}>{error || roomClosed}</Alert>
      </Message>
    );
  }

  if (!info) {
    return (
      <div className="flex min-h-screen items-center justify-center text-indigo-600">
        <Spinner />
      </div>
    );
  }

  if (!stream) {
    const join = async (s) => {
      setInfo(await getRoomInfo(token)); // check again that the room is still open
      setStream(s);
    };
    return (
      <DeviceCheck
        title="Check your camera and microphone"
        subtitle={`${info.job_title} interview`}
        onJoin={join}
        onBack={() => navigate(`/interview/join/${token}`)}
      />
    );
  }

  return (
    <RoomLayout
      jobTitle={info.job_title}
      candidateName={info.candidate_name}
      startedAt={info.started_at}
      waitingFor="the interviewer"
      peerName={peer?.name}
      stream={stream}
      remoteStream={call.remoteStream}
      connectionState={call.connectionState}
      remoteMedia={call.remoteMedia}
      onMediaChange={call.sendMediaState}
      sharing={call.sharing}
      onToggleShare={call.toggleShare}
      onLeave={() => navigate(`/interview/join/${token}`)}
      chat={{
        open: chatOpen,
        onToggle: () => setChatOpen(!chatOpen),
        unread: chat.unread,
        content: (
          <RoomChat
            interviewId={info.interview_id}
            ownRole="candidate"
            messages={chat.messages}
            loadError={chat.error}
            onSend={sendChat}
            onUploaded={chat.receive}
            readOnly={Boolean(endedReason || closed)}
          />
        ),
      }}
    />
  );
}
