# Nikosh — Project Guide for Claude

AI-Powered Recruitment & Interview Intelligence Platform. BJIT Academy final
evaluation project (solo, trainee 30222). Final demo: **27 Oct 2026**.

## How to work with me
- Work **one step at a time**. Do one step, then stop and wait for my
  confirmation before the next. No long multi-step changes in one go.
- Keep it **simple**. No over-engineering, no extra features I did not ask for.
- Be concise. Do not over-explain.
- If something is unclear or conflicts with the plan below, ask first.
- I run git commands myself. Do not commit or push; give me the commit command.
- Gemini free tier is rate-limited: avoid new LLM calls unless they are needed.
  Deterministic logic (scores, validation, ranking) stays in code, not in the LLM.

## Stack
- Backend: FastAPI, SQLAlchemy 2 + psycopg, Alembic, PostgreSQL 16 + pgvector,
  LangGraph (PostgresSaver checkpointer), Gemini via langchain-google-genai
  (`get_llm()` in `app/services/llm.py`), fastembed (bge-small-en-v1.5, 384-dim).
- Frontend: React + Vite + Tailwind + React Router, **plain JavaScript**
  (no TypeScript, no TanStack Query). Common UI in `src/components/ui`
  (Button, Input, Textarea, Card, Badge, Alert, Spinner, Modal, PageHeader, Table).
  `apiRequest` JSON-stringifies the body itself — pass plain objects.
- MCP server `nikosh-tools` (called via `app/services/mcp_client.call_tool`):
  publish_to_blogger, publish_to_telegram, create_job_form, set_form_open,
  list_job_applications, download_cv, trash_drive_file.
- Auth: JWT in HttpOnly cookie, roles `interviewer` / `candidate`,
  `require_role()` in `app/api/deps.py`.
- API prefix `/api/v1`, Swagger at `localhost:8000/docs`.

## Code conventions
- Errors: raise `AppException(message, status_code, "ERROR_CODE")`.
- Log success and failure (`logging.getLogger(__name__)`); logs go to
  `backend/logs/nikosh.log`.
- LangGraph workflows live in `app/workflows/`, one thread per job
  (e.g. `jd-job-{id}`, `shortlist-job-{id}`); human review = real `interrupt()`,
  resumed with `Command(resume=...)` from the API.
- Background work uses its own `SessionLocal()`.
- Alembic: autogenerate, then check the migration only contains intended
  changes (never LangGraph checkpoint tables).
- UI style: formal and clean, not over-complicated.

## Running
- Whole system: `docker compose up -d --build` → frontend `localhost:3000`,
  backend `localhost:8000`. Rebuild after code changes.
- Backend logs: `docker compose logs backend --tail 30`.
- The "volume nikosh_pgdata already exists" warning is harmless.

## Git & Redmine
- One branch per WBS feature, e.g. `feature/6.1-interview-scheduling`;
  merge into main with `--no-ff` when the feature is done; keep branches.
- Commit format (BJIT):
  `git commit -m "<type>(<scope>): <summary>" -m "<body>" -m "<footer>"`
  - summary: imperative, ≤ 50 chars
  - body: hyphen bullets, wrapped at 72 chars
  - footer: `Refs #<id>` (task continues), `Closes #<id>` (last commit of
    the task), `Fixes #<id>` (bug)
- Redmine: Story (module) > Story (feature) > Task. WBS tasks may be merged
  or reworded; Redmine follows the changed structure.
- Redmine notes: 5–8 short, simple bullet sentences.

## Status (12 Oct 2026)
- Modules 1–5 done and merged into main (JD agent + RAG, posting to
  Blogger/Telegram, per-job Google Forms + Drive CV collection, CV parsing
  with OCR, semantic gate Met/Partial/Unmet, weighted scoring, ranking).
- Current branch: `feature/6.1-interview-scheduling`.
- **6.1.1 done** (commit `729e0aa`, Closes #648471):
  - `candidates.shortlisted`, `shortlisted_at`; new `interviews` table
    (`app/models/interview.py`, statuses scheduled / in_progress / completed /
    cancelled / no_show).
  - Shortlisting workflow `app/workflows/shortlisting.py`:
    propose (top N from `ranked_candidates()`, no LLM) → review interrupt
    (approve, or revise with new `top_n` / `remove_ids`) → save.
  - Shortlist API `app/api/shortlist.py`: `GET /jobs/{id}/shortlist`,
    `POST /jobs/{id}/shortlist` `{top_n}`, `POST /jobs/{id}/shortlist/review`.
  - Interview API `app/api/interviews.py` + `app/services/interviews.py`:
    `POST/GET /jobs/{id}/interviews`, `GET /interviews`, `GET/PATCH /interviews/{id}`,
    `POST /interviews/{id}/cancel`, `POST /interviews/{id}/no-show`;
    `change_status()` enforces transitions.

## Module 6 plan — During-Interview: AI-Powered Video Interview (F3)
Order of work:
- 6.1 Candidate Selection & Interview Scheduling
  - 6.1.1 Shortlisting + scheduling with status tracking — **done**
  - 6.1.2 Shortlist, scheduling and session list screens — **next**
- 6.2 Interview Invitation & Candidate Access
  - 6.2.1 Unique interview link (secure token, no candidate login, valid only
    for its session and time window)
  - 6.2.2 Invitation email + Google Calendar event as MCP tools
    (`send_interview_email`, `create_calendar_event`), triggered automatically
    on schedule; reschedule updates, cancel removes; status/error stored;
    `POST /interviews/{id}/resend-invitation` to retry
- 6.3 Video Session
  - 6.3.1 Initial interview room (interviewer console + candidate room,
    camera/mic preview, mute / camera / end controls)
  - 6.3.2 Real-time connection handling (WebSocket signaling per session)
  - 6.3.3 Live video and audio (WebRTC peer-to-peer)
  - 6.3.4 End-to-end testing (same-PC, two-mic demo setup)
- 6.4 Audio Capture: 6.4.1 per-participant mic audio, 6.4.2 forward to STT
- 6.5 Connection Recovery: 6.5.1 auto-reconnect, 6.5.2 preserve session data

### 6.1.2 Candidates page design (agreed)
1. Job selector (dropdown of jobs).
2. Top N number field (default 5) + **Apply** button → starts the shortlist.
3. Proposed shortlist table: Rank, Candidate, Email, Score, Requirements
   (met/partial), Profile. Buttons: **Approve shortlist**, **Send back**
   (change N or remove candidates).
4. After approval: shortlisted table with interview status + **Schedule**
   button per row (schedule form: date, time, duration, notes).
5. Interviews page: session list with status badges (and cancel / no-show).

## Trainer schedule ahead
- 13 Oct score persistence & justification (done in Module 5)
- 14 Oct F5 interview scheduling, agentic email/calendar tool, unique link
- **15 Oct Milestone 2**: score → selection → scheduling → link → candidate
  join → interview UI
- 16 Oct video + live transcription (speaker attribution, timestamps)
- 19 Oct Milestone 3 / F8 interviewer co-pilot; 20–23 Oct analysis & reports
- 26 Oct integration; 27 Oct final demo
- Note: trainer schedule mentions Google Meet; plan uses in-app WebRTC
  (needed for per-participant live transcription) — to confirm with trainer.
