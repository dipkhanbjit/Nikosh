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
- Everything must stay free (no paid services).

## Stack
- Backend: FastAPI, SQLAlchemy 2 + psycopg, Alembic, PostgreSQL 16 + pgvector,
  LangGraph (PostgresSaver checkpointer), Gemini via langchain-google-genai
  (`get_llm()` in `app/services/llm.py`), fastembed (bge-small-en-v1.5, 384-dim).
- Frontend: React + Vite + Tailwind + React Router, **plain JavaScript**
  (no TypeScript, no TanStack Query). Common UI in `src/components/ui`
  (Button, Input, Textarea, Card, Badge, Alert, Spinner, Modal, PageHeader, Table).
  `apiRequest` JSON-stringifies the body itself — pass plain objects.
  Errors carry `err.status` and `err.code`. Clipboard: `utils/clipboard.js`
  (`copyText`, with HTTP fallback).
- MCP server `nikosh-tools` (called via `app/services/mcp_client.call_tool`):
  publish_to_blogger, publish_to_telegram, create_job_form, set_form_open,
  list_job_applications, download_cv, trash_drive_file, send_email,
  create_calendar_event, delete_calendar_event.
- Google: one OAuth token (`backend/secrets/google-oauth-token.json`) for
  Blogger, Forms, Drive, Gmail (gmail.send) and Calendar (calendar.events).
  Re-authorize with `.venv/Scripts/python.exe -m app.scripts.google_auth`
  (from `backend/`). The app is in Testing mode, so the token expires about
  every 7 days.
- Auth: JWT in HttpOnly cookie, roles `interviewer` / `candidate`,
  `require_role()` in `app/api/deps.py`. Login supports a safe `?next=` path.
- API prefix `/api/v1`, Swagger at `localhost:8000/docs`.

## Code conventions
- Errors: raise `AppException(message, status_code, "ERROR_CODE")`.
- Log success and failure (`logging.getLogger(__name__)`); logs go to
  `backend/logs/nikosh.log`. Never log passwords or full tokens.
- LangGraph workflows live in `app/workflows/`, one thread per job
  (e.g. `jd-job-{id}`, `shortlist-job-{id}`); human review = real `interrupt()`,
  resumed with `Command(resume=...)` from the API.
- Background work uses its own `SessionLocal()`.
- Alembic: autogenerate, then check the migration only contains intended
  changes (never LangGraph checkpoint tables). New columns nullable or with a
  server default.
- Times are shown in Asia/Dhaka (GMT+6); API datetimes carry a timezone offset.
- UI style: formal and clean, not over-complicated.

## Running & testing
- Whole system: `docker compose up -d --build` → frontend `localhost:3000`,
  backend `localhost:8000`. Rebuild after code changes.
- Backend logs: `docker compose logs backend --tail 30`.
- The backend runs Uvicorn with a **single worker** (no `--workers`): the
  interview room registry (`app/services/rooms.py`) is in memory. Do not add
  workers without moving it to a shared store.
- The "volume nikosh_pgdata already exists" warning is harmless.
- Same-PC testing: interviewer in a normal browser window, candidate in an
  incognito window or another browser (Edge). For video: Chrome + Edge,
  each with its own microphone.
- Test emails: always use `dipkhan870+<name>@gmail.com` as the candidate
  contact email (never the synthetic CV addresses).
- Camera/mic only work on `localhost` or HTTPS. Two-PC tests need a
  Cloudflare Tunnel (or the Chrome insecure-origin flag) and
  `FRONTEND_BASE_URL` in `.env`.

## Git & Redmine
- One branch per WBS feature, e.g. `feature/6.3-video-session`;
  merge into main with `--no-ff` when the feature is done; keep branches.
- Commit format (BJIT):
  `git commit -m "<type>(<scope>): <summary>" -m "<body>" -m "<footer>"`
  - summary: imperative, ≤ 50 chars
  - body: hyphen bullets, wrapped at 72 chars, blank line between bullets
  - footer: `Refs #<id>` (task continues), `Closes #<id>` (last commit of
    the task), `Fixes #<id>` (bug)
- Redmine: Story (module) > Story (feature) > Task. WBS tasks may be merged
  or reworded; Redmine follows the changed structure.
- Redmine notes: 5–8 short, simple bullet sentences.

## Status (13 Oct 2026)
- Modules 1–5 done and merged into main (JD agent + RAG, posting to
  Blogger/Telegram, per-job Google Forms + Drive CV collection, CV parsing
  with OCR, semantic gate Met/Partial/Unmet, weighted scoring, ranking).
- **Feature 6.1 done and merged** (Candidate Selection & Interview Scheduling):
  - `candidates.shortlisted`, `shortlisted_at`; `interviews` table
    (`app/models/interview.py`, statuses scheduled / in_progress / completed /
    cancelled / no_show).
  - Shortlisting workflow `app/workflows/shortlisting.py`:
    propose (top N from `ranked_candidates()`, no LLM) → review interrupt
    (approve, or revise with new `top_n` / `remove_ids`) → save.
  - Shortlist API `app/api/shortlist.py`: `GET/POST /jobs/{id}/shortlist`,
    `POST /jobs/{id}/shortlist/review`.
  - Interview API `app/api/interviews.py` + `app/services/interviews.py`:
    `POST/GET /jobs/{id}/interviews`, `GET /interviews`, `GET/PATCH /interviews/{id}`,
    `POST /interviews/{id}/cancel`, `POST /interviews/{id}/no-show`;
    `change_status()` enforces transitions. Background check marks overdue
    scheduled interviews as no_show every 5 minutes; manual no-show only
    after the start time.
  - Screens: Candidates page (job selector, Top N + Apply, approve / send
    back, shortlisted table with Schedule), Interviews page (status filter,
    cancel, no-show).
