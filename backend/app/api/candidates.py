from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import Candidate
from app.services.storage import delete_file

router = APIRouter(
    prefix="/candidates",
    tags=["candidates"],
    dependencies=[Depends(require_role("interviewer"))],
)


@router.delete("/{candidate_id}", status_code=204)
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise AppException("Candidate not found", 404, "CANDIDATE_NOT_FOUND")
    cv_path = candidate.cv_file_path
    db.delete(candidate)
    db.commit()
    delete_file(cv_path)