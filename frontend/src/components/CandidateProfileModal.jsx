import { useState } from "react";

import { SCORE_DIMENSIONS } from "../api/jobs";
import { Badge, Button, Modal, Spinner } from "./ui";

const RATINGS = {
  met: { label: "Met", className: "bg-green-100 text-green-700" },
  partial: { label: "Partially Met", className: "bg-yellow-100 text-yellow-800" },
  unmet: { label: "Unmet", className: "bg-red-100 text-red-700" },
};

const STATUS_STYLE = {
  applied: ["bg-green-100 text-green-700", "Eligible"],
  excluded: ["bg-amber-100 text-amber-800", "Excluded"],
  rejected: ["bg-red-100 text-red-700", "Rejected"],
};

const OVERRIDE_LABEL = { included: "Manually included", excluded: "Manually excluded" };

const scoreColor = (score) =>
  score >= 70 ? "bg-green-500" : score >= 40 ? "bg-amber-500" : "bg-red-500";

function Section({ title, children }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</p>
      {children}
    </div>
  );
}

function Bar({ value, height = "h-2" }) {
  return (
    <div className={`${height} rounded-full bg-gray-200`}>
      {value != null && <div className={`${height} rounded-full ${scoreColor(value)}`} style={{ width: `${value}%` }} />}
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

function Summary({ candidate }) {
  const score = candidate.overall_score;
  const [style, label] = STATUS_STYLE[candidate.status] ?? ["bg-gray-100 text-gray-700", candidate.status];
  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
      <div className="flex items-center gap-6">
        <div>
          <p className="text-xs text-gray-500">Rank</p>
          <p className="text-2xl font-bold text-indigo-700">{candidate.rank != null ? `#${candidate.rank}` : "—"}</p>
        </div>
        <div className="flex-1">
          <div className="flex items-baseline justify-between">
            <p className="text-xs text-gray-500">Score</p>
            <p className="text-lg font-semibold text-gray-800">{score != null ? score.toFixed(1) : "—"}</p>
          </div>
          <div className="mt-1">
            <Bar value={score} />
          </div>
        </div>
        <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>{label}</span>
      </div>
      {candidate.override && (
        <p className="mt-3 text-sm text-purple-700">
          <span className="font-medium">{OVERRIDE_LABEL[candidate.override] ?? candidate.override}:</span>{" "}
          {candidate.override_reason}
        </p>
      )}
      {!candidate.override && candidate.rejection_reason && (
        <p className={`mt-3 text-sm ${candidate.status === "excluded" ? "text-amber-700" : "text-red-600"}`}>
          {candidate.rejection_reason}
        </p>
      )}
    </div>
  );
}

function ScoreBreakdown({ data }) {
  if (data.scoring_status === "failed") {
    return (
      <Section title="Score">
        <p className="text-sm text-red-600">Scoring failed: {data.scoring_error}</p>
      </Section>
    );
  }
  if (!data.scores) return null;
  const weights = data.weights || {};
  return (
    <Section title="Score">
      <div className="rounded-md border border-gray-200">
        <div className="flex items-center justify-between border-b border-gray-100 bg-indigo-50 p-3">
          <div>
            <p className="text-sm font-semibold text-indigo-900">Score</p>
            <p className="text-xs text-indigo-700">Weighted average of the dimension scores</p>
          </div>
          <p className="text-3xl font-bold text-indigo-700">{data.overall_score?.toFixed(1) ?? "—"}</p>
        </div>
        <ul className="divide-y divide-gray-100">
          {SCORE_DIMENSIONS.map((d) => {
            const s = data.scores[d.key];
            if (!s) return null;
            const weight = weights[d.key] ?? 0;
            const contribution = (s.score * weight) / 100;
            return (
              <li key={d.key} className="p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-gray-800">{d.label}</p>
                  <p className="text-xs text-gray-500">
                    <span className="text-sm font-semibold text-gray-800">{s.score}</span>/100 × {weight}% ={" "}
                    <span className="font-semibold text-indigo-700">{contribution.toFixed(1)} pts</span>
                  </p>
                </div>
                <div className="mt-2">
                  <Bar value={s.score} height="h-1.5" />
                </div>
                <p className="mt-2 text-sm text-gray-700">{s.justification}</p>
                {s.evidence?.length > 0 && (
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs italic text-gray-500">
                    {s.evidence.map((e, i) => (
                      <li key={i}>“{e}”</li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </Section>
  );
}

function RequirementMatch({ screening }) {
  const count = (rating) => screening.filter((m) => m.rating === rating).length;
  return (
    <Section title="Requirements">
      <p className="mb-2 text-sm text-gray-600">
        {count("met")} Met · {count("partial")} Partially Met · {count("unmet")} Unmet
      </p>
      <ul className="divide-y divide-gray-100 rounded-md border border-gray-200">
        {screening.map((m, i) => (
          <li key={m.id ?? i} className="p-3">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium text-gray-800">{m.text}</p>
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
  const candidate = viewing?.candidate;
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
      title={candidate?.full_name || candidate?.cv_filename || "Candidate"}
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
          {hasScreening && <Summary candidate={candidate} />}
          {candidate?.status === "applied" && <ScoreBreakdown data={data} />}
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