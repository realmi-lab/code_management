"""Real pinned-source patch + request contract checks; provider HTTP is mocked here."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import httpx
import pytest
from code_agent import provider

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def commandcode(monkeypatch):
    monkeypatch.setenv('CODE_LLM_PROVIDER', 'commandcode')
    monkeypatch.setenv('COMMANDCODE_API_KEY', 'synthetic-commandcode-test-key')
    monkeypatch.setenv('CODE_LLM_MODEL', provider.COMMANDCODE_MODEL)
    monkeypatch.setenv('CODE_LLM_REASONING_EFFORT', 'high')


def test_missing_commandcode_key_never_falls_back(commandcode, monkeypatch):
    monkeypatch.delenv('COMMANDCODE_API_KEY')
    with pytest.raises(ValueError, match='COMMANDCODE_API_KEY'):
        provider.client_options('openai-key-must-not-be-used')


def test_original_provider_preserved(monkeypatch):
    monkeypatch.setenv('CODE_LLM_PROVIDER', 'openai')
    assert provider.client_options('synthetic-original-key') == {'api_key': 'synthetic-original-key'}
    assert provider.model_name('original-model') == 'original-model'
    assert provider.reasoning_options() == {}
    assert provider.evaluation_options() == {'model': 'gpt-4o', 'temperature': 0}


def test_judge_and_public_settings(commandcode):
    assert provider.evaluation_options()['reasoning_effort'] == 'high'
    assert provider.evaluation_options()['base_url'] == provider.COMMANDCODE_URL
    assert 'synthetic-commandcode-test-key' not in json.dumps(provider.public_settings())


@pytest.fixture
def patched_source(tmp_path):
    source = ROOT / 'upstream/backend'
    if not source.exists():
        pytest.skip('Run manage.py prepare for pinned-source integration checks')
    manage = load('source_verifier', ROOT / 'scripts/manage.py')
    manage.verify_source(ROOT / 'upstream', manage.lock_spec())
    target = tmp_path / 'backend'
    shutil.copytree(source, target)
    patch = load('provider_patch', ROOT / 'deploy/patch_provider.py')
    patch.apply(target)
    return target


def test_effective_settings_and_embeddings_unchanged(patched_source, commandcode):
    config = load('provider_config', patched_source / 'app/config.py')
    settings = config.RAGSettings(llm_provider='openai', llm_model='stale-model')
    assert settings.llm_provider == 'commandcode'
    assert settings.llm_model == provider.COMMANDCODE_MODEL
    assert settings.hyde_model == provider.COMMANDCODE_MODEL
    assert settings.embedding_model == 'text-embedding-3-small'
    path = 'app/services/embedding/openai.py'
    # Opt-in factory added, original OpenAI client/retry path remains present.
    assert 'self.client = AsyncOpenAI(api_key=api_key)' in (patched_source / path).read_text()


@pytest.mark.asyncio
async def test_actual_upstream_llm_sends_commandcode_high(patched_source, commandcode, monkeypatch):
    from test_upstream_adapter import module
    exceptions = load('provider_exceptions', patched_source / 'app/exceptions.py')
    module(monkeypatch, 'app.exceptions', CircuitBreakerOpenError=exceptions.CircuitBreakerOpenError,
           SearchServiceError=exceptions.SearchServiceError)
    resilience = load('provider_resilience', patched_source / 'app/services/resilience.py')
    module(monkeypatch, 'app.services.resilience', CircuitBreaker=resilience.CircuitBreaker)
    upstream = load('provider_generation', patched_source / 'app/services/generation/openai.py')
    from openai import AsyncOpenAI
    observed = []

    def response(request):
        observed.append(request)
        return httpx.Response(200, json={'id': 'test', 'object': 'chat.completion', 'created': 0,
            'model': provider.COMMANDCODE_MODEL,
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '검증 완료'}, 'finish_reason': 'stop'}]})

    monkeypatch.setattr(upstream, 'AsyncOpenAI', lambda **kw: AsyncOpenAI(
        **kw, http_client=httpx.AsyncClient(transport=httpx.MockTransport(response))))
    llm = upstream.OpenAILLM(api_key='unused-openai-key', model='old-model')
    try:
        assert await llm.generate('합성 확인', system_prompt='원문 보존') == '검증 완료'
    finally:
        await llm.client.close()
    request = observed[0]
    assert str(request.url) == provider.COMMANDCODE_URL + '/chat/completions'
    assert request.headers['authorization'] == 'Bearer synthetic-commandcode-test-key'
    payload = json.loads(request.content)
    assert payload['model'] == provider.COMMANDCODE_MODEL
    assert payload['reasoning_effort'] == 'high'
    assert payload['messages'][0] == {'role': 'system', 'content': '원문 보존'}


def test_changed_source_rejected(patched_source):
    patch = load('provider_patch_second', ROOT / 'deploy/patch_provider.py')
    with pytest.raises(RuntimeError, match='contract changed'):
        patch.apply(patched_source)
