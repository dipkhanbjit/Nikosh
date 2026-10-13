import { useCallback, useEffect, useState } from "react";

import { getChatMessages } from "../api/interviewChat";

// In-call chat state for the interview room.
//   ownRole: "interviewer" / "candidate"; open: the chat panel is visible
// receive(message): a "chat" event from the room socket (or an upload response);
// reload(): load the history again (e.g. after the socket reconnected).
// unread = messages from the other side that arrived while the panel was closed.
export default function useRoomChat(interviewId, { ownRole, open }) {
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState("");
  const [unread, setUnread] = useState(0);
  const [wasOpen, setWasOpen] = useState(open);

  // Opening the panel marks everything as read
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) setUnread(0);
  }

  // Merge by id (history and live messages can overlap) and keep server order
  const merge = useCallback((incoming) => {
    setMessages((current) => {
      const byId = new Map(current.map((m) => [m.id, m]));
      incoming.forEach((m) => byId.set(m.id, m));
      return [...byId.values()].sort((a, b) => a.id - b.id);
    });
  }, []);

  const reload = useCallback(() => {
    if (!interviewId) return;
    getChatMessages(interviewId)
      .then((list) => {
        merge(list);
        setError("");
      })
      .catch(() => setError("Could not load the chat history."));
  }, [interviewId, merge]);

  useEffect(reload, [reload]);

  const receive = useCallback(
    (message) => {
      merge([message]);
      if (message.sender_role !== ownRole && !open) setUnread((n) => n + 1);
    },
    [merge, ownRole, open],
  );

  return { messages, error, unread, receive, reload };
}
