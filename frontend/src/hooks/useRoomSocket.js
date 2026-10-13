import { useCallback, useEffect, useRef, useState } from "react";

const RETRY_MS = 2000;
const MAX_RETRY_MS = 10000;

// Client close codes: 1000 = left the room (the other side gets "peer-left" at once);
// CLOSE_RECONNECT = dropped on purpose to reconnect (offline / "Try again"), the server waits for us
export const CLOSE_RECONNECT = 3000;

// No reconnect after: normal close (interview ended), replaced by another tab, or refused (44xx)
export const isFinal = (code) => code === 1000 || code === 4000 || (code >= 4400 && code < 4500);

export function socketUrl(path) {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/v1${path}`;
}

const log = (...args) => console.info("[room]", ...args);

// Signaling socket for the interview room.
//   path: "/ws/interviews/<id>" or "/ws/join/<token>"; null = not connected yet
//   onSignal(data): a "signal" from the other participant (WebRTC data in 6.3.3)
//   onEvent(message): room-state, peer-joined, peer-reconnecting, peer-left, interview-started,
//     interview-ended, chat ({ type: "chat", message } - saved on the server, sent to both sides)
// Reconnects with backoff; drops the socket at once when the browser goes offline and reconnects
// as soon as it is back online.
// Returns { connected, online, peer, peerReconnecting, sendSignal, sendChat, closed, restart }.
// peer = { role, name } or null; peerReconnecting = the other side dropped and has not come back yet;
// closed = { code, reason } once the socket is closed for good; restart() = reconnect now ("Try again").
export default function useRoomSocket(path, { onSignal, onEvent } = {}) {
  const socketRef = useRef(null);
  const handlers = useRef({ onSignal, onEvent });
  const restarting = useRef(false);
  const [connected, setConnected] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  const [peer, setPeer] = useState(null);
  const [peerReconnecting, setPeerReconnecting] = useState(false);
  const [closed, setClosed] = useState(null);
  const [restartKey, setRestartKey] = useState(0);

  useEffect(() => {
    handlers.current = { onSignal, onEvent };
  });

  useEffect(() => {
    restarting.current = false;
    if (!path) return undefined;
    let stopped = false;
    let retryTimer;
    let attempts = 0;

    const lost = () => {
      setConnected(false);
      setPeer(null); // room-state restores it after reconnecting
      setPeerReconnecting(false);
    };

    const connect = () => {
      clearTimeout(retryTimer);
      if (attempts) log("reconnecting, attempt", attempts);
      const socket = new WebSocket(socketUrl(path));
      socketRef.current = socket;

      socket.onopen = () => {
        if (attempts) log("reconnected");
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
        if (["room-state", "peer-joined", "peer-left", "peer-reconnecting"].includes(message.type)) {
          setPeerReconnecting(message.type === "peer-reconnecting");
        }
        handlers.current.onEvent?.(message);
      };

      socket.onclose = (event) => {
        if (socketRef.current === socket) socketRef.current = null;
        lost();
        if (stopped) return;
        if (isFinal(event.code)) {
          log("closed for good", event.code, event.reason);
          setClosed({ code: event.code, reason: event.reason });
          return;
        }
        attempts += 1;
        if (!navigator.onLine) return; // "online" reconnects
        retryTimer = setTimeout(connect, Math.min(RETRY_MS * attempts, MAX_RETRY_MS));
      };
    };

    // Offline: drop the socket now (it may take long to notice by itself); online: reconnect now
    const goOffline = () => {
      setOnline(false);
      log("browser offline");
      clearTimeout(retryTimer);
      const socket = socketRef.current;
      if (!socket) return;
      socketRef.current = null;
      socket.onclose = null;
      socket.close(CLOSE_RECONNECT, "Offline");
      lost();
      attempts = Math.max(attempts, 1);
    };
    const goOnline = () => {
      setOnline(true);
      log("browser online");
      if (socketRef.current) return; // still connected or connecting
      attempts = Math.max(attempts, 1);
      connect();
    };
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);

    connect();

    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
      // "Try again" reconnects: do not tell the other side we left
      const code = restarting.current ? CLOSE_RECONNECT : 1000;
      restarting.current = false;
      socketRef.current?.close(code, code === 1000 ? "Left the room" : "Reconnecting");
      socketRef.current = null;
      lost();
    };
  }, [path, restartKey]);

  // "Try again": close and open the socket now (backoff reset)
  const restart = useCallback(() => {
    log("restart requested");
    restarting.current = true;
    setRestartKey((key) => key + 1);
  }, []);

  // Send WebRTC data to the other participant; false if not connected right now
  const sendSignal = useCallback((data) => {
    const socket = socketRef.current;
    if (socket?.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ type: "signal", data }));
    return true;
  }, []);

  // Send an in-call chat text; it comes back to both sides as a "chat" event once saved
  const sendChat = useCallback((text) => {
    const socket = socketRef.current;
    if (socket?.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ type: "chat", text }));
    return true;
  }, []);

  return { connected, online, peer, peerReconnecting, sendSignal, sendChat, closed, restart };
}
