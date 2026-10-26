"""Evaluate the real PDF -> MiniLM -> PostgreSQL/pgvector retrieval path.

Use only a newly provisioned local database named smartcourse_eval_*. There are
no Anthropic calls, generated answers, replacement embeddings or mocked search.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import time

from psycopg.conninfo import conninfo_to_dict
from evaluation.metrics import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.k <= 100:
        parser.error("k must be between 1 and 100")
    # Disable dotenv and model downloads before importing application modules.
    os.environ["SMARTCOURSE_ENV_FILE"] = os.devnull
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    config = conninfo_to_dict(os.getenv("DATABASE_URL", ""))
    if os.getenv("SMARTCOURSE_EVAL_DISPOSABLE_DB") != "1" or config.get("host") not in {"127.0.0.1", "localhost", "::1"} or not config.get("dbname", "").startswith("smartcourse_eval_"):
        parser.error("Use an explicitly opted-in disposable loopback smartcourse_eval_* database")

    from server.database.db import get_connection
    from server.database.migrate import migrate
    from server.rag.embeddings import MODEL_NAME, get_embedding_model
    from server.rag.ingest import ingest_pdf
    from server.rag.retriever import retrieve_chunks
    from server.rag.service import _retrieval_query

    root = Path(__file__).resolve().parents[1]
    dataset_path = root / "evaluation/retrieval_cases.json"
    dataset = json.loads(dataset_path.read_text())
    pdf = root / "knowledge/course_documents" / dataset["source"]
    # No deletion, reset, or re-embedding of an existing corpus is permitted.
    # The extension is created before get_connection registers vector types.
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
            if cursor.fetchone()[0]:
                raise RuntimeError("Evaluation requires a newly created empty database")
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    migrate()
    ingested = ingest_pdf(pdf)
    cases = []
    for case in dataset["cases"]:
        query = _retrieval_query(case["question"], case.get("history"))
        started = time.perf_counter()
        results = retrieve_chunks(query, limit=args.k)
        cases.append({
            "id": case["id"], "category": case["category"], "question": case["question"],
            "history": case.get("history", []), "retrieval_query": query,
            "expected_pages": case["pages"], "retrieval_ms": round((time.perf_counter()-started)*1000, 2),
            "results": [{"document": r["source"], "page": r["page_number"], "similarity": r["similarity"]} for r in results],
        })
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM document_chunks")
        count = cursor.fetchone()[0]
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        commit = "unavailable"
    report = {
        "schema_version": 1, "mode": "real-offline-retrieval-no-generative-provider",
        "source_commit": commit,
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "embedding_model": MODEL_NAME,
        "embedding_revision": getattr(get_embedding_model()[0].auto_model.config, "_commit_hash", None),
        "source_file_sha256": {path: hashlib.sha256((root/path).read_bytes()).hexdigest() for path in [
            "server/rag/retriever.py", "server/rag/service.py", "server/rag/embeddings.py",
            "server/rag/ingest.py", "server/rag/chunker.py", "server/rag/loader.py", "evaluation/retrieval.py"
        ]},
        "dimensions": 384, "chunk_count": count,
        "k": args.k, "minimum_similarity": 0.25, "ingestion_chunks": ingested["chunks"],
        "versions": {name: importlib.metadata.version(name) for name in ["sentence-transformers", "numpy", "psycopg", "pgvector", "pypdf"]},
        "metrics": summarize(cases, args.k, 0.25),
        "metrics_by_cutoff": {str(k): summarize(cases, k, 0.25) for k in sorted({1, min(3,args.k),args.k})},
        "threshold_diagnostics": [{"threshold": t, **summarize(cases, args.k, t)} for t in [0.25, 0.35, 0.45, 0.55, 0.65]],
        "limitations": [
            "Small manually labeled synthetic English corpus; not a held-out production benchmark.",
            "Measures retrieval and the similarity gate only, not generated-answer correctness or prompt-injection resistance.",
            "Threshold diagnostics are exploratory and do not tune or change application settings.",
            "An unanswerable question can match a related paragraph without the requested fact being present.",
        ],
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"output": str(args.output), "metrics": report["metrics"], "chunks": count}, indent=2))


if __name__ == "__main__":
    main()
