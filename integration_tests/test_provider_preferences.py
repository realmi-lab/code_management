"""Deployment constraints preserve original RAG preferences; no model calls."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from code_agent import provider


def preferences(mode='vector'):
    return SimpleNamespace(
        llm_provider='openai', llm_model='preferred-model',
        hyde_model='preferred-hyde', multi_query_model='preferred-multi',
        contextual_chunking_model='preferred-chunk',
        embedding_provider='openai', embedding_model='text-embedding-3-small',
        search_mode=mode, hyde_enabled=True, multi_query_enabled=True,
        chunking_strategy='semantic',
        guardrails=SimpleNamespace(hallucination_detection=SimpleNamespace(
            judge_model='preferred-judge')),
    )


def configure(monkeypatch, embedding):
    config = {'provider': 'anthropic', 'model': 'synthetic-model',
              'embedding': embedding, 'version': 1}
    monkeypatch.setattr(provider.ai_config, 'read', lambda: config)
    return config


@pytest.mark.parametrize('embedding', ['local', 'openai'])
@pytest.mark.parametrize('mode', ['vector', 'keyword', 'hybrid'])
def test_semantic_capability_preserves_selected_search_mode(monkeypatch, embedding, mode):
    configure(monkeypatch, embedding)
    effective = preferences(mode)
    provider.apply_model_settings(effective)
    assert effective.search_mode == mode
    assert effective.hyde_enabled and effective.multi_query_enabled
    assert effective.chunking_strategy == 'semantic'


def test_keyword_constraints_do_not_change_stored_preferences(monkeypatch):
    config = configure(monkeypatch, 'none')
    stored = preferences()
    keyword = deepcopy(stored)
    provider.apply_model_settings(keyword)
    assert keyword.search_mode == 'keyword'
    assert not keyword.hyde_enabled and not keyword.multi_query_enabled
    assert keyword.chunking_strategy == 'auto'
    assert keyword.guardrails.hallucination_detection.judge_model == 'synthetic-model'
    assert stored.guardrails.hallucination_detection.judge_model == 'preferred-judge'
    config['embedding'] = 'local'
    semantic = deepcopy(stored)
    provider.apply_model_settings(semantic)
    assert semantic.search_mode == 'vector'
    assert semantic.hyde_enabled and semantic.multi_query_enabled
    assert semantic.chunking_strategy == 'semantic'


def test_raw_settings_context_nests_and_resets_after_exception(monkeypatch):
    configure(monkeypatch, 'none')
    raw = preferences()
    with pytest.raises(RuntimeError):
        with provider.raw_model_settings():
            with provider.raw_model_settings():
                provider.apply_model_settings(raw)
            provider.apply_model_settings(raw)
            assert raw == preferences()
            raise RuntimeError('synthetic validation failure')
    effective = deepcopy(raw)
    provider.apply_model_settings(effective)
    assert effective.search_mode == 'keyword'
    assert raw == preferences()


@pytest.mark.asyncio
async def test_raw_settings_context_isolated_between_requests(monkeypatch):
    import asyncio
    configure(monkeypatch, 'none')
    started = asyncio.Event()
    finished = asyncio.Event()

    async def raw_request():
        with provider.raw_model_settings():
            started.set()
            await finished.wait()
            raw = preferences()
            provider.apply_model_settings(raw)
            assert raw.search_mode == 'vector'

    async def effective_request():
        await started.wait()
        effective = preferences()
        provider.apply_model_settings(effective)
        assert effective.search_mode == 'keyword'
        finished.set()

    await asyncio.gather(raw_request(), effective_request())
