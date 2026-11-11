"""Opt-in checks against local PostgreSQL; live API checks are separately gated.

These checks keep their own new sessions as demonstration history. They never
remove existing records, truncate tables, or reset the Docker volume.
"""
import json
import os
from importlib import import_module
from pathlib import Path
from uuid import uuid4
import pytest
from psycopg.conninfo import conninfo_to_dict
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from server.config import ROOT_DIR
from server.database import db
from server.database.migrate import migrate
from server.rag.ingest import ingest_pdf
from server.rag.retriever import retrieve_chunks
from server.rag.embeddings import embed_text

pytestmark = pytest.mark.integration


@pytest.fixture(scope='module', autouse=True)
def enabled():
    if os.getenv('SMARTCOURSE_INTEGRATION_TESTS') != '1':
        pytest.skip('Set SMARTCOURSE_INTEGRATION_TESTS=1 for local database checks.')
    config = conninfo_to_dict(os.getenv('DATABASE_URL', ''))
    if (os.getenv('SMARTCOURSE_TEST_DISPOSABLE_DB') != '1'
            or config.get('host') not in {'127.0.0.1', 'localhost', '::1'}
            or not config.get('dbname', '').startswith(('smartcourse_test_', 'smartcourse_eval_', 'smartcourse_portfolio_test'))):
        pytest.fail('Integration checks require explicit opt-in and a disposable loopback test database; the submission database must not be used.')
    migrate()
    assert db.check_database_connection()


class DeterministicProvider(RunnableLambda):
    def __init__(self):
        super().__init__(self.respond)

    def bind_tools(self, schemas):
        def select(prompt):
            name = schemas[0]['name']
            if name == 'grade_calculator':
                arguments = {'components': [{'name': 'Exam', 'grade': 82, 'weight': 70}, {'name': 'Project', 'grade': 95, 'weight': 30}]}
            else:
                arguments = {'query': 'Final Project'}
            return AIMessage(content='', tool_calls=[{'id': 'test_' + uuid4().hex, 'name': name, 'args': arguments, 'type': 'tool_call'}])
        return RunnableLambda(select)

    @staticmethod
    def respond(prompt):
        results = [json.loads(message.content) for message in prompt.to_messages() if isinstance(message, ToolMessage)]
        return AIMessage(content=json.dumps(results[-1], ensure_ascii=False) if results else 'Deterministic integration answer; external Anthropic is mocked.')


@pytest.fixture
def client(monkeypatch):
    module = import_module('server.app')
    from server.llm import chain
    monkeypatch.setattr(chain, 'get_llm', lambda: DeterministicProvider())
    return module.create_app({'TESTING': True}).test_client()


def test_database_migration_is_idempotent():
    assert migrate() == []
    with db.get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid='document_chunks'::regclass AND attname='embedding'")
        assert cursor.fetchone()[0] == 'vector(384)'


def test_pdf_ingestion_and_reingestion_keep_document_counts():
    pdf = ROOT_DIR / 'knowledge/course_documents/sample_course_notes.pdf'
    first = ingest_pdf(pdf)
    with db.get_connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM documents')
        documents = cursor.fetchone()[0]
        cursor.execute('SELECT count(*) FROM document_chunks')
        chunks = cursor.fetchone()[0]
    second = ingest_pdf(pdf)
    assert first['document_id'] == second['document_id'] and second['skipped']
    assert first['chunks'] > 0
    with db.get_connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM documents')
        assert cursor.fetchone()[0] == documents
        cursor.execute('SELECT count(*) FROM document_chunks')
        assert cursor.fetchone()[0] == chunks


def test_real_embeddings_and_vector_retrieval():
    embedding = embed_text('How do I authenticate with the Anthropic Python SDK?')
    assert embedding.shape == (384,) and str(embedding.dtype) == 'float32'
    results = retrieve_chunks('How do I authenticate with the Anthropic Python SDK?', limit=5)
    assert results and all('similarity' in row and row['source'] and row['page_number'] for row in results)
    assert max(row['similarity'] for row in results) >= 0.25


def test_chat_persists_real_tool_calls_and_metadata(client):
    grade = client.post('/chat', json={'message': 'My exam grade is 82 with weight 70%. My project grade is 95 with weight 30%. Calculate my final grade.'})
    assert grade.status_code == 200, grade.json
    assert grade.json['route'] == 'TOOL' and grade.json['tool'] == 'grade_calculator'
    assert '85.9' in grade.json['answer']
    assert grade.json['tool_execution']['status'] == 'executed'
    assert grade.json['tool_execution']['calls'][0]['result']['final_grade'] == 85.9
    session_id = grade.json['session_id']
    lookup = client.post('/chat', json={'session_id': session_id, 'message': 'When is the Final Project deadline?'})
    assert lookup.status_code == 200 and lookup.json['tool'] == 'course_information_lookup'
    history = client.get('/history', query_string={'session_id': session_id}).json['messages']
    assert [message['role'] for message in history] == ['user', 'assistant', 'user', 'assistant']
    assert history[1]['tool'] == 'grade_calculator'
    assert history[1]['metadata']['tool_execution'] == grade.json['tool_execution']
    assert history[-1]['metadata']['tool_execution']['status'] == 'executed'
    with db.get_connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT tool_name, input_data, output_data FROM tool_calls WHERE session_id=%s ORDER BY id', (session_id,))
        logs = cursor.fetchall()
    assert [log[0] for log in logs] == ['grade_calculator', 'course_information_lookup']
    assert logs[0][2]['result']['final_grade'] == 85.9
    assert logs[1][2]['result']['status'] == 'unavailable'


