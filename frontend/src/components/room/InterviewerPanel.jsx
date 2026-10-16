import { useEffect, useState } from "react";

import { cvUrl, getCVText } from "../../api/candidates";
import { ProfileView } from "../CandidateProfileModal";
import { Alert, Badge, Button, Spinner } from "../ui";
import AssistantTab from "./AssistantTab";

const TABS = ["AI Assistant", "Candidate"];
const TOP_SKILLS = 8;

// Latest education: highest graduation year, else the first one listed
function latestEducation(education = []) {
  if (!education.length) return null;
  return [...education].sort((a, b) => (b.graduation_year || 0) - (a.graduation_year || 0))[0];
}

function Field({ label, children }) {
  return (
    <div>
      <p className="text-xs font-medium tracking-wide text-gray-500 uppercase">{label}</p>
      <div className="mt-0.5 text-sm text-gray-800">{children || <span className="text-gray-400">Not available</span>}</div>
    </div>
  );
}

function CandidateDetails({ data, onOpenCv }) {
  const profile = data.profile || {};
  const latestRole = profile.work_history?.[0];
  const education = latestEducation(profile.education);
  const skills = (profile.skills || []).slice(0, TOP_SKILLS);
  const years = profile.total_experience_years;

  return (
    <div className="flex flex-col gap-5 p-4">
      <div className="flex flex-col gap-3">
        <p className="text-base font-semibold text-gray-900">{data.full_name || profile.full_name || "Candidate"}</p>
        <Field label="Phone">{data.phone}</Field>
        <Field label="Email">
          {data.email && (
            <a href={`mailto:${data.email}`} className="break-all text-indigo-600 hover:underline">
              {data.email}
            </a>
          )}
        </Field>
      </div>

      <div className="flex flex-col gap-3 border-t border-gray-100 pt-4">
        <p className="text-sm font-semibold text-gray-900">Key highlights</p>
        <Field label="Total experience">{years != null && `${years} ${years === 1 ? "year" : "years"}`}</Field>
        <Field label="Latest role">
          {latestRole && (
            <>
              {latestRole.title}
              {latestRole.company && <span className="text-gray-500"> · {latestRole.company}</span>}
            </>
          )}
        </Field>
        <Field label="Education">
          {education && (
            <>
              {education.degree}
              {education.field && ` in ${education.field}`}
              {(education.institution || education.graduation_year) && (
                <span className="block text-gray-500">
                  {[education.institution, education.graduation_year].filter(Boolean).join(" · ")}
                </span>
              )}
            </>
          )}
        </Field>
        <Field label="Top skills">
          {skills.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1.5">
              {skills.map((s) => (
                <Badge key={s} color="gray">
                  {s}
                </Badge>
              ))}
            </div>
          )}
        </Field>
      </div>

      <Button variant="secondary" onClick={onOpenCv} disabled={!data.cv_filename && !data.cv_text}>
        Open CV
      </Button>
    </div>
  );
}

// PDF inline; DOCX as the parsed profile, else the extracted text
function CvView({ candidateId, data }) {
  if (data.cv_filename?.toLowerCase().endsWith(".pdf")) {
    return <iframe title="Candidate CV" src={cvUrl(candidateId)} className="h-full w-full border-0" />;
  }
  if (data.profile) return <div className="p-4"><ProfileView profile={data.profile} /></div>;
  if (data.cv_text) return <pre className="whitespace-pre-wrap p-4 font-sans text-sm text-gray-700">{data.cv_text}</pre>;
  return <p className="p-4 text-sm text-gray-500">No CV content available.</p>;
}

function CandidateTab({ candidateId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [showCv, setShowCv] = useState(false);

  useEffect(() => {
    getCVText(candidateId)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [candidateId]);

  if (error) return <div className="p-4"><Alert type="error">{error}</Alert></div>;
  if (!data) return <div className="flex justify-center p-6 text-indigo-600"><Spinner /></div>;

  if (showCv) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center justify-between border-b border-gray-100 px-4 py-2">
          <button type="button" onClick={() => setShowCv(false)} className="text-sm font-medium text-indigo-600 hover:underline">
            ← Back
          </button>
          <span className="truncate pl-3 text-xs text-gray-500">{data.cv_filename}</span>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <CvView candidateId={candidateId} data={data} />
        </div>
      </div>
    );
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <CandidateDetails data={data} onOpenCv={() => setShowCv(true)} />
    </div>
  );
}

// Interviewer-only left panel: AI Assistant (co-pilot) and candidate details / CV
export default function InterviewerPanel({ interviewId, candidateId }) {
  const [tab, setTab] = useState("Candidate");

  return (
    <>
      <div className="flex shrink-0 gap-1 border-b border-gray-200 px-2">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-3 py-2.5 text-sm font-medium ${
              tab === t ? "border-indigo-600 text-indigo-700" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      {/* both tabs stay mounted so the CV and the co-pilot chat survive switching */}
      <div className={`min-h-0 flex-1 flex-col ${tab === "AI Assistant" ? "flex" : "hidden"}`}>
        <AssistantTab interviewId={interviewId} />
      </div>
      <div className={`min-h-0 flex-1 flex-col ${tab === "Candidate" ? "flex" : "hidden"}`}>
        <CandidateTab candidateId={candidateId} />
      </div>
    </>
  );
}
