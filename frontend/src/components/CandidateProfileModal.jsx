import { useState } from "react";

import { Badge, Button, Modal, Spinner } from "./ui";

const RATINGS = {
  met: { label: "Met", className: "bg-green-100 text-green-700" },
  partial: { label: "Partially Met", className: "bg-yellow-100 text-yellow-800" },
  unmet: { label: "Unmet", className: "bg-red-100 text-red-700" },
};

function Section({ title, children }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</p>
      {children}
    </div>
  );
}

function RatingBadge({ rating }) {
  const r = RATINGS[rating] ?? { label: rating, className: "bg-gray-100 text-gray-700" };
  return (
    <span className={`inline-block shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${r.className}`}>
      {r.label}
    </span>
  );
}

const period = (start, end) => [start || "?", end || "?"].join(" – ");

function RequirementMatch({ screening }) {
  const count = (rating) => screening.filter((m) => m.rating === rating).length;
  return (
    <Section title="Requirement Match">
      <p className="mb-2 text-sm text-gray-600">
        {count("met")} Met · {count("partial")} Partially Met · {count("unmet")} Unmet
      </p>
      <ul className="divide-y divide-gray-100 rounded-md border border-gray-200">
        {screening.map((m) => (
          <li key={m.id} className="p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-gray-800">{m.text}</p>
                <p className="text-xs text-gray-500">
                  {m.mandatory ? "Mandatory" : "Preferred"} · Weight {m.weight}
                </p>
              </div>
              <RatingBadge rating={m.rating} />
            </div>
            <p className="mt-2 text-sm italic text-gray-600">{m.evidence}</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}

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
                  <p className="text-gray-500">{[e.institution, e.result].filter(Boolean).join(" · ")}</p>
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
  const hasScreening = Array.isArray(data?.screening) && data.screening.length > 0;

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
        <div className="flex max-h-[60vh] flex-col gap-6 overflow-y-auto pr-1">
          {hasScreening && <RequirementMatch screening={data.screening} />}
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