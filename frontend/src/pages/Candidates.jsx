import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getCVText, listCandidates } from "../api/candidates";
import {
  ACTIVE_INTERVIEW_STATUSES,
  INTERVIEW_STATUS,
  credentialsFrom,
  formatDateTime,
  getShortlist,
  isPast,
  listJobInterviews,
  reviewShortlist,
  scheduleInterview,
  startShortlist,
  toScheduledAt,
} from "../api/interviews";
import { getScoreWeights, listJobs } from "../api/jobs";
import CandidateProfileModal from "../components/CandidateProfileModal";
import CredentialsModal from "../components/CredentialsModal";
import ScheduleAssistant from "../components/ScheduleAssistant";
import { Alert, Badge, Button, Card, Input, Modal, PageHeader, Spinner, Table, Textarea } from "../components/ui";

const DEFAULT_TOP_N = 5;
const MAX_TOP_N = 50; // backend limit
const DEFAULT_DURATION = 30;
const MIN_DURATION = 15;
const MAX_DURATION = 120;
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/; // same check as the backend

const todayInDhaka = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Dhaka" });

const pillColor = (score) =>
  score >= 70
    ? "bg-green-100 text-green-800"
    : score >= 40
      ? "bg-amber-100 text-amber-800"
      : "bg-red-100 text-red-700";

