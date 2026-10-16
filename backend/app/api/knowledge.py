from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models import KBDocument, User
from app.schemas.knowledge import KBDocumentOut
from app.services.knowledge_base import ingest_document

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
interviewer_only = require_role("interviewer")


@router.post("/documents", response_model=KBDocumentOut, status_code=201)
def upload_document(
    file: UploadFile,
    kind: str = Form("company"),
    db: Session = Depends(get_db),
    user: User = Depends(interviewer_only),
):
    return ingest_document(db, file.filename, file.file.read(), user.id, kind)


@router.get(
    "/documents",
    response_model=list[KBDocumentOut],
    dependencies=[Depends(interviewer_only)],
)
def list_documents(db: Session = Depends(get_db)):
    return db.scalars(select(KBDocument).order_by(KBDocument.created_at.desc())).all()


@router.delete(
    "/documents/{doc_id}", status_code=204, dependencies=[Depends(interviewer_only)]
)
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(KBDocument, doc_id)
    if not doc:
        raise AppException("Document not found", 404, "DOCUMENT_NOT_FOUND")
    db.delete(doc)
    db.commit()