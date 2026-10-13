import { useEffect, useState } from "react";

import { cvUrl, getCVText } from "../../api/candidates";
import { ProfileView } from "../CandidateProfileModal";
import { Alert, Spinner } from "../ui";

const TABS = ["CV", "Transcript"];

function CvView({ candidateId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getCVText(candidateId)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [candidateId]);

  if (error) return <div className="p-4"><Alert type="error">{error}</Alert></div>;
  if (!data) return <div className="flex justify-center p-6 text-indigo-600"><Spinner /></div>;

  if (data.cv_filename?.toLowerCase().endsWith(".pdf")) {
    return <iframe title="Candidate CV" src={cvUrl(candidateId)} className="h-full w-full border-0" />;
  }
  if (data.profile) return <div className="p-4"><ProfileView profile={data.profile} /></div>;
  if (data.cv_text) return <pre className="whitespace-pre-wrap p-4 font-sans text-sm text-gray-700">{data.cv_text}</pre>;
  return <p className="p-4 text-sm text-gray-500">No CV content available.</p>;
}

// Interviewer-only right panel: candidate CV and (Module 7) the live transcript
export default function InterviewerPanel({ candidateId }) {
  const [tab, setTab] = useState("CV");

  return (
    <aside className="flex w-[26rem] shrink-0 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="flex shrink-0 border-b border-gray-200">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`flex-1 px-4 py-2.5 text-sm font-medium ${
              tab === t ? "border-b-2 border-indigo-600 text-indigo-700" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      {/* both tabs stay mounted so the CV is not reloaded when switching */}
      <div className={`min-h-0 flex-1 overflow-y-auto ${tab === "CV" ? "" : "hidden"}`}>
        <CvView candidateId={candidateId} />
      </div>
      <div className={`min-h-0 flex-1 overflow-y-auto ${tab === "Transcript" ? "" : "hidden"}`}>
        <p className="p-6 text-center text-sm text-gray-500">Live transcript will appear here.</p>
      </div>
    </aside>
  );
}
