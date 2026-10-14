import RecordingsList from "./RecordingsList";
import { Modal } from "./ui";

export default function RecordingsModal({ interview, onClose }) {
  return (
    <Modal open={Boolean(interview)} title="Recordings" onClose={onClose}>
      {interview && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-gray-600">
            {interview.candidate_name || "Candidate"} — {interview.job_title}. Each part is one microphone connection;
            the start time is counted from the start of the interview.
          </p>
          <RecordingsList key={interview.id} interviewId={interview.id} />
        </div>
      )}
    </Modal>
  );
}
