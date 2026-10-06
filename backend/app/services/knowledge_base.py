import hashlib
from functools import lru_cache
from pathlib import Path

from fastembed import TextEmbedding
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.models.knowledge import KBChunk, KBDocument
from app.services.document_parser import extract_text

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


@lru_cache
def get_embedder() -> TextEmbedding:
    return TextEmbedding(
        model_name=settings.embedding_model, cache_dir=settings.embedding_cache_dir
    )


def chunk_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.kb_chunk_size, chunk_overlap=settings.kb_chunk_overlap
    )
    return [c for c in splitter.split_text(text) if c.strip()]


def ingest_document(
    db: Session, filename: str, data: bytes, uploaded_by: int | None = None
) -> KBDocument:
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise AppException("Unsupported file type", 400, "UNSUPPORTED_FILE_TYPE")
    if len(data) > settings.kb_max_file_mb * 1024 * 1024:
        raise AppException("File too large", 400, "FILE_TOO_LARGE")

    content_hash = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(KBDocument).where(KBDocument.content_hash == content_hash))
    if existing:
        return existing

    text = extract_text(filename, data)
    if not text.strip():
        raise AppException("No extractable text in document", 422, "NO_TEXT_EXTRACTED")

    chunks = chunk_text(text)
    vectors = get_embedder().embed(chunks)

    doc = KBDocument(
        filename=filename,
        content_hash=content_hash,
        chunk_count=len(chunks),
        uploaded_by=uploaded_by,
    )
    doc.chunks = [
        KBChunk(chunk_index=i, content=c, embedding=v.tolist())
        for i, (c, v) in enumerate(zip(chunks, vectors))
    ]
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def search(db: Session, query: str, k: int = 5) -> list[dict]:
    query_vec = next(iter(get_embedder().query_embed(query))).tolist()
    distance = KBChunk.embedding.cosine_distance(query_vec)
    rows = db.execute(
        select(KBChunk, KBDocument.filename, distance.label("distance"))
        .join(KBDocument)
        .order_by(distance)
        .limit(k)
    ).all()
    return [
        {
            "content": chunk.content,
            "source": filename,
            "chunk_index": chunk.chunk_index,
            "score": round(1 - dist, 4),
        }
        for chunk, filename, dist in rows
    ]