import { useEffect, useRef, useState } from "react";

import { stopStream } from "../../utils/media";
import {
  CameraIcon,
  CameraOffIcon,
  ChatIcon,
  CloseIcon,
  LeaveIcon,
  MicIcon,
  MicOffIcon,
  PanelIcon,
  ScreenShareIcon,
} from "./icons";

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
    <span className="rounded-md bg-white/10 px-2.5 py-1 font-mono text-xs text-gray-100">
      {startedAt ? formatElapsed(now - new Date(startedAt)) : "Not started"}
    </span>
  );
}

const CONNECTION_BADGES = {
  connected: { label: "Connected", dot: "bg-green-400" },
  disconnected: { label: "Connection lost", dot: "bg-red-400" },
  failed: { label: "Connection lost", dot: "bg-red-400" },
};
const CONNECTING_BADGE = { label: "Connecting...", dot: "bg-amber-400" };
const WAITING_BADGE = { label: "Waiting", dot: "bg-gray-400" };

function initials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  return parts.length ? (parts[0][0] + (parts.length > 1 ? parts.at(-1)[0] : "")).toUpperCase() : "?";
}

// Round control button with a tooltip. tone: default / off (red) / active (highlighted) / danger
const TONES = {
  default: "bg-gray-700 text-white hover:bg-gray-600",
  off: "bg-red-600 text-white hover:bg-red-500",
  active: "bg-indigo-200 text-indigo-900 hover:bg-indigo-100",
  danger: "bg-red-600 text-white hover:bg-red-500",
};

function ControlButton({ label, onClick, tone = "default", disabled, badge, children }) {
  return (
    <div className="group relative">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        aria-label={label}
        className={`flex h-11 w-11 items-center justify-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-40 disabled:hover:bg-gray-700 ${TONES[tone]}`}
      >
        {children}
      </button>
      {badge > 0 && (
        <span className="pointer-events-none absolute -top-1 -right-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[11px] font-semibold text-white ring-2 ring-gray-900">
          {badge > 9 ? "9+" : badge}
        </span>
      )}
      <span className="pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2 whitespace-nowrap rounded-md bg-gray-950 px-2 py-1 text-xs text-white opacity-0 shadow transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        {label}
      </span>
    </div>
  );
}

// Light side panel; stays mounted when closed so its content (CV, chat draft) is kept
function SidePanel({ title, open, onClose, children }) {
  return (
    <aside
      className={`w-80 shrink-0 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm 2xl:w-96 ${
        open ? "flex" : "hidden"
      }`}
    >
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-gray-200 pr-2 pl-4">
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label={`Close ${title}`}
          title="Close"
          className="flex h-8 w-8 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 hover:text-gray-700"
        >
          <CloseIcon className="h-4 w-4" />
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </aside>
  );
}

