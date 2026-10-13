import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";

import { getRoomInfo } from "../api/join";
import DeviceCheck from "../components/room/DeviceCheck";
import RoomLayout from "../components/room/RoomLayout";
import { Alert, Spinner } from "../components/ui";
import { getUser } from "../utils/auth";

const REFRESH_MS = 15000; // picks up the start time and the end of the interview

function roomError(err) {
  if (err.status === 410) return "This interview has ended or the link is no longer valid.";
  if (err.code === "ROOM_NOT_OPEN") return "The interview room is not open yet.";
  if (err.code === "NOT_YOUR_INTERVIEW") return "This interview belongs to another account.";
  if (err.status === 404) return "This interview link is not valid.";
  return "Could not open the interview room. Please try again.";
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

  useEffect(() => {
    if (!loggedIn) return;
    getRoomInfo(token)
      .then(setInfo)
      .catch((err) => setError(roomError(err)));
  }, [token, loggedIn]);

  // While in the room, refresh now and then (start time, interview ended)
  useEffect(() => {
    if (!stream) return undefined;
    const timer = setInterval(() => {
      getRoomInfo(token)
        .then(setInfo)
        .catch((err) => err.status === 410 && setError("The interview has ended. Thank you for attending."));
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [stream, token]);

  // The join page handles logging in and coming back
  if (!loggedIn) return <Navigate to={`/interview/join/${token}`} replace />;

  if (error) {
    return (
      <Message token={token}>
        <Alert type={stream ? "info" : "error"}>{error}</Alert>
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
      stream={stream}
      onLeave={() => navigate(`/interview/join/${token}`)}
    />
  );
}
