import { useCallback, useEffect, useRef, useState } from "react";

import { iceServers } from "../utils/media";

const log = (...args) => console.info("[webrtc]", ...args);

// Short id for one offer/answer session; signals of older sessions are ignored
const newSessionId = () => Math.random().toString(36).slice(2, 10);

// Recovery (interviewer side, 6.5.1): "disconnected" for DISCONNECT_GRACE_MS or "failed" →
// ICE restart on the same connection; not connected again RECOVERY_STEP_MS later → fresh connection
// (repeated every step); after GIVE_UP_MS automatic recovery stops until the peer (re)joins.
const DISCONNECT_GRACE_MS = 5000;
const RECOVERY_STEP_MS = 15000;
const GIVE_UP_MS = 60000;

// Peer-to-peer call over the room's signaling socket. Fixed roles: the interviewer
// sends the offer whenever the candidate is (again) in the room, the candidate answers.
// Every offer starts a fresh RTCPeerConnection, except an ICE restart ("restart": true, same sid),
// which the candidate answers on the existing connection (tracks and media state are kept).
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
  const recoveryRef = useRef({ since: 0, timer: null, restarted: false }); // interviewer only
  const onStateRef = useRef(null); // latest connection-state handler (uses functions defined below)
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
        onStateRef.current?.(pc.connectionState);
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

  const stopRecovery = useCallback(() => {
    clearTimeout(recoveryRef.current.timer);
    recoveryRef.current = { since: 0, timer: null, restarted: false };
  }, []);

  // Interviewer: new offer with fresh ICE credentials on the existing connection
  const restartIce = useCallback(
    async (session) => {
      const { pc, sid } = session;
      try {
        await pc.setLocalDescription(await pc.createOffer({ iceRestart: true }));
        if (sessionRef.current !== session) return;
        const sent = latest.current.sendSignal({ type: "offer", sid, sdp: pc.localDescription.sdp, restart: true });
        log(sent ? "ICE restart offer sent" : "ICE restart offer not sent (signaling not connected)");
      } catch (err) {
        console.error("[webrtc] ICE restart failed, starting a fresh connection", err);
        startOffer();
      }
    },
    [startOffer]
  );

  // Connection state changes of the current session (called from create)
  useEffect(() => {
    // Interviewer: one recovery step (ICE restart first, then fresh connections), checked again later
    const recover = () => {
      const recovery = recoveryRef.current;
      clearTimeout(recovery.timer);
      recovery.timer = null;
      if (!latest.current.stream) return;
      if (!recovery.since) recovery.since = Date.now();
      const elapsed = Date.now() - recovery.since;
      if (elapsed >= GIVE_UP_MS) {
        log(`recovery gave up after ${Math.round(elapsed / 1000)} s (waiting for the other side to rejoin)`);
        return;
      }
      const session = sessionRef.current;
      if (session && !recovery.restarted) {
        recovery.restarted = true;
        log("connection lost, trying an ICE restart");
        restartIce(session);
      } else {
        log("not recovered, starting a fresh connection");
        startOffer();
      }
      recovery.timer = setTimeout(() => {
        recovery.timer = null;
        if (sessionRef.current?.pc.connectionState !== "connected") recover();
      }, RECOVERY_STEP_MS);
    };

    onStateRef.current = (state) => {
      const recovery = recoveryRef.current;
      if (state === "connected") {
        if (recovery.since) log(`recovered after ${Math.round((Date.now() - recovery.since) / 1000)} s`);
        stopRecovery();
        return;
      }
      if (role !== "interviewer" || (state !== "disconnected" && state !== "failed")) return;
      if (recovery.timer) return; // a recovery step is already running
      if (state === "failed") {
        recover();
      } else {
        log(`connection disconnected, recovering in ${DISCONNECT_GRACE_MS / 1000} s unless it comes back`);
        if (!recovery.since) recovery.since = Date.now();
        recovery.timer = setTimeout(recover, DISCONNECT_GRACE_MS);
      }
    };
  });

  // Candidate: an ICE restart offer for the current session, answered on the same connection
  const answerRestart = useCallback(async (session, sdp) => {
    const { pc, sid } = session;
    try {
      await pc.setRemoteDescription({ type: "offer", sdp });
      await pc.setLocalDescription(await pc.createAnswer());
      if (sessionRef.current !== session) return;
      latest.current.sendSignal({ type: "answer", sid, sdp: pc.localDescription.sdp });
      log("ICE restart answered");
    } catch (err) {
      console.error("[webrtc] could not answer the ICE restart", err); // the interviewer falls back to a fresh offer
    }
  }, []);

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
        if (role !== "candidate") return;
        const current = sessionRef.current;
        if (!data.restart) answer(data);
        else if (current?.sid === data.sid) answerRestart(current, data.sdp);
        else log("ICE restart for an unknown session ignored"); // the interviewer falls back to a fresh offer
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
    [role, answer, answerRestart]
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
        if (role !== "interviewer") return; // candidate waits for the offer
        // Own signaling reconnected while the call itself survived: keep it.
        // peer-joined always starts fresh (the candidate may have reloaded the page).
        if (message.type === "room-state" && sessionRef.current?.pc.connectionState === "connected") {
          log("signaling reconnected, call still connected");
          return;
        }
        stopRecovery();
        startOffer();
      } else if (message.type === "peer-left" || message.type === "interview-ended") {
        stopRecovery();
        close();
      }
      // peer-reconnecting: keep the connection; it may recover, else peer-joined starts a fresh one
    },
    [role, startOffer, close, stopRecovery]
  );

  // Call off (no stream, e.g. interview ended): stop sharing and close the connection
  useEffect(() => {
    if (stream) return;
    stopRecovery();
    stopShare();
    close();
  }, [stream, stopShare, close, stopRecovery]);

  // Stop sharing and close on leave (unmount) and when the page closes
  useEffect(() => {
    const end = () => {
      stopRecovery();
      stopShare();
      close();
    };
    window.addEventListener("pagehide", end);
    return () => {
      window.removeEventListener("pagehide", end);
      end();
    };
  }, [stopShare, close, stopRecovery]);

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