// Shared interview room (Meet-style): optional left panel, dark video stage with header and
// controls, optional bottom panel, and the in-call chat on the right.
// The room owns the local stream: all tracks stop when it closes or the page is left.
// remoteStream / connectionState / remoteMedia come from usePeerConnection;
// onMediaChange() is called after mute / camera toggles (to tell the other side).
// sharing / onToggleShare: own screen share (usePeerConnection).
// leftPanel = { title, content } (interviewer only); chat = { open, onToggle, unread, content };
// endControl = interviewer "End interview" button.
// recording: own audio is being sent (useAudioCapture); recordingNotice: line shown to the candidate.
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
  endControl,
  leftPanel,
  chat,
  bottomPanel,
  recording,
  recordingNotice,
}) {
  const selfRef = useRef(null);
  const remoteRef = useRef(null);
  const [micOn, setMicOn] = useState(true);
  const [cameraOn, setCameraOn] = useState(true);
  const [leftOpen, setLeftOpen] = useState(true);
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
  const badge = peerName || connectionState ? CONNECTION_BADGES[connectionState] || CONNECTING_BADGE : WAITING_BADGE;
  const otherName = peerName || "The other participant";

  return (
    <div className="flex h-screen gap-3 overflow-hidden bg-gray-100 p-3">
      {leftPanel && (
        <SidePanel title={leftPanel.title} open={leftOpen} onClose={() => setLeftOpen(false)}>
          {leftPanel.content}
        </SidePanel>
      )}

      <main className="flex min-w-0 flex-1 flex-col gap-3">
        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl bg-gray-900 shadow-sm">
          <header className="flex min-h-14 shrink-0 items-center justify-between gap-4 px-5 py-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-white">{jobTitle}</p>
              <p className="truncate text-xs text-gray-400">Interview with {candidateName || "—"}</p>
              {recordingNotice && <p className="truncate text-xs text-gray-400">{recordingNotice}</p>}
            </div>
            <div className="flex shrink-0 items-center gap-3">
              {recording && (
                <span className="flex items-center gap-1.5 text-xs font-medium text-red-300">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
                  Recording
                </span>
              )}
              <span className="flex items-center gap-1.5 text-xs text-gray-300">
                <span className={`h-2 w-2 rounded-full ${badge.dot}`} />
                {badge.label}
              </span>
              <ElapsedTimer startedAt={startedAt} />
            </div>
          </header>

          <div className="relative mx-3 flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-xl bg-gray-800">
            <video ref={remoteRef} autoPlay playsInline className={`h-full w-full object-contain ${showRemote ? "" : "hidden"}`} />
            {!showRemote && (
              <div className="flex flex-col items-center gap-3 px-4 text-center">
                <span className="flex h-20 w-20 items-center justify-center rounded-full bg-indigo-600 text-2xl font-semibold text-white">
                  {peerName ? initials(peerName) : "…"}
                </span>
                <p className="text-sm text-gray-300">
                  {connected
                    ? `${otherName}: camera off`
                    : peerName
                      ? `${peerName} has joined`
                      : `Waiting for ${waitingFor} to join...`}
                </p>
              </div>
            )}
            {remoteSharing && (
              <span className="absolute top-3 left-1/2 -translate-x-1/2 rounded-md bg-indigo-600/90 px-2.5 py-1 text-xs font-medium text-white">
                {otherName} is sharing their screen
              </span>
            )}
            {connected && (
              <span className="absolute bottom-3 left-3 flex items-center gap-1.5 rounded-md bg-black/60 px-2 py-1 text-xs text-white">
                {remoteMedia?.mic === false && <MicOffIcon className="h-3.5 w-3.5 text-red-400" />}
                {peerName || "Participant"}
              </span>
            )}

            <div className="absolute right-3 bottom-3 flex aspect-video w-40 items-center justify-center overflow-hidden rounded-lg bg-gray-700 shadow-lg ring-1 ring-white/10 lg:w-52">
              <video
                ref={selfRef}
                autoPlay
                playsInline
                muted
                className={`h-full w-full -scale-x-100 object-cover ${showSelf ? "" : "hidden"}`}
              />
              {!showSelf && <span className="text-xs text-gray-400">{hasVideo ? "Camera off" : "No camera"}</span>}
              <span className="absolute bottom-1.5 left-1.5 flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-[11px] text-white">
                {!micOn && <MicOffIcon className="h-3 w-3 text-red-400" />}
                You{sharing ? " · sharing screen" : ""}
              </span>
            </div>
          </div>

          <div className="flex h-16 shrink-0 items-center justify-between gap-3 px-4">
            <div className="flex flex-1 items-center gap-2">
              {leftPanel && (
                <ControlButton
                  label={leftOpen ? `Hide ${leftPanel.title.toLowerCase()}` : `Show ${leftPanel.title.toLowerCase()}`}
                  onClick={() => setLeftOpen(!leftOpen)}
                  tone={leftOpen ? "active" : "default"}
                >
                  <PanelIcon />
                </ControlButton>
              )}
            </div>

            <div className="flex items-center gap-3">
              <ControlButton label={micOn ? "Turn off microphone" : "Turn on microphone"} onClick={toggleMic} tone={micOn ? "default" : "off"}>
                {micOn ? <MicIcon /> : <MicOffIcon />}
              </ControlButton>
              <ControlButton
                label={!hasVideo ? "No camera" : cameraOn ? "Turn off camera" : "Turn on camera"}
                onClick={toggleCamera}
                disabled={!hasVideo}
                tone={cameraOn && hasVideo ? "default" : "off"}
              >
                {cameraOn && hasVideo ? <CameraIcon /> : <CameraOffIcon />}
              </ControlButton>
              {onToggleShare && (
                <ControlButton
                  label={sharing ? "Stop sharing" : remoteSharing ? `${otherName} is sharing` : "Share screen"}
                  onClick={onToggleShare}
                  disabled={!sharing && !canShare}
                  tone={sharing ? "active" : "default"}
                >
                  <ScreenShareIcon />
                </ControlButton>
              )}
              <ControlButton label="Leave the room" onClick={onLeave} tone={endControl ? "default" : "danger"}>
                <LeaveIcon />
              </ControlButton>
            </div>

            <div className="flex flex-1 items-center justify-end gap-3">
              {chat && (
                <ControlButton
                  label={chat.open ? "Hide chat" : "Open chat"}
                  onClick={chat.onToggle}
                  tone={chat.open ? "active" : "default"}
                  badge={chat.open ? 0 : chat.unread}
                >
                  <ChatIcon />
                </ControlButton>
              )}
              {endControl}
            </div>
          </div>
        </section>

        {bottomPanel}
      </main>

      {chat && (
        <SidePanel title="In-call messages" open={chat.open} onClose={chat.onToggle}>
          {chat.content}
        </SidePanel>
      )}
    </div>
  );
}
