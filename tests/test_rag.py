import hashlib
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from server.errors import AppError
from server.rag import embeddings, ingest, loader, retriever, service
from server.rag.chunker import chunk_pages, chunk_text


def test_embeddings_load_once_on_demand_and_preserve_float32(monkeypatch):
    transformer = MagicMock()
    transformer.return_value.encode.return_value = np.ones(384)
    fake_module = MagicMock(SentenceTransformer=transformer)
    monkeypatch.setattr(embeddings, "_model", None)
    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", fake_module)
    first = embeddings.embed_text("Evidence")
    second = embeddings.embed_text("More evidence")
    assert transformer.call_count == 1
    assert first.shape == second.shape == (384,)
    assert first.dtype == second.dtype == np.float32


def test_source_page_numbers_survive_blank_pages_and_chunking(tmp_path):
    path = tmp_path / "course.pdf"
    path.write_bytes(b"placeholder")
    pages = [MagicMock(), MagicMock(), MagicMock()]
    for page, text in zip(pages, ["First page", "", "Third page with longer evidence"]):
        page.extract_text.return_value = text
    with patch.object(loader, "PdfReader", return_value=MagicMock(pages=pages)):
        extracted = loader.load_pdf(path)
    chunks = chunk_pages(extracted, chunk_size=20, overlap=5)
    assert [page["page_number"] for page in extracted] == [1, 3]
    assert {chunk["page_number"] for chunk in chunks} == {1, 3}
    assert [chunk["chunk_index"] for chunk in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize("size,overlap", [(0, 0), (10, 10), (10, 11), (10, -1)])
def test_invalid_chunk_parameters_raise_instead_of_looping(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("course evidence", size, overlap)


def test_repeated_pdf_ingestion_uses_hash_without_reembedding(tmp_path):
    path = tmp_path / "course.pdf"
    path.write_bytes(b"same PDF bytes")
    existing = {"document_id": 8, "chunks": 11, "skipped": True}
    with patch.object(ingest, "find_document_by_hash", return_value=existing) as find, patch.object(ingest, "load_pdf") as load, patch.object(ingest, "embed_texts") as embed, patch.object(ingest, "save_document_with_chunks") as save:
        assert ingest.ingest_pdf(path) == existing
        find.assert_called_once_with(hashlib.sha256(path.read_bytes()).hexdigest())
        load.assert_not_called()
        embed.assert_not_called()
        save.assert_not_called()


def test_new_ingestion_preserves_hash_and_sources_and_embeds_before_write(tmp_path):
    path = tmp_path / "course.pdf"
    path.write_bytes(b"PDF bytes")
    events = []
    pages = [{"page_number": 9, "text": "Course evidence"}]
    vectors = [np.ones(384, dtype=np.float32)]

    def embed(texts):
        events.append("embed")
        assert texts == ["Course evidence"]
        return vectors

    def save(filename, title, content_hash, chunks, embeddings_value):
        events.append("save")
        assert filename == "course.pdf" and title == "course"
        assert content_hash == hashlib.sha256(b"PDF bytes").hexdigest()
        assert chunks[0]["page_number"] == 9
        assert embeddings_value is vectors
        return {"document_id": 8, "chunks": 1, "skipped": False}

    with patch.object(ingest, "find_document_by_hash", return_value=None), patch.object(ingest, "adopt_legacy_document", return_value=None), patch.object(ingest, "load_pdf", return_value=pages), patch.object(ingest, "embed_texts", side_effect=embed), patch.object(ingest, "save_document_with_chunks", side_effect=save):
        assert ingest.ingest_pdf(path)["skipped"] is False
    assert events == ["embed", "save"]


def test_embedding_failure_never_opens_document_write(tmp_path):
    path = tmp_path / "course.pdf"
    path.write_bytes(b"PDF bytes")
    with patch.object(ingest, "find_document_by_hash", return_value=None), patch.object(ingest, "adopt_legacy_document", return_value=None), patch.object(ingest, "load_pdf", return_value=[{"page_number": 1, "text": "Course evidence"}]), patch.object(ingest, "embed_texts", side_effect=RuntimeError("model failed")), patch.object(ingest, "save_document_with_chunks") as save:
        with pytest.raises(RuntimeError):
            ingest.ingest_pdf(path)
        save.assert_not_called()


def test_verified_legacy_pdf_is_reused_without_new_embeddings(tmp_path):
    path = tmp_path / "course.pdf"
    path.write_bytes(b"PDF bytes")
    existing = {"document_id": 8, "chunks": 1, "skipped": True}
    with patch.object(ingest, "find_document_by_hash", return_value=None), patch.object(ingest, "load_pdf", return_value=[{"page_number": 1, "text": "Course evidence"}]), patch.object(ingest, "adopt_legacy_document", return_value=existing), patch.object(ingest, "embed_texts") as embed:
        assert ingest.ingest_pdf(path) == existing
        embed.assert_not_called()


@pytest.mark.parametrize("results", [[], [{"similarity": 0.1}]])
def test_no_relevant_evidence_is_actionable_422_without_llm_call(results):
    with patch.object(service, "retrieve_chunks", return_value=results), patch.object(service, "generate_rag_answer") as generate:
        with pytest.raises(AppError) as error:
            service.answer_question("Unsupported course question")
        assert error.value.status == 422
        generate.assert_not_called()


def test_rag_answer_deduplicates_sources_and_passes_conversation_history():
    results = [
        {"content": "First evidence", "source": "course.pdf", "page_number": 2, "similarity": 0.8},
        {"content": "More evidence", "source": "course.pdf", "page_number": 2, "similarity": 0.7},
        {"content": "Next page", "source": "course.pdf", "page_number": 3, "similarity": 0.6},
    ]
    history = [{"role": "user", "content": "Tell me about operating systems"}]
    with patch.object(service, "retrieve_chunks", return_value=results) as retrieve, patch.object(service, "generate_rag_answer", return_value="Grounded answer") as generate:
        result = service.answer_question("Explain that", history=history)
    assert result["answer"] == "Grounded answer"
    assert [source["page"] for source in result["sources"]] == [2, 3]
    assert generate.call_args.kwargs["history"] is history
    assert "Source: course.pdf\nPage: 2" in generate.call_args.kwargs["context"]
    assert retrieve.call_args.args[0] == "Tell me about operating systems\nFollow-up: Explain that"
    assert generate.call_args.kwargs["question"] == "Explain that"


def test_independent_question_does_not_mix_previous_retrieval_topic():
    history = [{"role": "user", "content": "Explain operating systems"}]
    assert service._retrieval_query("Define database normalization", history) == "Define database normalization"


def test_contextual_retrieval_query_is_bounded():
    history = [{"role": "user", "content": "x" * 5000}]
    query = service._retrieval_query("How do I keep it secure?", history)
    assert len(query) < 1250


def test_empty_search_index_returns_422():
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    with patch.object(retriever, "embed_text", return_value=np.ones(384)), patch.object(retriever, "get_connection", return_value=conn):
        with pytest.raises(AppError) as error:
            retriever.retrieve_chunks("Course question")
    assert error.value.status == 422
