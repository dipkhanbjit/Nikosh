import { useCallback, useEffect, useState } from "react";

const GIVE_UP_MS = 60000;

// Which connection problem the room shows (6.5.1):
//   "self"  - own drop: browser offline, or the room socket dropped after it had connected
//   "peer"  - the other side dropped ("peer-reconnecting"), or the call was connected and is not anymore
//   "lost"  - either one for GIVE_UP_MS; the room offers "Try again"
//   null    - all fine (or nobody to talk to yet)
// Inputs: online / connected / peerReconnecting from useRoomSocket, connectionState from usePeerConnection.
// Returns { status, retry }: retry() goes back to "self" / "peer" and waits GIVE_UP_MS again.
export default function useConnectionStatus({ online, connected, peerReconnecting, connectionState }) {
  const [socketSeen, setSocketSeen] = useState(false); // the room socket was connected once
  const [inCall, setInCall] = useState(false); // the call was connected (until it is closed)
  const [lost, setLost] = useState(false);
  const [attempt, setAttempt] = useState(0);

  if (connected && !socketSeen) setSocketSeen(true);
  if (connectionState === "connected" && !inCall) setInCall(true);
  else if (!connectionState && inCall) setInCall(false);

  let issue = null;
  if (!online || (socketSeen && !connected)) issue = "self";
  else if (peerReconnecting || (inCall && connectionState !== "connected")) issue = "peer";

  // Reset when the problem is gone
  const active = Boolean(issue);
  const [wasActive, setWasActive] = useState(active);
  if (active !== wasActive) {
    setWasActive(active);
    setLost(false);
  }

  useEffect(() => {
    if (!active) return undefined;
    const timer = setTimeout(() => {
      console.info("[room] not recovered after 60 s, showing \"Try again\"");
      setLost(true);
    }, GIVE_UP_MS);
    return () => clearTimeout(timer);
  }, [active, attempt]);

  const retry = useCallback(() => {
    setLost(false);
    setAttempt((n) => n + 1);
  }, []);

  return { status: issue && lost ? "lost" : issue, retry };
}
