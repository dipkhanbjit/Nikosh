import { useCallback, useEffect, useRef, useState } from "react";

const RETRY_MS = 2000;
const MAX_RETRY_MS = 10000;

// No reconnect after: normal close (interview ended), replaced by another tab, or refused (44xx)
const isFinal = (code) => code === 1000 || code === 4000 || (code >= 4400 && code < 4500);

function socketUrl(path) {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/v1${path}`;
}

// Signaling socket for the interview room.
//   path: "/ws/interviews/<id>" or "/ws/join/<token>"; null = not connected yet
//   onSignal(data): a "signal" from the other participant (WebRTC data in 6.3.3)
//   onEvent(message): room-state, peer-joined, peer-left, interview-started, interview-ended
// Returns { connected, peer, sendSignal, closed }. peer = { role, name } or null;
// closed = { code, reason } once the socket is closed for good.
export default function useRoomSocket(path, { onSignal, onEvent } = {}) {
  const socketRef = useRef(null);
  const handlers = useRef({ onSignal, onEvent });
  const [connected, setConnected] = useState(false);
  const [peer, setPeer] = useState(null);
  const [closed, setClosed] = useState(null);

  useEffect(() => {
    handlers.current = { onSignal, onEvent };
  });

  useEffect(() => {
    if (!path) return undefined;
    let stopped = false;
    let retryTimer;
    let attempts = 0;

    const connect = () => {
      const socket = new WebSocket(socketUrl(path));
      socketRef.current = socket;

      socket.onopen = () => {
        attempts = 0;
        setConnected(true);
        setClosed(null);
      };

      socket.onmessage = (event) => {
        let message;
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }
        if (message.type === "ping") {
          socket.send(JSON.stringify({ type: "pong" }));
          return;
        }
        if (message.type === "signal") {
          handlers.current.onSignal?.(message.data);
          return;
        }
        if (message.type === "room-state") setPeer(message.peers[0] || null);
        else if (message.type === "peer-joined") setPeer({ role: message.role, name: message.name });
        else if (message.type === "peer-left") setPeer(null);
        handlers.current.onEvent?.(message);
      };

      socket.onclose = (event) => {
        if (socketRef.current === socket) socketRef.current = null;
        setConnected(false);
        setPeer(null); // room-state restores it after reconnecting
        if (stopped) return;
        if (isFinal(event.code)) {
          setClosed({ code: event.code, reason: event.reason });
          return;
        }
        attempts += 1;
        retryTimer = setTimeout(connect, Math.min(RETRY_MS * attempts, MAX_RETRY_MS));
      };
    };

    connect();

    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      socketRef.current?.close(1000, "Left the room");
      socketRef.current = null;
    };
  }, [path]);

  // Send WebRTC data to the other participant; false if not connected right now
  const sendSignal = useCallback((data) => {
    const socket = socketRef.current;
    if (socket?.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ type: "signal", data }));
    return true;
  }, []);

  return { connected, peer, sendSignal, closed };
}
