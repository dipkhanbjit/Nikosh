import argparse
from pathlib import Path

from app.core.database import SessionLocal
from app.services.knowledge_base import ALLOWED_EXTENSIONS, DOCUMENT_KINDS, ingest_document


def main(folder: str, kind: str) -> None:
    paths = sorted(
        p for p in Path(folder).iterdir() if p.suffix.lower() in ALLOWED_EXTENSIONS
    )
    with SessionLocal() as db:
        for path in paths:
            doc = ingest_document(db, path.name, path.read_bytes(), kind=kind)
            print(f"{path.name}: {doc.chunk_count} chunks (id={doc.id}, kind={doc.kind})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest a folder into the knowledge base")
    parser.add_argument("folder")
    parser.add_argument("--kind", choices=sorted(DOCUMENT_KINDS), default="company")
    args = parser.parse_args()
    main(args.folder, args.kind)
