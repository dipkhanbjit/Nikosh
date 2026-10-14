// Seconds since the interview start as mm:ss
function formatOffset(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

// One transcript turn: interviewer right (indigo), candidate left (white); interims grey italic
export default function TranscriptBubble({ speaker, label, startS, text, incomplete, interim }) {
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
