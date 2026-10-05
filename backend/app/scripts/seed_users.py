from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User

DEMO_USERS = [
    ("interviewer@nikosh.local", "Demo Interviewer", "interviewer", "Interviewer@123"),
    ("candidate@nikosh.local", "Demo Candidate", "candidate", "Candidate@123"),
]


def main() -> None:
    with SessionLocal() as db:
        for email, full_name, role, password in DEMO_USERS:
            if db.scalar(select(User).where(User.email == email)):
                print(f"Exists: {email}")
                continue
            db.add(
                User(
                    email=email,
                    full_name=full_name,
                    role=role,
                    hashed_password=hash_password(password),
                )
            )
            print(f"Created: {email}")
        db.commit()


if __name__ == "__main__":
    main()
