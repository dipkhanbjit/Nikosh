import { useEffect, useRef, useState } from "react";

import { TranscriptIcon } from "./icons";

const STATUS_LABELS = {
  active: "Live",
  reconnecting: "Reconnecting…",
  unavailable: "Unavailable",
  off: "Off",
  stub: "Test mode",
};

// Seconds since the interview start as mm:ss
function formatOffset(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function Bubble({ speaker, label, startS, text, incomplete, interim }) {
  const own = speaker === "interviewer";
  let style;
  if (interim) style = own ? "bg-indigo-50 text-indigo-700 italic" : "border border-gray-200 bg-gray-50 text-gray-500 italic";
  else style = own ? "bg-indigo-600 text-white" : "border border-gray-200 bg-white text-gray-900";
  const meta = own && !interim ? "text-indigo-100" : "text-gray-400";

  return (
    <div className={`flex ${own ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[75%] rounded-xl px-3 py-1.5 text-sm ${style}`}>
        <p className={`text-[11px] ${meta}`}>
          {label} · {formatOffset(startS)}
          {incomplete && " (incomplete)"}
        </p>
        <p className="break-words whitespace-pre-wrap">{text}</p>
      </div>
    </div>
  );
}

// Interviewer only (7.3.2): turns, interims and status come from useLiveTranscript
export default function LiveTranscript({ turns, interims, status, candidateName }) {
  const listRef = useRef(null);
  const [atBottom, setAtBottom] = useState(true);
  const labels = { interviewer: "Interviewer", candidate: candidateName || "Candidate" };

  const interimList = Object.entries(interims)
    .map(([speaker, interim]) => ({ speaker, ...interim }))
    .sort((a, b) => (a.start_s ?? Infinity) - (b.start_s ?? Infinity));

  // Follow new text only while the user is at the bottom
  useEffect(() => {
    const el = listRef.current;
    if (el && atBottom) el.scrollTop = el.scrollHeight;
  }, [turns, interims, atBottom]);

  const handleScroll = () => {
    const el = listRef.current;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 40);
  };

  const scrollToLatest = () => {
    const el = listRef.current;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  };

  const empty = turns.length === 0 && interimList.length === 0;

  return (
    <section className="flex h-48 shrink-0 flex-col rounded-2xl border border-gray-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-4 border-b border-gray-100 px-4 py-2">
        <span className="flex items-center gap-2 text-sm font-semibold text-gray-900">
          <TranscriptIcon className="h-4 w-4 text-gray-500" />
          Live transcript
        </span>
        <span className="flex min-w-0 gap-4 truncate text-xs text-gray-500">
          {["interviewer", "candidate"].map((speaker) => (
            <span key={speaker} className="truncate">
              {labels[speaker]} · {STATUS_LABELS[status[speaker]] || "—"}
            </span>
          ))}
        </span>
      </div>

      <div className="relative min-h-0 flex-1">
        <div ref={listRef} onScroll={handleScroll} className="flex h-full flex-col gap-2 overflow-y-auto px-4 py-3">
          {empty && (
            <p className="flex flex-1 items-center justify-center text-sm text-gray-500">
              The transcript will appear here.
            </p>
          )}
          {turns.map((turn) => (
            <Bubble
              key={turn.seq}
              speaker={turn.speaker}
              label={labels[turn.speaker] || turn.speaker}
              startS={turn.start_s}
              text={turn.text}
              incomplete={turn.incomplete}
            />
          ))}
          {interimList.map((interim) => (
            <Bubble
              key={`interim-${interim.speaker}`}
              speaker={interim.speaker}
              label={labels[interim.speaker] || interim.speaker}
              startS={interim.start_s}
              text={interim.text}
              interim
            />
          ))}
        </div>

        {!atBottom && (
          <button
            type="button"
            onClick={scrollToLatest}
            className="absolute bottom-2 left-1/2 -translate-x-1/2 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50"
          >
            Latest ↓
          </button>
        )}
      </div>
    </section>
  );
}
