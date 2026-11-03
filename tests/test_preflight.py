import json
import pytest

from server import preflight
from server.errors import AppError
from server.llm import chain


VALID = {
    'DATABASE_URL': 'postgresql://student:private-password@localhost:55432/study_test',
    'ANTHROPIC_API_KEY': 'private-key-sentinel',
    'ANTHROPIC_MODEL': 'configured-model',
}


def test_report_never_prints_values_and_does_not_claim_live_verification():
    report = preflight.configuration_report(VALID)
    assert report['ready'] and report['scope'] == 'configuration_only'
    assert not report['provider_verified'] and not report['database_verified']
    assert all(value not in json.dumps(report) for value in VALID.values())


@pytest.mark.parametrize('name', list(VALID))
def test_missing_required_configuration_is_named_without_its_value(name):
    values = {key: value for key, value in VALID.items() if key != name}
    report = preflight.configuration_report(values)
    assert not report['ready']
    assert {'setting': name, 'status': 'missing'} in report['checks']


@pytest.mark.parametrize('value', ['replace_with_active_key', '<your-key>', 'changeme'])
def test_placeholder_key_is_rejected_locally_and_by_model_factory(monkeypatch, value):
    report = preflight.configuration_report({**VALID, 'ANTHROPIC_API_KEY': value})
    assert not report['ready']
    monkeypatch.setenv('ANTHROPIC_API_KEY', value)
    monkeypatch.setenv('ANTHROPIC_MODEL', 'configured-model')
    with pytest.raises(AppError) as error:
        chain.get_llm()
    assert error.value.code == 'llm_not_configured'


@pytest.mark.parametrize('url', [
    'https://student:private-password@localhost/db',
    'postgresql://localhost:bad/db',
    'postgresql://localhost/',
    'postgresql://[invalid-host/db',
    'postgresql://student:replace_with_local_database_password@localhost/db',
])
def test_invalid_database_config_is_safe(url):
    report = preflight.configuration_report({**VALID, 'DATABASE_URL': url})
    assert not report['ready'] and url not in json.dumps(report)


@pytest.mark.parametrize('name,value', [
    ('LLM_TIMEOUT_SECONDS', 'nan'), ('LLM_MAX_RETRIES', 'two'),
    ('RAG_MIN_SIMILARITY', 'inf'), ('RAG_MIN_SIMILARITY', '2'),
    ('MEMORY_MESSAGES', '31'), ('PORT', '0'),
])
def test_bad_numeric_configuration_is_reported(name, value):
    report = preflight.configuration_report({**VALID, name: value})
    assert {'setting': name, 'status': 'invalid'} in report['checks']


def test_cli_uses_exit_code_and_only_safe_output(monkeypatch, capsys):
    preflight_report = {'ready': False, 'checks': [{'setting': 'ANTHROPIC_MODEL', 'status': 'missing'}]}
    monkeypatch.setattr(preflight, 'configuration_report', lambda: preflight_report)
    assert preflight.main(['--json']) == 1
    assert json.loads(capsys.readouterr().out) == preflight_report
