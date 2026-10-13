import { useCallback, useEffect, useRef, useState } from "react";

import { iceServers } from "../utils/media";

const log = (...args) => console.info("[webrtc]", ...args);

// Short id for one offer/answer session; signals of older sessions are ignored
const newSessionId = () => Math.random().toString(36).slice(2, 10);

// Peer-to-peer call over the room's signaling socket. Fixed roles: the interviewer
// sends the offer whenever the candidate is (again) in the room, the candidate answers.
// Every offer starts a fresh RTCPeerConnection (no renegotiation).
//   role: "interviewer" | "candidate"
//   stream: local stream from the device check; null = call off (closes the connection)
//   sendSignal: from useRoomSocket
// Returns { remoteStream, connectionState, remoteMedia, sharing, handleSignal, handleEvent,
// sendMediaState, toggleShare }; pass handleSignal and handleEvent to useRoomSocket's onSignal / onEvent.
// connectionState: null (no connection) or RTCPeerConnection.connectionState.
// remoteMedia: { mic, camera, screen } of the other side (its "media-state" message), null until known.
// sendMediaState(): call after mute / camera toggles (reads track.enabled of the local stream).
// toggleShare(): start / stop sharing the screen. Only the outgoing video track is replaced
// (replaceTrack, no renegotiation); the microphone track is never touched.
export default function usePeerConnection({ role, stream, sendSignal }) {
  const sessionRef = useRef(null); // { pc, sid, pending: [ICE candidates before the remote description] }
  const latest = useRef({ stream, sendSignal });
  const screenRef = useRef(null); // screen share stream while sharing
  const [remoteStream, setRemoteStream] = useState(null);
  const [connectionState, setConnectionState] = useState(null);
  const [remoteMedia, setRemoteMedia] = useState(null);
  const [sharing, setSharing] = useState(false);

  useEffect(() => {
    latest.current = { stream, sendSignal };
  });

  const close = useCallback(() => {
    const session = sessionRef.current;
    if (!session) return;
    sessionRef.current = null;
    session.pc.ontrack = null;
    session.pc.onicecandidate = null;
    session.pc.onconnectionstatechange = null;
    session.pc.oniceconnectionstatechange = null;
    session.pc.close();
    setRemoteStream(null);
    setConnectionState(null);
    setRemoteMedia(null);
    log("connection closed");
  }, []);

  // Tell the other side whether our mic / camera is on
  const sendMediaState = useCallback(() => {
    const localStream = latest.current.stream;
    if (!localStream) return;
    latest.current.sendSignal({
      type: "media-state",
      mic: Boolean(localStream.getAudioTracks()[0]?.enabled),
      camera: Boolean(localStream.getVideoTracks()[0]?.enabled),
      screen: Boolean(screenRef.current),
    });
  }, []);

  // Video we send: the screen while sharing, else the camera (may be none)
  const outgoingVideo = useCallback(
    () => screenRef.current?.getVideoTracks()[0] || latest.current.stream?.getVideoTracks()[0] || null,
    []
  );

  // New connection for session sid (closes the old one)
  const create = useCallback(
    (sid) => {
      close();
      const pc = new RTCPeerConnection({ iceServers: iceServers() });
      const session = { pc, sid, pending: [] };
      sessionRef.current = session;
      const current = () => sessionRef.current === session;
      const remoteTracks = [];

      pc.ontrack = (event) => {
        remoteTracks.push(event.track);
        setRemoteStream(new MediaStream(remoteTracks));
      };
      pc.onicecandidate = (event) => {
        if (event.candidate) latest.current.sendSignal({ type: "ice", sid, candidate: event.candidate.toJSON() });
      };
      pc.onconnectionstatechange = () => {
        if (!current()) return;
        log("connection state:", pc.connectionState);
        setConnectionState(pc.connectionState);
        if (pc.connectionState === "connected") sendMediaState();
      };
      pc.oniceconnectionstatechange = () => current() && log("ICE state:", pc.iceConnectionState);

      setConnectionState(pc.connectionState);
      log("new connection", sid);
      return session;
    },
    [close, sendMediaState]
  );

  const flushPending = async (session) => {
    const { pc, pending } = session;
    session.pending = [];
    for (const candidate of pending) await pc.addIceCandidate(candidate);
  };

  // Interviewer: start a fresh connection and send the offer
  const startOffer = useCallback(async () => {
    const localStream = latest.current.stream;
    if (!localStream) return;
    const session = create(newSessionId());
    const { pc, sid } = session;
    // Video goes "sendrecv" even without a camera: we still receive the other side's video,
    // and a screen share can be added later with replaceTrack.
    pc.addTransceiver(localStream.getAudioTracks()[0] || "audio", { direction: "sendrecv", streams: [localStream] });
    pc.addTransceiver(outgoingVideo() || "video", { direction: "sendrecv", streams: [localStream] });
    try {
      await pc.setLocalDescription(await pc.createOffer());
      if (sessionRef.current !== session) return;
      latest.current.sendSignal({ type: "offer", sid, sdp: pc.localDescription.sdp });
      log("offer sent");
    } catch (err) {
      console.error("[webrtc] could not create the offer", err);
    }
  }, [create, outgoingVideo]);

  // Candidate: answer an offer on a fresh connection
  const answer = useCallback(
    async ({ sid, sdp }) => {
      const localStream = latest.current.stream;
      if (!localStream) return;
      const session = create(sid);
      const { pc } = session;
      try {
        await pc.setRemoteDescription({ type: "offer", sdp });
        for (const transceiver of pc.getTransceivers()) {
          const kind = transceiver.receiver.track.kind;
          const track = kind === "audio" ? localStream.getAudioTracks()[0] : outgoingVideo();
          if (track) await transceiver.sender.replaceTrack(track);
          transceiver.sender.setStreams?.(localStream);
          transceiver.direction = "sendrecv";
        }
        await flushPending(session);
        await pc.setLocalDescription(await pc.createAnswer());
        if (sessionRef.current !== session) return;
        latest.current.sendSignal({ type: "answer", sid, sdp: pc.localDescription.sdp });
        log("answer sent");
      } catch (err) {
        console.error("[webrtc] could not answer the offer", err);
      }
    },
    [create, outgoingVideo]
  );

  const handleSignal = useCallback(
    async (data) => {
      if (!data?.type) return;
      if (data.type === "media-state") {
        setRemoteMedia({ mic: Boolean(data.mic), camera: Boolean(data.camera), screen: Boolean(data.screen) });
        return;
      }
      if (data.type === "offer") {
        if (role === "candidate") answer(data);
        return;
      }
      const session = sessionRef.current;
      if (!session || session.sid !== data.sid) return; // old or unknown session
      try {
        if (data.type === "answer" && role === "interviewer") {
          if (session.pc.signalingState !== "have-local-offer") return;
          await session.pc.setRemoteDescription({ type: "answer", sdp: data.sdp });
          await flushPending(session);
          log("answer received");
        } else if (data.type === "ice" && data.candidate) {
          if (session.pc.remoteDescription) await session.pc.addIceCandidate(data.candidate);
          else session.pending.push(data.candidate);
        }
      } catch (err) {
        console.error(`[webrtc] could not apply ${data.type}`, err);
      }
    },
    [role, answer]
  );

  // Put the current outgoing video on the connection's video sender
  const applyOutgoingVideo = useCallback(async () => {
    const transceiver = sessionRef.current?.pc.getTransceivers().find((t) => t.receiver.track.kind === "video");
    if (!transceiver) return;
    try {
      await transceiver.sender.replaceTrack(outgoingVideo());
    } catch (err) {
      console.error("[webrtc] could not switch the video track", err);
    }
  }, [outgoingVideo]);

  const stopShare = useCallback(() => {
    const screen = screenRef.current;
    if (!screen) return;
    screenRef.current = null;
    screen.getTracks().forEach((track) => track.stop());
    setSharing(false);
    applyOutgoingVideo(); // back to the camera
    sendMediaState();
    log("screen sharing stopped");
  }, [applyOutgoingVideo, sendMediaState]);

  const startShare = useCallback(async () => {
    let screen;
    try {
      screen = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    } catch (err) {
      if (err.name !== "NotAllowedError") console.error("[webrtc] could not share the screen", err);
      return; // cancelled in the browser's picker
    }
    if (!latest.current.stream || screenRef.current) {
      screen.getTracks().forEach((track) => track.stop()); // left meanwhile, or already sharing
      return;
    }
    screenRef.current = screen;
    screen.getVideoTracks()[0].onended = stopShare; // the browser's own "Stop sharing" button
    setSharing(true);
    await applyOutgoingVideo();
    sendMediaState();
    log("screen sharing started");
  }, [applyOutgoingVideo, sendMediaState, stopShare]);

  const toggleShare = useCallback(
    () => (screenRef.current ? stopShare() : startShare()),
    [stopShare, startShare]
  );

  // Room events, handled in socket order (no race with the offer that follows them)
  const handleEvent = useCallback(
    (message) => {
      if (!latest.current.stream) return;
      const peerPresent =
        message.type === "peer-joined" || (message.type === "room-state" && message.peers.length > 0);
      if (peerPresent) {
        if (role === "interviewer") startOffer(); // candidate waits for the offer
      } else if (message.type === "peer-left" || message.type === "interview-ended") {
        close();
      }
    },
    [role, startOffer, close]
  );

  // Call off (no stream, e.g. interview ended): stop sharing and close the connection
  useEffect(() => {
    if (stream) return;
    stopShare();
    close();
  }, [stream, stopShare, close]);

  // Stop sharing and close on leave (unmount) and when the page closes
  useEffect(() => {
    const end = () => {
      stopShare();
      close();
    };
    window.addEventListener("pagehide", end);
    return () => {
      window.removeEventListener("pagehide", end);
      end();
    };
  }, [stopShare, close]);

  return {
    remoteStream,
    connectionState,
    remoteMedia,
    sharing,
    handleSignal,
    handleEvent,
    sendMediaState,
    toggleShare,
  };
}
