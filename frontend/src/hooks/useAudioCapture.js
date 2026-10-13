import { useCallback, useEffect, useState } from "react";

import { CLOSE_RECONNECT, isFinal, socketUrl } from "./useRoomSocket";

const RETRY_MS = 2000;
const MAX_RETRY_MS = 10000;
const PING_MS = 20000; // while muted, so the server's 45 s idle timeout does not close the socket
const TARGET_RATE = 16000;

const log = (...args) => console.info("[audio]", ...args);

// AudioContext at 16 kHz so the browser resamples. Some browsers (Firefox) cannot connect a mic
// at a different rate; then the device rate is used and the worklet averages down.
function openAudioGraph(track) {
  const stream = new MediaStream([track]);
  try {
    const ctx = new AudioContext({ sampleRate: TARGET_RATE });
    try {
      return { ctx, source: ctx.createMediaStreamSource(stream) };
    } catch {
      ctx.close();
    }
  } catch {
    // sampleRate option not supported
  }
  const ctx = new AudioContext();
  return { ctx, source: ctx.createMediaStreamSource(stream) };
}

// Sends this browser's own microphone to the backend as 16 kHz mono LINEAR16 chunks (~100 ms)
// over a separate audio socket. The call does not depend on it.
//   path: "/ws/audio/interviews/<id>" or "/ws/audio/join/<token>"; null = not capturing
//   track: the mic track used in the call (same track, so mute = nothing sent; screen sharing and
//     camera changes only touch video tracks)
// Reconnects with backoff (each connection is a new part on the server); drops the socket at once
// when the browser goes offline and reconnects as soon as it is back online.
// Returns { recording, restart }: recording = the audio socket is open; restart() = start again ("Try again").
export default function useAudioCapture({ path, track }) {
  const [recording, setRecording] = useState(false);
  const [restartKey, setRestartKey] = useState(0);

  useEffect(() => {
    if (!path || !track) return undefined;
    let stopped = false;
    let socket = null;
    let retryTimer;
    let attempts = 0;
    let graph = null;
    let node = null;

    const connect = () => {
      clearTimeout(retryTimer);
      if (attempts) log("audio reconnecting, attempt", attempts);
      const ws = new WebSocket(socketUrl(path));
      ws.binaryType = "arraybuffer";
      socket = ws;
      ws.onopen = () => {
        log(attempts ? "audio socket reconnected" : "audio socket connected");
        attempts = 0;
        setRecording(true);
      };
      ws.onclose = (event) => {
        if (socket === ws) socket = null;
        setRecording(false);
        if (stopped) return;
        if (isFinal(event.code)) {
          log("audio socket closed", event.code, event.reason);
          return;
        }
        attempts += 1;
        if (!navigator.onLine) return; // "online" reconnects
        retryTimer = setTimeout(connect, Math.min(RETRY_MS * attempts, MAX_RETRY_MS));
      };
    };

    // Offline: drop the socket now; online: reconnect now (once the capture graph is ready)
    const goOffline = () => {
      clearTimeout(retryTimer);
      if (!socket) return;
      const ws = socket;
      socket = null;
      ws.onclose = null;
      ws.close(CLOSE_RECONNECT, "Offline");
      setRecording(false);
      attempts = Math.max(attempts, 1);
      log("audio socket dropped (offline)");
    };
    const goOnline = () => {
      if (stopped || socket || !node) return;
      attempts = Math.max(attempts, 1);
      connect();
    };
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);

    const start = async () => {
      try {
        graph = openAudioGraph(track);
        await graph.ctx.resume(); // browsers may create it suspended (autoplay policy)
        await graph.ctx.audioWorklet.addModule("/pcm-worklet.js");
        if (stopped) return;
        node = new AudioWorkletNode(graph.ctx, "pcm-capture", { numberOfOutputs: 1, outputChannelCount: [1] });
        node.port.onmessage = (event) => {
          if (track.enabled && socket?.readyState === WebSocket.OPEN) socket.send(event.data);
        };
        graph.source.connect(node);
        node.connect(graph.ctx.destination); // keeps the worklet running; it outputs silence
        log("capture started at", graph.ctx.sampleRate, "Hz, context", graph.ctx.state);
        connect();
      } catch (err) {
        if (!stopped) console.error("[audio] could not start audio capture", err); // else: left meanwhile
      }
    };

    const ping = setInterval(() => {
      if (!track.enabled && socket?.readyState === WebSocket.OPEN) socket.send("ping");
    }, PING_MS);

    const stop = () => {
      if (stopped) return;
      stopped = true;
      clearTimeout(retryTimer);
      clearInterval(ping);
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
      socket?.close(1000, "Left the room");
      socket = null;
      if (node) node.port.onmessage = null;
      graph?.source.disconnect();
      graph?.ctx.close();
      setRecording(false);
      log("capture stopped");
    };

    start();
    window.addEventListener("pagehide", stop);
    return () => {
      window.removeEventListener("pagehide", stop);
      stop(); // the track itself belongs to the room (RoomLayout stops it)
    };
  }, [path, track, restartKey]);

  const restart = useCallback(() => setRestartKey((key) => key + 1), []);

  return { recording, restart };
}
