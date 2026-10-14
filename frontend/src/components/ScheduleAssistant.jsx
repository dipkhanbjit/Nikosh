import { useEffect, useRef, useState } from "react";

import { formatDateTime } from "../api/interviews";
import { cancelAssistant, confirmAssistant, getAssistant, sendAssistantMessage } from "../api/scheduleAssistant";
import { Badge, Button, Spinner } from "./ui";

const SOURCE_LABEL = { chat: "chat", form: "form", cv: "CV", test: "test" };
const RESULT_BADGE = {
  sent: { color: "green", label: "Sent" },
  failed: { color: "red", label: "Failed" },
  skipped: { color: "yellow", label: "Skipped" },
};

// Assistant state from the API → chat message (null when nothing is open)
const fromState = (state) => (state.status === "none" ? null : { role: "assistant", state });

function PlanTable({ items }) {
  return (
    <table className="mt-2 w-full text-left text-xs">
      <thead className="text-gray-500">
        <tr>
          <th className="py-1 pr-2 font-medium">Candidate</th>
          <th className="py-1 pr-2 font-medium">Date and time</th>
          <th className="py-1 font-medium">Email</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {items.map((item) => (
          <tr key={item.candidate_id} className="align-top">
            <td className="py-1.5 pr-2 font-medium text-gray-800">{item.name || `#${item.candidate_id}`}</td>
            <td className="py-1.5 pr-2 text-gray-700">
              {formatDateTime(item.start)}
              <span className="block text-gray-500">{item.duration_min} min</span>
            </td>
            <td className="py-1.5 text-gray-700">
              <span className="block break-all">{item.email}</span>
              <Badge color={item.email_source === "test" ? "purple" : "gray"}>
                {SOURCE_LABEL[item.email_source] ?? item.email_source}
              </Badge>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ResultTable({ results }) {
  return (
    <table className="mt-2 w-full text-left text-xs">
      <thead className="text-gray-500">
        <tr>
          <th className="py-1 pr-2 font-medium">Candidate</th>
          <th className="py-1 pr-2 font-medium">Date and time</th>
          <th className="py-1 font-medium">Status</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {results.map((r) => (
          <tr key={r.candidate_id} className="align-top">
            <td className="py-1.5 pr-2 font-medium text-gray-800">{r.name || `#${r.candidate_id}`}</td>
            <td className="py-1.5 pr-2 text-gray-700">{formatDateTime(r.start)}</td>
            <td className="py-1.5 text-gray-700">
              <Badge color={RESULT_BADGE[r.status].color}>{RESULT_BADGE[r.status].label}</Badge>
              {r.reason && <span className="mt-0.5 block text-gray-500">{r.reason}</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const resultSummary = (results) =>
  ["sent", "failed", "skipped"]
    .map((status) => [results.filter((r) => r.status === status).length, status])
    .filter(([count]) => count > 0)
    .map(([count, status]) => `${count} ${status}`)
    .join(", ") || "Nothing was scheduled.";

function AssistantBubble({ state, actions }) {
  return (
    <div className="max-w-[90%] self-start rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm">
      {state.message && <p className="whitespace-pre-wrap">{state.message}</p>}
      {state.status === "plan" && state.items.length > 0 && <PlanTable items={state.items} />}
      {state.status === "done" && (
        <>
          <p>{resultSummary(state.results)}</p>
          {state.results.length > 0 && <ResultTable results={state.results} />}
        </>
      )}
      {state.skipped.length > 0 && (
        <div className="mt-2 text-xs text-gray-600">
          <p className="font-medium">Skipped:</p>
          <ul className="list-disc pl-4">
            {state.skipped.map((s) => (
              <li key={s.candidate_id}>
                {s.name || `#${s.candidate_id}`}: {s.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {actions}
    </div>
  );
}

// Chat for one job; render with key={jobId} so each job starts with a fresh history
function AssistantChat({ jobId, open, hasShortlist, onScheduled }) {
  const [messages, setMessages] = useState([]); // { role: "user" | "assistant" | "error" | "info", text?, state? }
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(""); // text shown while waiting, "" when idle
  const [restoring, setRestoring] = useState(true);
  const [noShortlist, setNoShortlist] = useState(false);
  const fetched = useRef(false);
  const listEnd = useRef(null);

  // Restore an open plan or question on the first open for this job (not on every reopen)
  useEffect(() => {
    if (!open || !jobId || !hasShortlist || fetched.current) return;
    fetched.current = true;
    getAssistant(jobId)
      .then((state) => {
        const message = fromState(state);
        if (message) setMessages((prev) => [message, ...prev]);
      })
      .catch((err) => setMessages((prev) => [...prev, { role: "error", text: err.message }]))
      .finally(() => setRestoring(false));
  }, [open, jobId, hasShortlist]);

  useEffect(() => {
    listEnd.current?.scrollIntoView({ block: "end" });
  }, [messages, busy, open]);

  const blocked = !jobId || !hasShortlist || noShortlist;
  const loading = !blocked && restoring;
  const disabled = blocked || loading || Boolean(busy);
  const lastPlanIndex = messages.findLastIndex((m) => m.state?.status === "plan");
  const planOpen = lastPlanIndex !== -1 && !messages.slice(lastPlanIndex + 1).some((m) => m.state || m.cancelled);

  const add = (message) => setMessages((prev) => [...prev, message]);

  const send = async () => {
    const text = input.trim();
    if (!text || disabled) return;
    add({ role: "user", text });
    setInput("");
    setBusy("Planning…");
    try {
      const message = fromState(await sendAssistantMessage(jobId, text));
      add(message ?? { role: "info", text: "Nothing to schedule." });
    } catch (err) {
      if (err.code === "NO_SHORTLIST") setNoShortlist(true);
      add({ role: "error", text: err.message });
    } finally {
      setBusy("");
    }
  };

  const cancel = async () => {
    setBusy("Cancelling…");
    try {
      await cancelAssistant(jobId);
      add({ role: "info", text: "Plan cancelled.", cancelled: true });
    } catch (err) {
      add({ role: "error", text: err.message });
    } finally {
      setBusy("");
    }
  };

  const confirm = async () => {
    setBusy("Scheduling and sending invitations…");
    try {
      add({ role: "assistant", state: await confirmAssistant(jobId) });
    } catch (err) {
      add({ role: "error", text: err.message, cancelled: err.code === "NO_OPEN_PLAN" });
    } finally {
      setBusy("");
    }
    onScheduled?.();
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const planActions = (
    <div className="mt-3 flex justify-end gap-2">
      <Button variant="secondary" className="px-3 py-1 text-xs" onClick={cancel} disabled={Boolean(busy)}>
        Cancel
      </Button>
      <Button className="px-3 py-1 text-xs" onClick={confirm} disabled={Boolean(busy)}>
        Confirm and send
      </Button>
    </div>
  );

  return (
    <>
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto bg-gray-50 p-4">
        {!jobId && <p className="text-center text-sm text-gray-500">Select a job to use the assistant.</p>}
        {jobId && (!hasShortlist || noShortlist) && (
          <p className="text-center text-sm text-gray-500">Approve a shortlist for this job before scheduling.</p>
        )}
        {loading && (
          <div className="flex justify-center text-gray-400">
            <Spinner size="sm" />
          </div>
        )}
        {!blocked && !loading && messages.length === 0 && (
          <p className="text-center text-sm text-gray-500">
            Tell me whom to schedule and when. I will propose a plan for you to review.
          </p>
        )}
        {messages.map((m, i) => {
          if (m.role === "user") {
            return (
              <div
                key={i}
                className="max-w-[85%] self-end whitespace-pre-wrap rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white"
              >
                {m.text}
              </div>
            );
          }
          if (m.role === "error") {
            return (
              <div
                key={i}
                className="max-w-[85%] self-start rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
              >
                {m.text}
              </div>
            );
          }
          if (m.role === "info") {
            return (
              <p key={i} className="self-center text-xs text-gray-500">
                {m.text}
              </p>
            );
          }
          return (
            <AssistantBubble
              key={i}
              state={m.state}
              actions={planOpen && i === lastPlanIndex && m.state.items.length > 0 ? planActions : null}
            />
          );
        })}
        {busy && (
          <div className="flex items-center gap-2 self-start text-sm text-gray-500">
            <Spinner size="sm" /> {busy}
          </div>
        )}
        <div ref={listEnd} />
      </div>

      <div className="border-t border-gray-200 bg-white p-3">
        <textarea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          maxLength={1000}
          placeholder="Schedule the top 3 tomorrow from 10 AM, 30 min each"
          className="w-full resize-none rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-100"
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-xs text-gray-400">Enter to send, Shift+Enter for a new line</span>
          <Button className="px-3 py-1 text-xs" onClick={send} disabled={disabled || !input.trim()}>
            Send
          </Button>
        </div>
      </div>
    </>
  );
}

// Floating scheduling assistant on the Candidates page (below Modal, which uses z-50)
export default function ScheduleAssistant({ jobId, jobTitle, hasShortlist, onScheduled }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div
        className={`fixed bottom-24 right-6 z-40 flex h-[520px] max-h-[calc(100vh-8rem)] w-[400px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl ${open ? "" : "hidden"}`}
      >
        <div className="flex items-start justify-between border-b border-gray-200 px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-gray-900">Scheduling assistant</h2>
            <p className="truncate text-xs text-gray-500">{jobTitle || "No job selected"}</p>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="cursor-pointer rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        </div>
        <AssistantChat key={jobId} jobId={jobId} open={open} hasShortlist={hasShortlist} onScheduled={onScheduled} />
      </div>

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Scheduling assistant"
        title="Scheduling assistant"
        className="fixed bottom-6 right-6 z-40 flex h-14 w-14 cursor-pointer items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg hover:bg-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
      >
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M8 10h8M8 14h5m-9 6 2.6-2.6A2 2 0 0 1 8 17h10a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v14Z"
          />
        </svg>
      </button>
    </>
  );
}
