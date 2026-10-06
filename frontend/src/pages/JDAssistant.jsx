import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { generateJD, getJD, getJob, reviewJD } from "../api/jobs";
import ChatPanel from "../components/ChatPanel";
import MarkdownView from "../components/MarkdownView";
import RequirementsEditor from "../components/RequirementsEditor";
import { Alert, Badge, Button, Card, PageHeader, Spinner, Textarea } from "../components/ui";

const STATUS_INFO = {
  not_started: {
    badge: ["gray", "Not started"],
    hint: "Describe the role in the chat. The assistant drafts the JD from company documents.",
    placeholder: "e.g. Senior backend engineer for our fintech APIs, hybrid in Dhaka…",
  },
  awaiting_review: {
    badge: ["yellow", "Awaiting review"],
    hint: "Review the draft. Send feedback in the chat to refine it, or edit it directly and approve.",
    placeholder: "e.g. Make it shorter and add Kafka as a preferred skill…",
  },
  approved: {
    badge: ["green", "Approved"],
    hint: "This JD is approved. Send a message to revise it.",
    placeholder: "e.g. Add a responsibility for on-call support…",
  },
};

export default function JDAssistant() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [jd, setJd] = useState(null);
  const [pending, setPending] = useState(null);
  const [sending, setSending] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [draftText, setDraftText] = useState("");
  const [draftReqs, setDraftReqs] = useState([]);

  const applyState = (state) => {
    setJd(state);
    setDraftText(state.description ?? "");
    setDraftReqs(state.requirements ?? []);
    setEditMode(false);
  };

  useEffect(() => {
    Promise.all([getJob(id), getJD(id)])
      .then(([jobData, jdData]) => {
        setJob(jobData);
        applyState(jdData);
      })
      .catch((err) => setError(err.message));
  }, [id]);

  const handleSend = async (text) => {
    setSending(true);
    setPending(text);
    setError("");
    try {
      const state =
        jd.status === "awaiting_review"
          ? await reviewJD(id, { action: "refine", feedback: text })
          : await generateJD(id, text);
      applyState(state);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(null);
      setSending(false);
    }
  };

  const handleApprove = async () => {
    setApproving(true);
    setError("");
    try {
      await reviewJD(id, { action: "approve", description: draftText, requirements: draftReqs });
      navigate(`/jobs/${id}`);
    } catch (err) {
      setError(err.message);
      setApproving(false);
    }
  };

  if (!jd || !job) {
    return error ? (
      <Alert type="error">{error}</Alert>
    ) : (
      <div className="flex justify-center py-12 text-indigo-600">
        <Spinner size="lg" />
      </div>
    );
  }

  const info = STATUS_INFO[jd.status];
  const reviewing = jd.status === "awaiting_review";
  const messages = pending ? [...jd.messages, { role: "user", content: pending }] : jd.messages;

  return (
    <div>
      <Link to={`/jobs/${id}`} className="mb-3 inline-block text-sm text-gray-500 hover:text-gray-700">
        ← Back to {job.title}
      </Link>
      <PageHeader
        title="JD Assistant"
        subtitle={job.title}
        actions={<Badge color={info.badge[0]}>{info.badge[1]}</Badge>}
      />

      <div className="mb-4">
        <Alert type="info">{info.hint}</Alert>
      </div>
      {error && (
        <div className="mb-4">
          <Alert type="error">{error}</Alert>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="flex h-[36rem] flex-col rounded-lg border border-gray-200 bg-white shadow-sm lg:col-span-2">
          <div className="border-b border-gray-200 px-4 py-3">
            <h2 className="text-base font-semibold">Chat</h2>
          </div>
          <div className="min-h-0 flex-1">
            <ChatPanel
              messages={messages}
              onSend={handleSend}
              loading={sending}
              disabled={approving}
              placeholder={info.placeholder}
              emptyText="No messages yet. Describe the role to get started."
            />
          </div>
        </div>

        <div className="flex flex-col gap-6 lg:col-span-3">
          <Card
            title="Job Description"
            actions={
              reviewing && (
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => setEditMode(!editMode)} disabled={sending}>
                    {editMode ? "Preview" : "Edit"}
                  </Button>
                  <Button onClick={handleApprove} loading={approving} disabled={sending}>
                    Approve
                  </Button>
                </div>
              )
            }
          >
            {!jd.description ? (
              <p className="py-10 text-center text-sm text-gray-500">The draft will appear here.</p>
            ) : editMode ? (
              <Textarea
                rows={22}
                value={draftText}
                onChange={(e) => setDraftText(e.target.value)}
                className="font-mono text-xs"
              />
            ) : (
              <div className="max-h-[28rem] overflow-y-auto pr-2">
                <MarkdownView content={draftText} />
              </div>
            )}
          </Card>

          <Card title="Requirements">
            <RequirementsEditor requirements={draftReqs} onChange={setDraftReqs} editable={reviewing} />
          </Card>
        </div>
      </div>
    </div>
  );
}