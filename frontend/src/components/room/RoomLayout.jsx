import { useEffect, useRef, useState } from "react";

import { stopStream } from "../../utils/media";
import { Button } from "../ui";

const pad = (n) => String(n).padStart(2, "0");

function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function ElapsedTimer({ startedAt }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!startedAt) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);

  return (
    <span className="rounded-md bg-gray-100 px-2.5 py-1 font-mono text-sm text-gray-700">
      {startedAt ? formatElapsed(now - new Date(startedAt)) : "Not started"}
    </span>
  );
}

const CONNECTION_BADGES = {
  connected: { label: "Connected", className: "bg-green-600/90" },
  disconnected: { label: "Connection lost", className: "bg-red-600/90" },
  failed: { label: "Connection lost", className: "bg-red-600/90" },
};
function MicOffIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5" aria-label="Muted">
      <path d="M9 9v3a3 3 0 0 0 5.1 2.1M15 9.3V5a3 3 0 0 0-5.9-.7" />
      <path d="M19 10v2a7 7 0 0 1-.6 2.9M5 10v2a7 7 0 0 0 11.6 5.3M12 19v3M3 3l18 18" />
    </svg>
  );
}

const CONNECTING_BADGE = { label: "Connecting...", className: "bg-gray-600/90" };

// Shared interview room: header, remote video area, self-view and controls.
// The room owns the local stream: all tracks stop when it closes or the page is left.
// remoteStream / connectionState / remoteMedia come from usePeerConnection;
// onMediaChange() is called after mute / camera toggles (to tell the other side).
// sharing / onToggleShare: own screen share (usePeerConnection).
export default function RoomLayout({
  jobTitle,
  candidateName,
  startedAt,
  waitingFor,
  peerName,
  stream,
  remoteStream,
  connectionState,
  remoteMedia,
  onMediaChange,
  sharing,
  onToggleShare,
  onLeave,
  extraControls,
  sidePanel,
  bottomPanel,
}) {
  const selfRef = useRef(null);
  const remoteRef = useRef(null);
  const [micOn, setMicOn] = useState(true);
  const [cameraOn, setCameraOn] = useState(true);
  const hasVideo = Boolean(stream?.getVideoTracks().length);

  useEffect(() => {
    if (selfRef.current) selfRef.current.srcObject = stream;
    const stop = () => stopStream(stream);
    window.addEventListener("pagehide", stop);
    return () => {
      window.removeEventListener("pagehide", stop);
      stop();
    };
  }, [stream]);

  useEffect(() => {
    if (remoteRef.current) remoteRef.current.srcObject = remoteStream || null;
  }, [remoteStream]);

  const toggleMic = () => {
    stream?.getAudioTracks().forEach((t) => (t.enabled = !micOn));
    setMicOn(!micOn);
    onMediaChange?.();
  };

  const toggleCamera = () => {
    stream?.getVideoTracks().forEach((t) => (t.enabled = !cameraOn));
    setCameraOn(!cameraOn);
    onMediaChange?.();
  };

  const showSelf = hasVideo && cameraOn;
  // Remote media arrived; the element also plays the remote audio (kept mounted, only hidden)
  const connected = Boolean(remoteStream) && connectionState === "connected";
  const remoteSharing = connected && Boolean(remoteMedia?.screen);
  const showRemote = connected && (remoteSharing || remoteMedia?.camera !== false);
  // One share at a time; not available on browsers without getDisplayMedia (e.g. mobile)
  const canShare = Boolean(navigator.mediaDevices?.getDisplayMedia) && connected && !remoteSharing;
  const badge = peerName || connectionState ? CONNECTION_BADGES[connectionState] || CONNECTING_BADGE : null;

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-5">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-gray-900">{jobTitle}</p>
          <p className="truncate text-xs text-gray-500">Candidate: {candidateName || "—"}</p>
        </div>
        <ElapsedTimer startedAt={startedAt} />
      </header>

      <div className="flex min-h-0 flex-1 gap-4 p-4">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-lg bg-gray-900">
            <video ref={remoteRef} autoPlay playsInline className={`h-full w-full object-contain ${showRemote ? "" : "hidden"}`} />
            {!showRemote && (
              <p className="text-sm text-gray-300">
                {connected
                  ? `${peerName || "The other participant"}: camera off`
                  : peerName
                    ? `${peerName} has joined`
                    : `Waiting for ${waitingFor} to join...`}
              </p>
            )}
            {badge && (
              <span className={`absolute top-3 left-3 rounded px-2 py-0.5 text-xs font-medium text-white ${badge.className}`}>
                {badge.label}
              </span>
            )}
            {remoteSharing && (
              <span className="absolute top-3 left-1/2 -translate-x-1/2 rounded bg-indigo-600/90 px-2 py-0.5 text-xs font-medium text-white">
                {peerName || "The other participant"} is sharing their screen
              </span>
            )}
            {connected && (
              <span className="absolute bottom-3 left-3 flex items-center gap-1 rounded bg-black/50 px-2 py-0.5 text-xs text-white">
                {remoteMedia?.mic === false && <MicOffIcon />}
                {peerName || "Participant"}
              </span>
            )}

            <div className="absolute right-3 bottom-3 flex aspect-video w-48 items-center justify-center overflow-hidden rounded-md border border-gray-700 bg-gray-800 shadow-lg">
              <video
                ref={selfRef}
                autoPlay
                playsInline
                muted
                className={`h-full w-full -scale-x-100 object-cover ${showSelf ? "" : "hidden"}`}
              />
              {!showSelf && <span className="text-xs text-gray-400">{hasVideo ? "Camera off" : "No camera"}</span>}
              <span className="absolute bottom-1 left-1.5 rounded bg-black/50 px-1.5 text-[11px] text-white">
                You{micOn ? "" : " (muted)"}
                {sharing ? " · sharing screen" : ""}
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center justify-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2.5">
            <Button variant="secondary" onClick={toggleMic} className={micOn ? "" : "text-red-600"}>
              {micOn ? "Mute" : "Unmute"}
            </Button>
            <Button variant="secondary" onClick={toggleCamera} disabled={!hasVideo} className={cameraOn ? "" : "text-red-600"}>
              {cameraOn ? "Turn camera off" : "Turn camera on"}
            </Button>
            {onToggleShare && (
              <Button
                variant="secondary"
                onClick={onToggleShare}
                disabled={!sharing && !canShare}
                className={sharing ? "text-indigo-600" : ""}
              >
                {sharing ? "Stop sharing" : "Share screen"}
              </Button>
            )}
            <Button variant="secondary" onClick={onLeave}>
              Leave
            </Button>
            {extraControls}
          </div>

          {bottomPanel}
        </div>

        {sidePanel}
      </div>
    </div>
  );
}