def test_rag_chat_sources_survive_history_refresh(client):
    response = client.post('/chat', json={'message': 'How do I authenticate with the Anthropic Python SDK?'})
    assert response.status_code == 200 and response.json['route'] == 'RAG'
    messages = client.get('/history', query_string={'session_id': response.json['session_id']}).json['messages']
    assert messages[-1]['sources'] == response.json['sources'] and messages[-1]['route'] == 'RAG'


def test_unexecuted_tool_status_survives_history_without_a_fake_tool_log(monkeypatch):
    from server.llm import chain

    class TextOnlyProvider(DeterministicProvider):
        def bind_tools(self, schemas):
            return RunnableLambda(lambda prompt: AIMessage(content='Your final grade is 85.9.'))

    monkeypatch.setattr(chain, 'get_llm', lambda: TextOnlyProvider())
    module = import_module('server.app')
    client = module.create_app({'TESTING': True}).test_client()
    response = client.post('/chat', json={'message': 'Calculate my final grade.'})
    assert response.status_code == 200
    assert '85.9' not in response.json['answer']
    execution = response.json['tool_execution']
    assert execution == {'status': 'not_executed', 'calls': []}
    session_id = response.json['session_id']
    messages = client.get('/history', query_string={'session_id': session_id}).json['messages']
    assert messages[-1]['metadata']['tool_execution'] == execution
    with db.get_connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM tool_calls WHERE session_id=%s', (session_id,))
        assert cursor.fetchone()[0] == 0


def test_failed_tool_calls_are_persisted(monkeypatch):
    from server.llm import chain
    class InvalidGradeProvider(DeterministicProvider):
        def bind_tools(self, schemas):
            return RunnableLambda(lambda prompt: AIMessage(content='', tool_calls=[{
                'id': 'invalid_' + uuid4().hex, 'name': 'grade_calculator',
                'args': {'components': [{'name': 'Exam', 'grade': 120, 'weight': 100}]},
                'type': 'tool_call',
            }]))
    monkeypatch.setattr(chain, 'get_llm', lambda: InvalidGradeProvider())
    module = import_module('server.app')
    client = module.create_app({'TESTING': True}).test_client()
    response = client.post('/chat', json={'message': 'Calculate my final grade: exam grade 120 with weight 100%.'})
    assert response.status_code == 200
    assert response.json['tool_execution']['status'] == 'failed'
    with db.get_connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT output_data FROM tool_calls WHERE session_id=%s ORDER BY id', (response.json['session_id'],))
        outputs = [row[0] for row in cursor.fetchall()]
    assert outputs and all(output['status'] == 'error' for output in outputs)
    assert all('between 0 and 100' in output['error'] for output in outputs)


@pytest.mark.live
def test_live_anthropic_all_routes_and_memory():
    if os.getenv('SMARTCOURSE_LIVE_TESTS') != '1':
        pytest.skip('Set SMARTCOURSE_LIVE_TESTS=1 to spend Anthropic API credits.')
    module = import_module('server.app')
    client = module.create_app({'TESTING': True}).test_client()
    cases = [
        ('Hello, what can you help me with?', 'DIRECT_LLM', None),
        ('My exam grade is 82 with weight 70%. My project grade is 95 with weight 30%. Calculate my final grade.', 'TOOL', 'grade_calculator'),
        ('When is the Final Project deadline?', 'TOOL', 'course_information_lookup'),
        ('How do I authenticate with the Anthropic Python SDK?', 'RAG', None),
    ]
    for question, route, tool in cases:
        response = client.post('/chat', json={'message': question})
        assert response.status_code == 200, response.json
        result = response.json
        assert result['route'] == route and result['tool'] == tool and result['answer'].strip()
        if tool == 'grade_calculator':
            assert '85.9' in result['answer']
        if route == 'RAG':
            assert result['sources']
    session_id = result['session_id']
    followup = client.post('/chat', json={'session_id': session_id, 'message': 'How do I keep it secure?'})
    assert followup.status_code == 200 and followup.json['route'] == 'RAG'
    assert len(db.get_messages(session_id)) == 4
