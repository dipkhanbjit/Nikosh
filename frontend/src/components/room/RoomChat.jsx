import { useEffect, useRef, useState } from "react";

import { CHAT_FILE_TYPES, CHAT_MAX_FILE_MB, chatFileUrl, uploadChatFile } from "../../api/interviewChat";
import { Spinner } from "../ui";

const URL_PATTERN = /(https?:\/\/[^\s<>"]+)/g;

const formatTime = (iso) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Dhaka" });

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Plain text with http(s) links made clickable. React escapes the text, so no HTML is injected.
function LinkedText({ text }) {
  return text.split(URL_PATTERN).map((part, i) => {
    if (i % 2 === 0) return part;
    const trailing = part.match(/[.,;:!?)\]]+$/)?.[0] || ""; // "see https://x.com." keeps the dot outside
    const url = trailing ? part.slice(0, -trailing.length) : part;
    return (
      <span key={i}>
        <a href={url} target="_blank" rel="noopener noreferrer" className="break-all underline">
          {url}
        </a>
        {trailing}
      </span>
    );
  });
}

function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5 shrink-0">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}

function PaperclipIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
      <path d="M21 11.5 12.5 20a5 5 0 0 1-7-7L14 4.5a3.5 3.5 0 0 1 5 5L10.5 18a2 2 0 0 1-3-3L15 7.5" />
    </svg>
  );
}

function Bubble({ message, own, interviewId }) {
  return (
    <div className={`flex flex-col ${own ? "items-end" : "items-start"}`}>
      <p className="mb-0.5 px-1 text-[11px] text-gray-500">
        {own ? "You" : message.sender_name || message.sender_role} · {formatTime(message.created_at)}
      </p>
      <div
        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
          own ? "rounded-br-sm bg-indigo-600 text-white" : "rounded-bl-sm bg-gray-100 text-gray-800"
        }`}
      >
        {message.file_name ? (
          <a
            href={chatFileUrl(interviewId, message.id)}
            download={message.file_name}
            className="flex items-center gap-2 hover:underline"
          >
            <FileIcon />
            <span className="min-w-0">
              <span className="block truncate font-medium">{message.file_name}</span>
              <span className={`block text-xs ${own ? "text-indigo-100" : "text-gray-500"}`}>
                {formatSize(message.file_size)}
              </span>
            </span>
          </a>
        ) : (
          <p className="whitespace-pre-wrap break-words">
            <LinkedText text={message.text || ""} />
          </p>
        )}
      </div>
    </div>
  );
}

// In-call chat panel (both sides). Messages come from useRoomChat; text is sent over the room
// socket (onSend returns false if not connected), files through the upload endpoint.
// offline: own room socket is down; input is disabled (nothing queued, the draft is kept) until it is back.
export default function RoomChat({ interviewId, ownRole, messages, loadError, onSend, onUploaded, readOnly, offline }) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const bottomRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const send = () => {
    const value = text.trim();
    if (!value || readOnly || offline) return;
    if (!onSend(value)) {
      setError("Not connected. Please wait a moment and try again.");
      return;
    }
    setText("");
    setError("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // the same file can be chosen again
    if (!file) return;
    const ext = `.${file.name.split(".").pop().toLowerCase()}`;
    if (!CHAT_FILE_TYPES.split(",").includes(ext)) {
      setError("Allowed files: TXT, PDF, Word, Excel and PowerPoint.");
      return;
    }
    if (file.size > CHAT_MAX_FILE_MB * 1024 * 1024) {
      setError(`The file is larger than ${CHAT_MAX_FILE_MB} MB.`);
      return;
    }
    setUploading(true);
    setError("");
    try {
      onUploaded(await uploadChatFile(interviewId, file));
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {loadError && <p className="text-center text-xs text-red-600">{loadError}</p>}
        {messages.length === 0 && !loadError && (
          <p className="py-8 text-center text-sm text-gray-500">
            {readOnly ? "No messages were sent." : "Messages and files you share appear here."}
          </p>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} message={m} own={m.sender_role === ownRole} interviewId={interviewId} />
        ))}
        <div ref={bottomRef} />
      </div>

      {readOnly ? (
        <p className="shrink-0 border-t border-gray-200 px-3 py-2.5 text-center text-xs text-gray-500">
          The interview has ended. The chat is read-only.
        </p>
      ) : (
        <div className="shrink-0 border-t border-gray-200 p-2.5">
          {offline ? (
            <p className="mb-1.5 px-1 text-xs text-amber-700">You&apos;re offline - reconnecting...</p>
          ) : (
            error && <p className="mb-1.5 px-1 text-xs text-red-600">{error}</p>
          )}
          <div className="flex items-end gap-1.5">
            <input ref={fileRef} type="file" accept={CHAT_FILE_TYPES} onChange={handleFile} className="hidden" />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={uploading || offline}
              title={`Share a file (max ${CHAT_MAX_FILE_MB} MB)`}
              aria-label="Share a file"
              className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed"
            >
              {uploading ? <Spinner size="sm" /> : <PaperclipIcon />}
            </button>
            <textarea
              rows={1}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Send a message"
              disabled={offline}
              maxLength={2000}
              className="max-h-24 min-h-9 flex-1 resize-none rounded-2xl border border-gray-300 px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-400"
            />
            <button
              type="button"
              onClick={send}
              disabled={!text.trim() || offline}
              className="h-9 shrink-0 cursor-pointer rounded-full bg-indigo-600 px-3.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
