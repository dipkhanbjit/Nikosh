import { useEffect, useRef, useState } from "react";

import { Alert, Button, Spinner } from "./ui";

// Optional: m.sources is shown under a message; error is shown inline below the messages
export default function ChatPanel({ messages, onSend, loading, disabled, placeholder, emptyText, error }) {
  const [text, setText] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, error]);

  const send = () => {
    const value = text.trim();
    if (!value || loading || disabled) return;
    onSend(value);
    setText("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && !loading && (
          <p className="py-8 text-center text-sm text-gray-500">{emptyText}</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
                m.role === "user" ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-800"
              }`}
            >
              {m.content}
              {m.sources?.length > 0 && (
                <p className="mt-2 border-t border-gray-200 pt-1.5 text-xs text-gray-500">
                  Sources: {m.sources.join(", ")}
                </p>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Spinner size="sm" /> Generating…
          </div>
        )}
        {error && !loading && <Alert type="error">{error}</Alert>}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2 border-t border-gray-200 p-3">
        <textarea
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={loading || disabled}
          className="flex-1 resize-none rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-50"
        />
        <Button onClick={send} disabled={!text.trim() || disabled} loading={loading} className="self-end">
          Send
        </Button>
      </div>
    </div>
  );
}