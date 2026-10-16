"""Attach a realistic synthetic transcript (Python backend interview) to an existing interview,
for testing Q&A pairing and analysis, and for the demo. Marks the interview completed.

Usage (from backend/, or inside the backend container):
    python -m app.scripts.seed_transcript --interview-id <id> [--replace]
"""

import argparse
from datetime import timedelta

from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.models import Interview, InterviewTranscriptTurn

WORDS_PER_SECOND = 2.5
PAUSE_S = 1.2

# (speaker, text[, incomplete]) in spoken order; times are derived from the text length
SCRIPT = [
    ("interviewer", "Hello, good afternoon. Can you hear me clearly?"),
    ("candidate", "Yes, I can hear you well. Good afternoon."),
    ("interviewer", "Great. Thanks for joining. This will take about thirty minutes, "
                    "and I'll mostly ask technical questions. Shall we start?"),
    ("candidate", "Sure, I'm ready."),
    # 1 main
    ("interviewer", "Could you briefly tell me about your current role and the projects you work on?"),
    ("candidate", "I'm a backend developer at a fintech startup for about three years. I mainly build REST "
                  "services in Python with FastAPI and PostgreSQL, and recently I led the migration of our "
                  "payment reconciliation service from Flask to FastAPI."),
    # 2 main, multi-part
    ("interviewer", "When you design a new REST API, how do you structure the endpoints, how do you handle "
                    "versioning, and how do you return errors to the client?"),
    ("candidate", "For structure, I model resources as nouns, like orders and orders slash id slash items, "
                  "and use HTTP methods for the actions. For versioning we put the major version in the path, "
                  "slash api slash v1, and only bump it for breaking changes. For errors we return a consistent "
                  "JSON body with an error code and a message, and the right status code, for example 404 "
                  "or 422 for validation errors."),
    # 3 main, answer split by a short reaction
    ("interviewer", "How does dependency injection work in FastAPI, and why is it useful?"),
    ("candidate", "In FastAPI you declare dependencies with Depends in the endpoint signature. FastAPI calls "
                  "those functions for each request and passes the result in, for example a database session "
                  "or the current user."),
    ("interviewer", "Mm-hm."),
    ("candidate", "It's useful because the endpoint code stays small, and the same logic like authentication "
                  "is reused everywhere. And dependencies can use yield, so the session is closed after "
                  "the request."),
    # 4 follow-up of 3
    ("interviewer", "You said it helps with reuse. How do you use it when writing tests?"),
    ("candidate", "We use app dependency_overrides. In tests we replace the database session dependency with "
                  "one bound to a test database, and replace the current user dependency with a fake user, "
                  "so we don't need real tokens."),
    # 5 main, with a clarification
    ("interviewer", "Let's talk about databases. When would you add an index?"),
    ("candidate", "Do you mean in PostgreSQL specifically, or in general?"),
    ("interviewer", "PostgreSQL. When would you add an index, and when would you avoid one?"),
    ("candidate", "I add an index on columns used often in WHERE clauses, joins or ORDER BY, like foreign keys "
                  "or an email lookup. I check with EXPLAIN ANALYZE first. I avoid indexes on small tables, "
                  "on columns with very few distinct values, and on tables with heavy writes, because every "
                  "index slows down inserts and updates."),
    # 6 main
    ("interviewer", "What is the difference between async and sync endpoints in FastAPI?"),
    ("candidate", "An async endpoint runs on the event loop, so it's good for I/O like calling other APIs with "
                  "an async client. A normal def endpoint runs in a thread pool. If you call blocking code "
                  "inside an async endpoint, you block the whole event loop, which is a common mistake."),
    ("interviewer", "Okay, good."),
    # 7 main, not answered
    ("interviewer", "How would you implement distributed tracing across several microservices?"),
    ("interviewer", "Actually, let's skip that one for now, we're a bit short on time."),
    # 8 main
    ("interviewer", "Tell me about a difficult production bug you solved."),
    ("candidate", "Once our reconciliation job started creating duplicate records at night. The logs showed "
                  "two workers picking the same batch. The cause was a missing lock, so I used SELECT FOR "
                  "UPDATE SKIP LOCKED to claim rows, and added a unique constraint as a safety net. After "
                  "that we had no duplicates."),
    # 9 follow-up of 8
    ("interviewer", "Why did you add the unique constraint if the lock already fixed it?"),
    ("candidate", "Because the lock fixes the race in code, but the constraint protects the data even if "
                  "someone adds another job later or the code changes. The database is the last line "
                  "of defence."),
    # 10 main
    ("interviewer", "How do you make sure your code is tested before it goes to production?"),
    ("candidate", "We write unit tests with pytest for the business logic and API tests with the test client. "
                  "Every pull request runs the tests and linting in GitHub Actions, and we need one review "
                  "before merging. We also aim for coverage on the critical payment paths, but we",
     True),
    # 11 main
    ("interviewer", "Last question. Why are you interested in this position?"),
    ("candidate", "I enjoy building reliable backend systems, and your team works on products at a larger "
                  "scale. I also want to learn more about AI features, which I saw in the job description."),
    # closing
    ("interviewer", "Thank you. Do you have any questions for me?"),
    ("candidate", "Yes, how big is the backend team, and what does the first month look like?"),
    ("interviewer", "The team has six developers, and in the first month you'll pair with a mentor on a small "
                    "feature. We'll get back to you within a week. Thanks for your time."),
    ("candidate", "Thank you, have a nice day."),
]


def _turns(interview_id: int) -> list[InterviewTranscriptTurn]:
    turns, clock = [], 2.0
    for seq, (speaker, text, *flag) in enumerate(SCRIPT, start=1):
        duration = round(max(len(text.split()) / WORDS_PER_SECOND, 1.0), 1)
        turns.append(
            InterviewTranscriptTurn(
                interview_id=interview_id,
                seq=seq,
                speaker=speaker,
                text=text,
                start_s=round(clock, 1),
                end_s=round(clock + duration, 1),
                confidence=0.93,
                incomplete=bool(flag and flag[0]),
            )
        )
        clock += duration + PAUSE_S
    return turns


def main(interview_id: int, replace: bool) -> None:
    with SessionLocal() as db:
        interview = db.get(Interview, interview_id)
        if interview is None:
            raise SystemExit(f"Interview {interview_id} not found")
        existing = db.scalar(
            select(func.count()).where(InterviewTranscriptTurn.interview_id == interview_id)
        )
        if existing and not replace:
            raise SystemExit(f"Interview {interview_id} already has {existing} turns; use --replace")
        if existing:
            db.execute(delete(InterviewTranscriptTurn).where(InterviewTranscriptTurn.interview_id == interview_id))

        turns = _turns(interview_id)
        db.add_all(turns)
        if interview.started_at is None:
            interview.started_at = interview.scheduled_at
        if interview.ended_at is None:
            interview.ended_at = interview.started_at + timedelta(seconds=turns[-1].end_s + 5)
        previous = interview.status
        interview.status = "completed"
        db.commit()
    print(f"Interview {interview_id}: {len(turns)} turns saved ({existing} replaced), "
          f"status {previous} -> completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed a synthetic transcript for an interview")
    parser.add_argument("--interview-id", type=int, required=True)
    parser.add_argument("--replace", action="store_true", help="delete the interview's existing turns first")
    args = parser.parse_args()
    main(args.interview_id, args.replace)
