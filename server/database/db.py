"""PostgreSQL persistence. Each write uses one committed transaction."""

import os
from uuid import UUID

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb

from server.config import ROOT_DIR  # loads the project .env independently of cwd
from server.errors import AppError


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise AppError("The database is not configured. Set DATABASE_URL and run the schema migration.", "DATABASE_NOT_CONFIGURED", 503)
    conn = psycopg.connect(database_url, connect_timeout=10)
    try:
        register_vector(conn)
    except Exception:
        conn.close()
        raise
    return conn


def check_database_connection():
    try:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT 1;")
            return cursor.fetchone() == (1,)
    except Exception:
        return False


def create_session(session_id):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO sessions (id) VALUES (%s) ON CONFLICT (id) DO NOTHING;",
            (session_id,),
        )


def session_exists(session_id):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT EXISTS(SELECT 1 FROM sessions WHERE id = %s);", (session_id,))
        return cursor.fetchone()[0]


def _insert_message(cursor, session_id, role, content, metadata=None):
    cursor.execute(
        """INSERT INTO messages (session_id, role, content, metadata, created_at)
           VALUES (%s, %s, %s, %s, clock_timestamp()) RETURNING id;""",
        (session_id, role, content, Jsonb(metadata or {})),
    )
    return cursor.fetchone()[0]


def save_message(session_id, role, content, metadata=None):
    with get_connection() as conn, conn.cursor() as cursor:
        message_id = _insert_message(cursor, session_id, role, content, metadata)
        cursor.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (session_id,))
        return message_id


def save_exchange(session_id, message, response):
    """Commit user + assistant together; errors never leave a partial exchange."""
    answer = response["answer"]
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("The assistant answer must be a non-empty string.")
    metadata = {key: value for key, value in response.items() if key not in {"answer", "session_id"}}
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("INSERT INTO sessions (id) VALUES (%s) ON CONFLICT (id) DO NOTHING;", (session_id,))
        cursor.execute("SELECT id FROM sessions WHERE id = %s FOR UPDATE;", (session_id,))
        user_id = _insert_message(cursor, session_id, "user", message)
        assistant_id = _insert_message(cursor, session_id, "assistant", answer, metadata)
        cursor.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (session_id,))
        return [user_id, assistant_id]


def get_messages(session_id, limit=None):
    """Return oldest-to-newest history; a limit selects the latest messages."""
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("History limit must be a positive integer.")
    with get_connection() as conn, conn.cursor() as cursor:
        if limit is None:
            cursor.execute(
                """SELECT id, role, content, created_at, metadata FROM messages
                   WHERE session_id = %s ORDER BY created_at ASC, id ASC;""",
                (session_id,),
            )
        else:
            cursor.execute(
                """SELECT id, role, content, created_at, metadata FROM (
                       SELECT id, role, content, created_at, metadata FROM messages
                       WHERE session_id = %s ORDER BY created_at DESC, id DESC LIMIT %s
                   ) AS recent ORDER BY created_at ASC, id ASC;""",
                (session_id, limit),
            )
        rows = cursor.fetchall()
    messages = []
    for message_id, role, content, created_at, metadata in rows:
        metadata = metadata or {}
        item = {
            "id": message_id,
            "role": role,
            "content": content,
            "created_at": created_at.isoformat(),
            "metadata": metadata,
        }
        item.update({key: metadata[key] for key in ("route", "tool", "sources") if key in metadata})
        messages.append(item)
    return messages