- **Feature 6.2 done and merged** (Interview Invitation & Candidate Access):
  - `interviews.join_token`; `join_url` = `FRONTEND_BASE_URL/interview/join/<token>`.
  - Candidate account created on schedule (`ensure_candidate_account`,
    `candidates.user_id`), one-time password returned once as `credentials`;
    staff emails blocked (`EMAIL_IN_USE`). Each schedule / resend resets the
    password.
  - `GET /join/{token}` (candidate role, owner only): window from 10 min
    before start until the end; in_progress always ready; 404 INVALID_LINK,
    403 NOT_YOUR_INTERVIEW, 410 LINK_EXPIRED.
  - `GET /me/interviews` (candidate home "My interviews").
  - Invitation (`app/services/invitations.py`): calendar event + Gmail
    invitation on schedule; cancel deletes the event and emails;
    `POST /interviews/{id}/resend-invitation` (new password); fields
    calendar_event_id, calendar_url, invitation_status, invitation_error,
    invitation_sent_at. Editable contact email in the schedule modal.
    Reschedule does not update invitations.
  - 6.2.2 fix: one formal invitation email. Google Calendar
    `sendUpdates="none"`; `.ics` REQUEST/CANCEL attachment with a stable UID
    and `invitation_sequence`; `GOOGLE_ACCOUNT_EMAIL` setting; no password
    in the calendar.
- **Feature 6.3 done and merged** (Video Session):
  - 6.3.1 Rooms: device check; interviewer room `/interviews/:id/room`,
    candidate room `/interview/join/:token/room`; start/end endpoints;
    `room_open` window helper.
  - 6.3.2 WebSocket signaling: `/ws/interviews/{id}`, `/ws/join/{token}`;
    in-memory room registry (single Uvicorn worker); close codes;
    interview-started/ended events (incl. cancelled / no_show).
  - 6.3.3 WebRTC peer-to-peer video/audio (`usePeerConnection`, Google STUN
    via `VITE_ICE_SERVERS`), media-state, screen sharing.
  - 6.3.4 End-to-end tests (single PC, and two PCs via Cloudflare quick
    tunnel); README demo setup; `FRONTEND_BASE_URL`.
  - Room layout: left = AI Assistant placeholder + Candidate tab (key
    highlights, Open CV); centre = video, controls, transcript placeholder;
    right = in-call chat (saved history, links, file sharing up to 10 MB:
    txt/pdf/doc/xls/ppt). Chat files are deleted with the candidate/job.

## Module 6 plan — During-Interview: AI-Powered Video Interview (F3)
- 6.1 Candidate Selection & Interview Scheduling — **done**
- 6.2 Interview Invitation & Candidate Access — **done**
- 6.3 Video Session — **done**
- 6.4 Audio Capture — **next** (branch `feature/6.4-audio-capture`):
  6.4.1 per-participant mic audio tagged by role, 6.4.2 backend receives
  audio per speaker over WebSocket (STT connected in Module 7)
- 6.5 Connection Recovery: 6.5.1 auto-reconnect, 6.5.2 preserve session data
- Goal: finish Module 6 on 13 Oct.

## Later (noted, not now)
- Module 8 hiring decision: Selected / Not selected with an optional short
  message, emailed to the candidate and shown in "My interviews".
- Candidates never see scores, transcripts or analysis.
- 7.3.2 live transcript panel (interviewer only), chat style: interviewer
  bubbles right (blue), candidate bubbles left (white); speaker name +
  timestamp on each; interim text grey italic until final; auto-scroll
  unless the user scrolled up.
- F8 AI Assistant: plug the existing ChatPanel into the left "AI Assistant"
  tab; RAG over company docs + candidate CV + job requirements (+ recent
  transcript later); Gemini only on demand.
- Module 10 cleanup: fix the existing eslint `react-hooks/set-state-in-effect`
  errors (RecordingsModal, JobFormModal, Candidates, InterviewJoin).
- Two-PC testing: the tunnel URL changes every start; set
  `FRONTEND_BASE_URL` and run `docker compose up -d backend` (not
  `restart`); switch back to localhost afterwards.

## Trainer schedule ahead
- 14 Oct F5 interview scheduling, agentic email/calendar tool, unique link (done)
- **15 Oct Milestone 2**: score → selection → scheduling → link → candidate
  join → interview UI
- 16 Oct video + live transcription (speaker attribution, timestamps)
- 19 Oct Milestone 3 / F8 interviewer co-pilot; 20–23 Oct analysis & reports
- 26 Oct integration; 27 Oct final demo
- Note: trainer schedule mentions Google Meet; plan uses in-app WebRTC
  (needed for per-participant live transcription) — to confirm with trainer.
