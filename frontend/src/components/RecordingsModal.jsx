import { useEffect, useState } from "react";

import { audioPartUrl, listAudioParts } from "../api/interviews";
import { Alert, Badge, Modal, Spinner } from "./ui";

const ROLE_LABEL = { interviewer: ["blue", "Interviewer"], candidate: ["green", "Candidate"] };

// 135.4 → "02:15"; one hour or more → "1:02:15"
const formatSeconds = (value) => {
  const total = Math.round(value ?? 0);
  const h = Math.floor(total / 3600);
  const mm = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};

export default function RecordingsModal({ interview, onClose }) {
  const [parts, setParts] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!interview) return;
    setParts(null);
    setError("");
    listAudioParts(interview.id)
      .then(setParts)
      .catch((err) => setError(err.message));
  }, [interview]);

  return (
    <Modal open={Boolean(interview)} title="Recordings" onClose={onClose}>
      {interview && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-gray-600">
            {interview.candidate_name || "Candidate"} — {interview.job_title}. Each part is one microphone connection;
            the start time is counted from the start of the interview.
          </p>
          {error && <Alert type="error">{error}</Alert>}
          {!parts && !error && <Spinner />}
          {parts?.length === 0 && <p className="text-sm text-gray-500">No audio was recorded for this interview.</p>}
          {parts?.map((part) => {
            const [color, label] = ROLE_LABEL[part.role] ?? ["gray", part.role];
            return (
              <div key={part.id} className="rounded-md border border-gray-200 p-3">
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <Badge color={color}>{label}</Badge>
                    <span className="text-gray-700">Part {part.part_no}</span>
                  </span>
                  <span className="text-xs text-gray-500">
                    Starts at {formatSeconds(part.start_offset_s)} · {formatSeconds(part.duration_s)} long
                  </span>
                </div>
                <audio controls preload="none" className="w-full" src={audioPartUrl(interview.id, part.id)} />
              </div>
            );
          })}
        </div>
      )}
    </Modal>
  );
}
