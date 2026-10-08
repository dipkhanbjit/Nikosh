import { useState } from "react";

import { Badge, Button, Modal, Spinner } from "./ui";

function Section({ title, children }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</p>
      {children}
    </div>
  );
}

const period = (start, end) => [start || "?", end || "?"].join(" – ");

function ProfileView({ profile }) {
  return (
    <div className="flex flex-col gap-5 text-sm">
      {profile.summary && <p className="leading-relaxed text-gray-700">{profile.summary}</p>}

      <div className="flex gap-8">
        <div>
          <p className="text-xs text-gray-500">Total Experience</p>
          <p className="font-semibold text-gray-800">
            {profile.total_experience_years != null ? `${profile.total_experience_years} years` : "Not stated"}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Skills</p>
          <p className="font-semibold text-gray-800">{profile.skills.length}</p>
        </div>
      </div>

      {profile.skills.length > 0 && (
        <Section title="Skills">
          <div className="flex flex-wrap gap-1.5">
            {profile.skills.map((s) => (
              <Badge key={s} color="gray">
                {s}
              </Badge>
            ))}
          </div>
        </Section>
      )}

      {profile.work_history.length > 0 && (
        <Section title="Work History">
          <ul className="divide-y divide-gray-100">
            {profile.work_history.map((w, i) => (
              <li key={i} className="py-2">
                <div className="flex justify-between gap-3">
                  <p className="font-medium text-gray-800">
                    {w.title}
                    {w.company && <span className="font-normal text-gray-500"> · {w.company}</span>}
                  </p>
                  <span className="shrink-0 text-xs text-gray-500">{period(w.start_date, w.end_date)}</span>
                </div>
                {w.summary && <p className="mt-1 text-gray-600">{w.summary}</p>}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {profile.education.length > 0 && (
        <Section title="Education">
          <ul className="divide-y divide-gray-100">
            {profile.education.map((e, i) => (
              <li key={i} className="flex justify-between gap-3 py-2">
                <div>
                  <p className="font-medium text-gray-800">
                    {e.degree}
                    {e.field && ` in ${e.field}`}
                  </p>
                  <p className="text-gray-500">
                    {[e.institution, e.result].filter(Boolean).join(" · ")}
                  </p>
                </div>
                {e.graduation_year && <span className="shrink-0 text-xs text-gray-500">{e.graduation_year}</span>}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {profile.certifications.length > 0 && (
        <Section title="Certifications">
          <ul className="list-disc space-y-1 pl-5 text-gray-700">
            {profile.certifications.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

export default function CandidateProfileModal({ viewing, onClose }) {
  const [showText, setShowText] = useState(false);
  const data = viewing?.data;
  const hasProfile = Boolean(data?.profile);

  const close = () => {
    setShowText(false);
    onClose();
  };

  return (
    <Modal
      open={Boolean(viewing)}
      title={viewing?.candidate.full_name || viewing?.candidate.cv_filename || "Candidate"}
      onClose={close}
      footer={
        <>
          {hasProfile && (
            <Button variant="secondary" onClick={() => setShowText(!showText)}>
              {showText ? "Show Profile" : "Show Raw Text"}
            </Button>
          )}
          <Button variant="secondary" onClick={close}>
            Close
          </Button>
        </>
      }
    >
      {!data ? (
        <div className="flex justify-center py-8 text-indigo-600">
          <Spinner />
        </div>
      ) : hasProfile && !showText ? (
        <div className="max-h-[60vh] overflow-y-auto pr-1">
          <ProfileView profile={data.profile} />
        </div>
      ) : (
        <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded-md bg-gray-50 p-3 font-sans text-xs leading-relaxed text-gray-700">
          {data.cv_text || "No text available."}
        </pre>
      )}
    </Modal>
  );
}