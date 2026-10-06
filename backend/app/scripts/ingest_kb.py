import sys
from pathlib import Path

from app.core.database import SessionLocal
from app.services.knowledge_base import ALLOWED_EXTENSIONS, ingest_document


def main(folder: str) -> None:
    paths = sorted(
        p for p in Path(folder).iterdir() if p.suffix.lower() in ALLOWED_EXTENSIONS
    )
    with SessionLocal() as db:
        for path in paths:
            doc = ingest_document(db, path.name, path.read_bytes())
            print(f"{path.name}: {doc.chunk_count} chunks (id={doc.id})")


if __name__ == "__main__":
    main(sys.argv[1])