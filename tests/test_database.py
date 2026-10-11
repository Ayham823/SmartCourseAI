from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from server.database import db


def connection(cursor=None):
    cursor = cursor or MagicMock()
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


def test_connection_registers_pgvector_and_closes_failed_registration(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test-placeholder")
    conn = MagicMock()
    with patch.object(db.psycopg, "connect", return_value=conn), patch.object(db, "register_vector") as register:
        assert db.get_connection() is conn
        register.assert_called_once_with(conn)
    with patch.object(db.psycopg, "connect", return_value=conn), patch.object(db, "register_vector", side_effect=RuntimeError("vector absent")):
        with pytest.raises(RuntimeError):
            db.get_connection()
        conn.close.assert_called_once()


def test_exchange_commits_both_messages_and_response_metadata():
    conn, cursor = connection()
    cursor.fetchone.side_effect = [(51,), (52,)]
    response = {"answer": "Answer", "route": "RAG", "tool": None, "sources": [{"document": "course.pdf", "page": 2}]}
    with patch.object(db, "get_connection", return_value=conn):
        assert db.save_exchange("session", "Question", response) == [51, 52]
    inserts = [call for call in cursor.execute.call_args_list if "INSERT INTO messages" in call.args[0]]
    assert [call.args[1][1] for call in inserts] == ["user", "assistant"]
    assert inserts[0].args[1][3].obj == {}
    assert inserts[1].args[1][3].obj == {key: value for key, value in response.items() if key != "answer"}
    assert conn.__exit__.call_args.args == (None, None, None)


def test_exchange_assistant_insert_failure_propagates_to_transaction_rollback():
    conn, cursor = connection()

    def execute(sql, values):
        if "INSERT INTO messages" in sql and values[1] == "assistant":
            raise RuntimeError("assistant write failed")

    cursor.execute.side_effect = execute
    cursor.fetchone.return_value = (51,)
    with patch.object(db, "get_connection", return_value=conn):
        with pytest.raises(RuntimeError, match="assistant write failed"):
            db.save_exchange("session", "Question", {"answer": "Answer", "route": "LLM"})
    assert conn.__exit__.call_args.args[0] is RuntimeError
    assert not any("UPDATE sessions" in call.args[0] for call in cursor.execute.call_args_list)


def test_history_limit_selects_latest_then_returns_chronological_with_metadata():
    conn, cursor = connection()
    sources = [{"document": "course.pdf", "page": 7}]
    cursor.fetchall.return_value = [
        (2, "user", "Question", datetime(2026, 1, 1, 12), {}),
        (3, "assistant", "Answer", datetime(2026, 1, 1, 12, 1), {"route": "RAG", "tool": None, "sources": sources}),
    ]
    with patch.object(db, "get_connection", return_value=conn):
        messages = db.get_messages("session", limit=2)
    query, values = cursor.execute.call_args.args
    assert "ORDER BY created_at DESC, id DESC LIMIT %s" in query
    assert "AS recent ORDER BY created_at ASC, id ASC" in query
    assert values == ("session", 2)
    assert [message["id"] for message in messages] == [2, 3]
    assert messages[1]["sources"] == messages[1]["metadata"]["sources"] == sources
    assert messages[1]["route"] == "RAG"


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "2"])
def test_invalid_history_limits_do_not_connect(limit):
    with patch.object(db, "get_connection") as connect:
        with pytest.raises(ValueError):
            db.get_messages("session", limit)
        connect.assert_not_called()


def test_document_inserts_are_atomic_and_float32():
    conn, cursor = connection()
    cursor.fetchone.return_value = (8,)
    chunks = [{"chunk_index": 0, "content": "Course evidence", "page_number": 3}]
    with patch.object(db, "get_connection", return_value=conn):
        result = db.save_document_with_chunks("course.pdf", "Course", "a" * 64, chunks, [np.ones(384)])
    assert result == {"document_id": 8, "chunks": 1, "skipped": False}
    params = cursor.executemany.call_args.args[1]
    assert params[0][:4] == (8, 0, "Course evidence", 3)
    assert params[0][4].dtype == np.float32
    assert conn.__exit__.call_args.args == (None, None, None)


def test_failed_chunk_insert_rolls_back_document():
    conn, cursor = connection()
    cursor.fetchone.return_value = (8,)
    cursor.executemany.side_effect = RuntimeError("chunk write failed")
    with patch.object(db, "get_connection", return_value=conn):
        with pytest.raises(RuntimeError):
            db.save_document_with_chunks("course.pdf", "Course", "a" * 64, [{"chunk_index": 0, "content": "x", "page_number": 1}], [np.ones(384)])
    assert conn.__exit__.call_args.args[0] is RuntimeError


@pytest.mark.parametrize("embedding", [np.ones(1536), np.full(384, np.nan)])
def test_invalid_document_vectors_fail_before_database_writes(embedding):
    with patch.object(db, "get_connection") as connect:
        with pytest.raises(ValueError):
            db.save_document_with_chunks("course.pdf", "Course", "a" * 64, [{"chunk_index": 0, "content": "x", "page_number": 1}], [embedding])
        connect.assert_not_called()


def test_concurrent_duplicate_document_reuses_existing_complete_document():
    conn, cursor = connection()
    cursor.fetchone.side_effect = [None, (8, 11)]
    with patch.object(db, "get_connection", return_value=conn):
        result = db.save_document_with_chunks("course.pdf", "Course", "a" * 64, [{"chunk_index": 0, "content": "x", "page_number": 1}], [np.ones(384)])
    assert result == {"document_id": 8, "chunks": 11, "skipped": True}
    cursor.executemany.assert_not_called()


@pytest.mark.parametrize("matches", [True, False])
def test_legacy_hash_adoption_requires_identical_page_and_content(matches):
    conn, cursor = connection()
    cursor.fetchone.return_value = None
    cursor.fetchall.side_effect = [[(8,)], [(0, "Course evidence", 3 if matches else 4)]]
    with patch.object(db, "get_connection", return_value=conn):
        result = db.adopt_legacy_document("course.pdf", "a" * 64, [{"chunk_index": 0, "content": "Course evidence", "page_number": 3}])
    updates = [call for call in cursor.execute.call_args_list if "UPDATE documents" in call.args[0]]
    assert bool(updates) is matches
    assert result == ({"document_id": 8, "chunks": 1, "skipped": True} if matches else None)