def is_valid_uuid(value):
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def find_document_by_hash(content_hash):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT d.id, COUNT(dc.id) FROM documents d
               LEFT JOIN document_chunks dc ON dc.document_id = d.id
               WHERE d.content_hash = %s GROUP BY d.id;""",
            (content_hash,),
        )
        row = cursor.fetchone()
    return {"document_id": row[0], "chunks": row[1], "skipped": True} if row else None


def _lock_document_hash(cursor, content_hash):
    cursor.execute("SELECT pg_advisory_xact_lock(%s);", (int(content_hash[:15], 16),))


def adopt_legacy_document(filename, content_hash, chunks):
    """Attach a hash only when an existing document has exactly the same chunks.

    Legacy rows are retained, including their IDs and embeddings. Matching a
    filename alone is insufficient: content, page numbers, and order must match.
    """
    expected = [(chunk["chunk_index"], chunk["content"], chunk["page_number"]) for chunk in chunks]
    with get_connection() as conn, conn.cursor() as cursor:
        _lock_document_hash(cursor, content_hash)
        cursor.execute(
            """SELECT d.id, COUNT(dc.id) FROM documents d
               LEFT JOIN document_chunks dc ON dc.document_id = d.id
               WHERE d.content_hash = %s GROUP BY d.id;""",
            (content_hash,),
        )
        existing = cursor.fetchone()
        if existing:
            return {"document_id": existing[0], "chunks": existing[1], "skipped": True}
        cursor.execute(
            "SELECT id FROM documents WHERE filename = %s AND content_hash IS NULL ORDER BY id;",
            (filename,),
        )
        candidates = cursor.fetchall()
        for (document_id,) in candidates:
            cursor.execute(
                """SELECT chunk_index, content, page_number FROM document_chunks
                   WHERE document_id = %s ORDER BY chunk_index, id;""",
                (document_id,),
            )
            if cursor.fetchall() != expected:
                continue
            cursor.execute("UPDATE documents SET content_hash = %s WHERE id = %s;", (content_hash, document_id))
            return {"document_id": document_id, "chunks": len(chunks), "skipped": True}
    return None


def save_document_with_chunks(filename, title, content_hash, chunks, embeddings):
    """Insert a complete document atomically; concurrent identical PDFs reuse it."""
    if not chunks or len(chunks) != len(embeddings):
        raise ValueError("Every non-empty document chunk requires an embedding.")
    vectors = []
    for embedding in embeddings:
        vector = np.asarray(embedding, dtype=np.float32)
        if vector.shape != (384,) or not np.isfinite(vector).all():
            raise ValueError("Document embeddings must contain 384 finite values.")
        vectors.append(vector)
    with get_connection() as conn, conn.cursor() as cursor:
        _lock_document_hash(cursor, content_hash)
        cursor.execute(
            """INSERT INTO documents (filename, title, content_hash)
               VALUES (%s, %s, %s) ON CONFLICT (content_hash) DO NOTHING RETURNING id;""",
            (filename, title, content_hash),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                """SELECT d.id, COUNT(dc.id) FROM documents d
                   LEFT JOIN document_chunks dc ON dc.document_id = d.id
                   WHERE d.content_hash = %s GROUP BY d.id;""",
                (content_hash,),
            )
            existing = cursor.fetchone()
            return {"document_id": existing[0], "chunks": existing[1], "skipped": True}
        document_id = row[0]
        cursor.executemany(
            """INSERT INTO document_chunks (document_id, chunk_index, content, page_number, embedding)
               VALUES (%s, %s, %s, %s, %s);""",
            [
                (document_id, chunk["chunk_index"], chunk["content"], chunk["page_number"], vector)
                for chunk, vector in zip(chunks, vectors)
            ],
        )
        return {"document_id": document_id, "chunks": len(chunks), "skipped": False}


def create_document(filename, title=None):
    """Compatibility helper; complete ingestion uses save_document_with_chunks."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("INSERT INTO documents (filename, title) VALUES (%s, %s) RETURNING id;", (filename, title))
        return cursor.fetchone()[0]


def save_document_chunk(document_id, chunk_index, content, page_number, embedding):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO document_chunks (document_id, chunk_index, content, page_number, embedding)
               VALUES (%s, %s, %s, %s, %s) RETURNING id;""",
            (document_id, chunk_index, content, page_number, np.asarray(embedding, dtype=np.float32)),
        )
        return cursor.fetchone()[0]


def save_tool_call(session_id, tool_name, input_data, output_data):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO tool_calls (session_id, tool_name, input_data, output_data)
               VALUES (%s, %s, %s, %s) RETURNING id;""",
            (session_id, tool_name, Jsonb(input_data), Jsonb(output_data)),
        )
        return cursor.fetchone()[0]
