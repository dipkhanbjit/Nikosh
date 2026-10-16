import { useEffect, useState } from "react";

import { copilotChat, generateSuggestedQuestions, getSuggestedQuestions } from "../../api/copilot";
import { formatDateTime } from "../../api/interviews";
import { copyText } from "../../utils/clipboard";
import ChatPanel from "../ChatPanel";
import { Alert, Badge, Button, Modal, Spinner } from "../ui";

const SUB_TABS = ["Questions", "Chat"];
const MAX_HISTORY = 6;

function QuestionCard({ item }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (await copyText(item.question)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="rounded-md border border-gray-200 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {item.requirement.category && <Badge color="indigo">{item.requirement.category}</Badge>}
          <p className="mt-1 text-xs text-gray-500">{item.requirement.text}</p>
        </div>
        <button type="button" onClick={copy} className="shrink-0 text-xs font-medium text-indigo-600 hover:underline">
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <p className="mt-2 text-sm font-medium text-gray-900">{item.question}</p>
      {item.key_points.length > 0 && (
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-xs font-medium text-gray-600">Key points</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-gray-700">
            {item.key_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </details>
      )}
      {item.cv_probe && (
        <p className="mt-2 text-xs text-gray-600 italic">
          <span className="font-medium not-italic">CV probe:</span> {item.cv_probe}
        </p>
      )}
      {item.sources.length > 0 && <p className="mt-2 text-xs text-gray-400">Sources: {item.sources.join(", ")}</p>}
    </div>
  );
}

function QuestionsSection({ interviewId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    getSuggestedQuestions(interviewId)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [interviewId]);

  const generate = async () => {
    setConfirmOpen(false);
    setGenerating(true);
    setError("");
    try {
      setData(await generateSuggestedQuestions(interviewId));
    } catch (err) {
      setError(err.message);
    } finally {
      setGenerating(false);
    }
  };

  if (!data && !error) return <div className="flex justify-center p-6 text-indigo-600"><Spinner /></div>;

  const questions = data?.questions || [];

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      {error && <div className="mb-3"><Alert type="error">{error}</Alert></div>}

      {questions.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <p className="text-sm text-gray-500">No suggested questions yet. Generate questions based on the job requirements and the candidate's CV.</p>
          <Button onClick={generate} loading={generating}>Generate</Button>
        </div>
      ) : (
        <>
          <div className="mb-3 flex items-center justify-between gap-2">
            <p className="text-xs text-gray-500">{data.generated_at && `Generated ${formatDateTime(data.generated_at)}`}</p>
            <Button variant="secondary" onClick={() => setConfirmOpen(true)} loading={generating}>
              Regenerate
            </Button>
          </div>
          <div className="flex flex-col gap-3">
            {questions.map((q, i) => (
              <QuestionCard key={i} item={q} />
            ))}
          </div>
        </>
      )}

      <Modal
        open={confirmOpen}
        title="Regenerate questions"
        onClose={() => setConfirmOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>Cancel</Button>
            <Button onClick={generate}>Regenerate</Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">This replaces the current suggested questions.</p>
      </Modal>
    </div>
  );
}

function ChatSection({ interviewId }) {
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const send = async (text) => {
    // only successful turns go into the history
    const history = messages
      .filter((m) => !m.failed)
      .slice(-MAX_HISTORY)
      .map(({ role, content }) => ({ role, content }));
    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);
    setError("");
    try {
      const res = await copilotChat(interviewId, text, history);
      setMessages((prev) => [...prev, { role: "assistant", content: res.answer, sources: res.sources }]);
    } catch (err) {
      setMessages((prev) => prev.map((m) => (m === userMsg ? { ...m, failed: true } : m)));
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-0 flex-1">
      <ChatPanel
        messages={messages}
        onSend={send}
        loading={sending}
        error={error}
        placeholder="Ask the co-pilot…"
        emptyText="Ask about the candidate, the job requirements or company policies."
      />
    </div>
  );
}

// Interviewer co-pilot: suggested questions and chat (both stay mounted)
export default function AssistantTab({ interviewId }) {
  const [sub, setSub] = useState("Questions");

  return (
    <>
      <div className="flex shrink-0 gap-1 border-b border-gray-100 p-2">
        {SUB_TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setSub(t)}
            className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium ${
              sub === t ? "bg-indigo-50 text-indigo-700" : "text-gray-500 hover:bg-gray-50 hover:text-gray-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      <div className={`min-h-0 flex-1 flex-col ${sub === "Questions" ? "flex" : "hidden"}`}>
        <QuestionsSection interviewId={interviewId} />
      </div>
      <div className={`min-h-0 flex-1 flex-col ${sub === "Chat" ? "flex" : "hidden"}`}>
        <ChatSection interviewId={interviewId} />
      </div>
    </>
  );
}
