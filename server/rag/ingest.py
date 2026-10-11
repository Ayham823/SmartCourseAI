"""Idempotent PDF ingestion: python -m server.rag.ingest <pdf_path>."""

import argparse
import hashlib
from pathlib import Path

from server.database.db import adopt_legacy_document, find_document_by_hash, save_document_with_chunks
from server.rag.chunker import chunk_pages
from server.rag.embeddings import embed_texts
from server.rag.loader import load_pdf


def ingest_pdf(file_path):
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files can be ingested.")
    content = path.read_bytes()
    content_hash = hashlib.sha256(content).hexdigest()
    existing = find_document_by_hash(content_hash)
    if existing:
        return existing

    pages = load_pdf(path, content=content)
    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError("No text was extracted from the PDF; scanned PDFs require OCR first.")
    legacy = adopt_legacy_document(path.name, content_hash, chunks)
    if legacy:
        return legacy
    # Extract and embed everything before opening the write transaction. A
    # failed extraction, model call, or chunk insert leaves no partial document.
    embeddings = embed_texts([chunk["content"] for chunk in chunks])
    return save_document_with_chunks(path.name, path.stem, content_hash, chunks, embeddings)


def main():
    parser = argparse.ArgumentParser(description="Index a PDF once, preserving its source pages.")
    parser.add_argument("pdf_path")
    args = parser.parse_args()
    try:
        result = ingest_pdf(args.pdf_path)
    except Exception as error:
        # Avoid printing exception text that may contain a database DSN.
        print(f"Ingestion failed ({type(error).__name__}); no partial document was saved.")
        return 1
    action = "Already indexed" if result["skipped"] else "Indexed"
    print(f"{action}: document {result['document_id']} ({result['chunks']} chunks).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
