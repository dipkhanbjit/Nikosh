import { useCallback, useEffect, useState } from "react";

const bySpokenOrder = (a, b) => a.start_s - b.start_s || a.seq - b.seq;

// Live transcript state for the interviewer room (7.3.1; the panel is 7.3.2).
// receive(message): a transcript-* event from the room socket:
//   transcript-snapshot (on join / reconnect: replaces everything), transcript-turn (open or
//   closed turn, replaced by seq), transcript-interim (empty text clears it), transcript-status.
// turns = [{ seq, speaker, text, start_s, end_s, confidence, incomplete, closed }] in spoken order;
// interims = { role: { text, start_s } }; status = { role: "active" | "reconnecting" | ... }.
export default function useLiveTranscript() {
  const [turns, setTurns] = useState([]);
  const [interims, setInterims] = useState({});
  const [status, setStatus] = useState({});

  const receive = useCallback((message) => {
    if (message.type === "transcript-snapshot") {
      setTurns([...message.turns].sort(bySpokenOrder));
      setInterims(message.interims || {});
      setStatus(message.status || {});
    } else if (message.type === "transcript-turn") {
      const turn = message.turn;
      setTurns((current) => [...current.filter((t) => t.seq !== turn.seq), turn].sort(bySpokenOrder));
    } else if (message.type === "transcript-interim") {
      setInterims((current) => {
        const next = { ...current };
        if (message.text) next[message.speaker] = { text: message.text, start_s: message.start_s };
        else delete next[message.speaker];
        return next;
      });
    } else if (message.type === "transcript-status") {
      setStatus((current) => ({ ...current, [message.speaker]: message.state }));
    }
  }, []);

  // TEMP (7.3.1 testing): remove with the 7.3.2 panel
  useEffect(() => {
    console.debug("[transcript]", { turns, interims, status });
  }, [turns, interims, status]);

  return { turns, interims, status, receive };
}
