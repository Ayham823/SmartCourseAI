from importlib import import_module
from uuid import uuid4
import pytest
import psycopg
from server.errors import AppError


@pytest.fixture
def api(monkeypatch):
    module = import_module('server.app')
    sessions = {}
    calls = []
    monkeypatch.setattr(module.db, 'check_database_connection', lambda: True)
    monkeypatch.setattr(module.db, 'create_session', lambda session_id: sessions.setdefault(session_id, []))
    monkeypatch.setattr(module.db, 'session_exists', lambda session_id: session_id in sessions)
    monkeypatch.setattr(module.db, 'get_messages', lambda session_id, limit=None: sessions[session_id][-limit:] if limit else sessions[session_id][:])

    def generate(message, session_id, history):
        calls.append((message, session_id, list(history)))
        return dict(session_id=session_id, answer='Generated test response', route='DIRECT_LLM', tool=None, sources=[], routing_reason='General question')

    def save(session_id, message, response):
        sessions[session_id].extend([dict(role='user', content=message), dict(role='assistant', content=response['answer'], route=response['route'], tool=response['tool'], sources=response['sources'])])

    monkeypatch.setattr(module, 'process_message', generate)
    monkeypatch.setattr(module.db, 'save_exchange', save)
    app = module.create_app({'TESTING': True, 'MEMORY_MESSAGES': 4})
    return app.test_client(), module, sessions, calls


def test_health_connected_and_disconnected(api, monkeypatch):
    client, module, _, _ = api
    assert client.get('/health').json['database'] == 'connected'
    monkeypatch.setattr(module.db, 'check_database_connection', lambda: False)
    assert client.get('/health').status_code == 503


@pytest.mark.parametrize('payload', [None, [], 'message', 3, {}, {'message': ''}, {'message': '  '}, {'message': 17}, {'message': True}, {'message': []}, {'message': 'a' * 4001}])
def test_chat_validates_json_and_message(api, payload):
    client, _, sessions, calls = api
    response = client.post('/chat', json=payload)
    assert response.status_code == 400
    assert response.json['error']
    assert not sessions and not calls


def test_malformed_json(api):
    client = api[0]
    assert client.post('/chat', data='{', content_type='application/json').status_code == 400


@pytest.mark.parametrize('session_id', ['', 23, [], 'not-a-uuid'])
def test_invalid_session(api, session_id):
    assert api[0].post('/chat', json={'message': 'Hi', 'session_id': session_id}).status_code == 400


def test_missing_existing_session_is_not_created(api):
    client, _, sessions, _ = api
    response = client.post('/chat', json={'message': 'Hi', 'session_id': str(uuid4())})
    assert response.status_code == 404
    assert not sessions


def test_new_session_reuse_history_metadata_and_memory(api):
    client, _, sessions, calls = api
    first = client.post('/chat', json={'message': 'Explain RAG'})
    assert first.status_code == 200
    session_id = first.json['session_id']
    second = client.post('/chat', json={'message': 'What is its advantage?', 'session_id': session_id})
    assert second.status_code == 200 and second.json['session_id'] == session_id
    assert len(sessions) == 1 and len(calls[-1][2]) == 2
    history = client.get('/history', query_string={'session_id': session_id}).json['messages']
    assert [row['role'] for row in history] == ['user', 'assistant', 'user', 'assistant']
    assert history[1]['route'] == 'DIRECT_LLM'
    assert all(field in first.json for field in ['session_id', 'answer', 'route', 'tool', 'sources'])


def test_session_preflight_reserves_history_before_generation(api):
    client, module, sessions, calls = api
    reserved = client.post('/sessions', json={})
    assert reserved.status_code == 201 and not calls
    session_id = reserved.json['session_id']
    assert session_id in sessions
    assert client.get('/history', query_string={'session_id': session_id}).json['messages'] == []
    response = client.post('/chat', json={'message': 'Hello', 'session_id': session_id})
    assert response.status_code == 200 and response.json['session_id'] == session_id


def test_history_filters_session(api):
    client, _, _, _ = api
    one = client.post('/chat', json={'message': 'One'}).json['session_id']
    two = client.post('/chat', json={'message': 'Two'}).json['session_id']
    assert client.get('/history', query_string={'session_id': one}).json['messages'][0]['content'] == 'One'
    assert client.get('/history', query_string={'session_id': two}).json['messages'][0]['content'] == 'Two'
    assert client.get('/history').status_code == 400
    assert client.get('/history', query_string={'session_id': str(uuid4())}).status_code == 404


def test_memory_bounded_to_recent_messages(api):
    client, _, _, calls = api
    session_id = client.post('/chat', json={'message': 'first'}).json['session_id']
    for number in range(4):
        client.post('/chat', json={'message': f'message {number}', 'session_id': session_id})
    assert len(calls[-1][2]) == 4
    assert calls[-1][2][0]['content'] == 'message 1'


def test_llm_error_does_not_save_fake_answer(api, monkeypatch):
    client, module, sessions, _ = api
    def fail(*args):
        raise AppError('AI service is unavailable.', 'llm_unavailable', 503)
    monkeypatch.setattr(module, 'process_message', fail)
    response = client.post('/chat', json={'message': 'Hello'})
    assert response.status_code == 503
    assert sessions[response.json['session_id']] == []


def test_database_error_is_sanitized(api, monkeypatch):
    client, module, _, _ = api
    def fail(*args, **kwargs):
        raise psycopg.OperationalError('secret-database-password')
    monkeypatch.setattr(module.db, 'create_session', fail)
    response = client.post('/chat', json={'message': 'Hello'})
    assert response.status_code == 503
    assert 'secret' not in str(response.json)


def test_unexpected_error_is_sanitized(api, monkeypatch):
    client, module, _, _ = api
    def fail(*args):
        raise RuntimeError('secret-api-key')
    monkeypatch.setattr(module, 'process_message', fail)
    response = client.post('/chat', json={'message': 'Hello'})
    assert response.status_code == 500 and 'secret' not in str(response.json)


def test_rag_search_and_answer(api, monkeypatch):
    client, module, _, _ = api
    results = [{'chunk_id': 1, 'content': 'Source text', 'page_number': 3, 'similarity': 0.7, 'source': 'lecture.pdf'}]
    monkeypatch.setattr(module, 'retrieve_chunks', lambda query, limit=5: results)
    response = client.post('/rag/search', json={'query': 'API'})
    assert response.status_code == 200 and response.json['results'] == results
    monkeypatch.setattr(module, 'answer_question', lambda query: {'answer': 'Grounded test answer', 'sources': [{'document': 'lecture.pdf', 'page': 3, 'similarity': 0.7}]})
    assert client.post('/rag/answer', json={'query': 'API'}).json['sources'][0]['page'] == 3
    assert client.post('/rag/search', json={'query': 42}).status_code == 400


def test_frontend_is_served(api):
    response = api[0].get('/')
    assert response.status_code == 200 and b'SmartCourse' in response.data
    assert api[0].get('/static/app.js').status_code == 200


def test_unknown_route_returns_json_error(api):
    response = api[0].get('/unknown')
    assert response.status_code == 404 and response.is_json


def test_request_body_size_is_bounded(api):
    response = api[0].post('/chat', data='x' * 40000, content_type='application/json')
    assert response.status_code == 413 and response.is_json