export default function Candidates() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [jobId, setJobId] = useState("");
  const [shortlist, setShortlist] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [topN, setTopN] = useState(DEFAULT_TOP_N);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [approving, setApproving] = useState(false);
  const [sendBack, setSendBack] = useState(null); // { topN, removeIds }
  const [revising, setRevising] = useState(false);
  const [interviews, setInterviews] = useState([]);
  const [scheduling, setScheduling] = useState(null); // { item, email, date, time, duration, notes }
  const [savingInterview, setSavingInterview] = useState(false);
  const [credentials, setCredentials] = useState(null); // see credentialsFrom(), shown once
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    listJobs().then(setJobs).catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    setShortlist(null);
    setCandidates([]);
    setInterviews([]);
    setError("");
    setNotice("");
    if (!jobId) return;
    setLoading(true);
    Promise.all([getShortlist(jobId), listCandidates(jobId), listJobInterviews(jobId)])
      .then(([state, list, jobInterviews]) => {
        setShortlist(state);
        setCandidates(list);
        setInterviews(jobInterviews);
        setTopN(Math.min(state.top_n || DEFAULT_TOP_N, state.eligible_count) || DEFAULT_TOP_N);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [jobId]);

  const eligible = shortlist?.eligible_count ?? 0;
  const maxTopN = Math.min(eligible, MAX_TOP_N);
  const topNValid = Number.isInteger(topN) && topN >= 1 && topN <= maxTopN;

  const apply = async () => {
    setConfirmReplace(false);
    setApplying(true);
    setError("");
    setNotice("");
    try {
      setShortlist(await startShortlist(jobId, topN));
    } catch (err) {
      setError(err.message);
    } finally {
      setApplying(false);
    }
  };

  const review = async (setBusy, body, message) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setShortlist(await reviewShortlist(jobId, body));
      setSendBack(null);
      setNotice(message);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleApprove = () =>
    review(setApproving, { action: "approve" }, "Shortlist approved. You can now schedule interviews.");

  const openSendBack = () => setSendBack({ topN: shortlist.top_n, removeIds: [] });

  const toggleRemove = (id) =>
    setSendBack((prev) => ({
      ...prev,
      removeIds: prev.removeIds.includes(id) ? prev.removeIds.filter((x) => x !== id) : [...prev.removeIds, id],
    }));

  const sendBackTopNValid =
    Number.isInteger(sendBack?.topN) && sendBack.topN >= 1 && sendBack.topN <= maxTopN;
  const sendBackChanged = sendBack && (sendBack.topN !== shortlist?.top_n || sendBack.removeIds.length > 0);

  const handleSendBack = () =>
    review(
      setRevising,
      {
        action: "revise",
        top_n: sendBack.topN !== shortlist.top_n ? sendBack.topN : null,
        remove_ids: sendBack.removeIds,
      },
      "Shortlist revised. Please review the new proposal."
    );

  // Latest interview of a candidate (highest id = most recently created)
  const interviewOf = (candidateId) =>
    interviews.filter((iv) => iv.candidate_id === candidateId).sort((a, b) => b.id - a.id)[0];

  const openSchedule = (item) =>
    setScheduling({ item, email: item.email || "", date: "", time: "", duration: DEFAULT_DURATION, notes: "" });

  const scheduleInPast = scheduling?.date && scheduling?.time && isPast(scheduling.date, scheduling.time);
  const durationValid =
    Number.isInteger(scheduling?.duration) &&
    scheduling.duration >= MIN_DURATION &&
    scheduling.duration <= MAX_DURATION;
  const emailValid = EMAIL_PATTERN.test(scheduling?.email?.trim() || "");
  const scheduleValid = scheduling?.date && scheduling?.time && !scheduleInPast && durationValid && emailValid;

  // After the scheduling assistant confirms a plan: show the new interview statuses
  const handleAssistantScheduled = async () => {
    try {
      const [list, jobInterviews] = await Promise.all([listCandidates(jobId), listJobInterviews(jobId)]);
      setCandidates(list);
      setInterviews(jobInterviews);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSchedule = async () => {
    const { item, email, date, time, duration, notes } = scheduling;
    setSavingInterview(true);
    setError("");
    setNotice("");
    try {
      const interview = await scheduleInterview(jobId, {
        candidate_id: item.candidate_id,
        scheduled_at: toScheduledAt(date, time),
        duration_minutes: duration,
        notes: notes.trim() || null,
        contact_email: email.trim().toLowerCase(),
      });
      setScheduling(null);
      setCredentials(credentialsFrom(interview));
      setInterviews(await listJobInterviews(jobId));
      setNotice(
        `Interview scheduled for ${interview.candidate_name || "the candidate"} on ${formatDateTime(interview.scheduled_at)}.`
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingInterview(false);
    }
  };

  const handleApply = () => (shortlist?.status === "approved" ? setConfirmReplace(true) : apply());

  const openProfile = async (item) => {
    const candidate = candidates.find((c) => c.id === item.candidate_id);
    if (!candidate) return;
    setViewing({ candidate, data: null });
    try {
      const [data, weights] = await Promise.all([getCVText(candidate.id), getScoreWeights(jobId)]);
      setViewing({ candidate, data: { ...data, weights: weights.weights } });
    } catch (err) {
      setViewing(null);
      setError(err.message);
    }
  };

  const columns = [
    {
      key: "rank",
      label: "Rank",
      render: (i) => <span className="text-sm font-bold text-indigo-700">#{i.rank}</span>,
    },
    {
      key: "name",
      label: "Candidate",
      render: (i) => <span className="font-medium text-gray-800">{i.full_name || "Name not found"}</span>,
    },
    { key: "email", label: "Email", render: (i) => i.email || "—" },
    {
      key: "score",
      label: "Score",
      render: (i) =>
        i.score != null ? (
          <span className={`inline-block rounded-md px-2 py-1 text-sm font-semibold ${pillColor(i.score)}`}>
            {i.score.toFixed(1)}
          </span>
        ) : (
          "—"
        ),
    },
    {
      key: "requirements",
      label: "Requirements",
      render: (i) => (
        <p className="text-xs text-gray-600">
          <span className="font-medium text-green-700">{i.met} met</span>
          {" · "}
          <span className="font-medium text-amber-700">{i.partial} partial</span>
        </p>
      ),
    },
    {
      key: "profile",
      label: "Profile",
      render: (i) => (
        <Button variant="secondary" className="px-3 py-1" onClick={() => openProfile(i)}>
          View
        </Button>
      ),
    },
  ];

  const shortlistedColumns = [
    ...columns,
    {
      key: "interview",
      label: "Interview",
      render: (i) => {
        const iv = interviewOf(i.candidate_id);
        if (!iv) return <Badge color="gray">Not scheduled</Badge>;
        const [color, label] = INTERVIEW_STATUS[iv.status] ?? ["gray", iv.status];
        return (
          <div>
            <Badge color={color}>{label}</Badge>
            <p className="mt-1 text-xs text-gray-500">{formatDateTime(iv.scheduled_at)}</p>
          </div>
        );
      },
    },
    {
      key: "actions",
      label: "",
      render: (i) => {
        const iv = interviewOf(i.candidate_id);
        const active = iv && ACTIVE_INTERVIEW_STATUSES.includes(iv.status);
        return (
          <div className="flex justify-end gap-2">
            {iv?.status === "completed" && (
              <Button
                variant="secondary"
                className="px-3 py-1"
                onClick={() => navigate(`/candidates/${i.candidate_id}/assessment?interview=${iv.id}`)}
              >
                Assessment
              </Button>
            )}
            <Button
              className="px-3 py-1"
              onClick={() => openSchedule(i)}
              disabled={active}
              title={active ? "Interview already scheduled" : ""}
            >
              Schedule
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Candidates" subtitle="Shortlist ranked candidates and schedule interviews." />

      {error && <Alert type="error">{error}</Alert>}
      {notice && <Alert type="success">{notice}</Alert>}

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex min-w-[16rem] flex-col gap-1">
            <label htmlFor="job" className="text-sm font-medium text-gray-700">
              Job
            </label>
            <select
              id="job"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Select a job…</option>
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title}
                </option>
              ))}
            </select>
          </div>

          {shortlist && (
            <>
              <div className="w-28">
                <Input
                  label="Top N"
                  name="top_n"
                  type="number"
                  min={1}
                  max={maxTopN}
                  value={Number.isNaN(topN) ? "" : topN}
                  onChange={(e) => setTopN(parseInt(e.target.value, 10))}
                  disabled={eligible === 0}
                />
              </div>
              <Button onClick={handleApply} loading={applying} disabled={!topNValid}>
                Apply
              </Button>
              <p className="pb-2 text-sm text-gray-500">{eligible} eligible candidates</p>
            </>
          )}
        </div>

        {shortlist && eligible === 0 && (
          <div className="mt-4">
            <Alert type="info">
              No eligible scored candidates for this job yet. Screen and score CVs on the job page first.
            </Alert>
          </div>
        )}
        {shortlist && eligible > 0 && !topNValid && (
          <p className="mt-2 text-sm text-red-600">Top N must be between 1 and {maxTopN}.</p>
        )}
      </Card>

      {loading && (
        <div className="flex justify-center text-indigo-600">
          <Spinner />
        </div>
      )}

      {shortlist?.status === "awaiting_review" && (
        <Card
          title={`Proposed shortlist (top ${shortlist.top_n})`}
          actions={
            <>
              <Button variant="secondary" onClick={openSendBack} disabled={approving}>
                Send back
              </Button>
              <Button onClick={handleApprove} loading={approving} disabled={shortlist.items.length === 0}>
                Approve shortlist
              </Button>
            </>
          }
        >
          <Table columns={columns} data={shortlist.items} emptyMessage="No candidates proposed." />
        </Card>
      )}

      {shortlist?.status === "approved" && (
        <Card title={`Shortlisted candidates (${shortlist.items.length})`}>
          <Table columns={shortlistedColumns} data={shortlist.items} emptyMessage="No shortlisted candidates." />
        </Card>
      )}

      <CandidateProfileModal viewing={viewing} onClose={() => setViewing(null)} />

      <Modal
        open={Boolean(sendBack)}
        title="Send Back Shortlist"
        onClose={() => setSendBack(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSendBack(null)} disabled={revising}>
              Cancel
            </Button>
            <Button onClick={handleSendBack} loading={revising} disabled={!sendBackTopNValid || !sendBackChanged}>
              Send back
            </Button>
          </>
        }
      >
        {sendBack && (
          <div className="flex flex-col gap-4">
            <div className="w-28">
              <Input
                label="Top N"
                name="revise_top_n"
                type="number"
                min={1}
                max={maxTopN}
                value={Number.isNaN(sendBack.topN) ? "" : sendBack.topN}
                onChange={(e) => setSendBack({ ...sendBack, topN: parseInt(e.target.value, 10) })}
              />
            </div>
            {!sendBackTopNValid && <p className="text-sm text-red-600">Top N must be between 1 and {maxTopN}.</p>}
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium text-gray-700">Remove candidates</p>
              {shortlist.items.map((i) => (
                <label key={i.candidate_id} className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={sendBack.removeIds.includes(i.candidate_id)}
                    onChange={() => toggleRemove(i.candidate_id)}
                    className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  #{i.rank} {i.full_name || "Name not found"}
                </label>
              ))}
            </div>
            <p className="text-xs text-gray-500">
              Removed candidates are replaced by the next ranked candidates to keep the list at N.
            </p>
          </div>
        )}
      </Modal>

      <Modal
        open={Boolean(scheduling)}
        title="Schedule Interview"
        onClose={() => setScheduling(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setScheduling(null)} disabled={savingInterview}>
              Cancel
            </Button>
            <Button onClick={handleSchedule} loading={savingInterview} disabled={!scheduleValid}>
              Schedule
            </Button>
          </>
        }
      >
        {scheduling && (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-gray-700">
              Interview with <span className="font-semibold">{scheduling.item.full_name || "this candidate"}</span>.
              Times are in Bangladesh time (GMT+6).
            </p>
            <div>
              <Input
                label="Contact email"
                name="contact_email"
                type="email"
                required
                value={scheduling.email}
                onChange={(e) => setScheduling({ ...scheduling, email: e.target.value })}
              />
              <p className="mt-1 text-xs text-gray-500">Login details and the invitation are sent to this address.</p>
              {scheduling.email.trim() && !emailValid && (
                <p className="mt-1 text-sm text-red-600">Enter a valid email address.</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Date"
                name="interview_date"
                type="date"
                min={todayInDhaka()}
                value={scheduling.date}
                onChange={(e) => setScheduling({ ...scheduling, date: e.target.value })}
              />
              <Input
                label="Time"
                name="interview_time"
                type="time"
                value={scheduling.time}
                onChange={(e) => setScheduling({ ...scheduling, time: e.target.value })}
              />
            </div>
            {scheduleInPast && <p className="text-sm text-red-600">Interview time must be in the future.</p>}
            <div className="w-40">
              <Input
                label="Duration (minutes)"
                name="interview_duration"
                type="number"
                min={MIN_DURATION}
                max={MAX_DURATION}
                step={5}
                value={Number.isNaN(scheduling.duration) ? "" : scheduling.duration}
                onChange={(e) => setScheduling({ ...scheduling, duration: parseInt(e.target.value, 10) })}
              />
            </div>
            {!durationValid && (
              <p className="text-sm text-red-600">
                Duration must be between {MIN_DURATION} and {MAX_DURATION} minutes.
              </p>
            )}
            <Textarea
              label="Notes"
              name="interview_notes"
              rows={3}
              maxLength={1000}
              value={scheduling.notes}
              onChange={(e) => setScheduling({ ...scheduling, notes: e.target.value })}
              placeholder="Optional notes for this interview"
            />
          </div>
        )}
      </Modal>

      <CredentialsModal credentials={credentials} onClose={() => setCredentials(null)} />

      <Modal
        open={confirmReplace}
        title="Replace Shortlist"
        onClose={() => setConfirmReplace(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmReplace(false)}>
              Cancel
            </Button>
            <Button onClick={apply}>Continue</Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">
          This job already has an approved shortlist. Applying will propose a new top {topN} for review and,
          once approved, replace the current shortlist. Candidates with an active interview stay shortlisted.
        </p>
      </Modal>

      <ScheduleAssistant
        jobId={jobId}
        jobTitle={jobs.find((job) => String(job.id) === jobId)?.title}
        hasShortlist={shortlist?.status === "approved"}
        onScheduled={handleAssistantScheduled}
      />
    </div>
  );
}
