"""Actual pinned SettingsService/config with in-memory DB and Redis IO doubles."""
import ast
from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, JSON, String
from sqlalchemy.orm import declarative_base

from code_agent import provider
from test_provider import patched_source, load
from test_upstream_adapter import module


class Cache:
    def __init__(self, value=None):
        self.value = value
        self.invalidations = []

    async def get(self, key):
        return deepcopy(self.value)

    async def set(self, key, value, ttl):
        self.value = deepcopy(value)

    async def invalidate_settings(self):
        self.value = None
        self.invalidations.append('settings')

    async def invalidate_search(self):
        self.invalidations.append('search')


class Database:
    def __init__(self, row):
        self.row = row
        self.commits = 0
        self.reads = 0

    async def execute(self, statement):
        self.reads += 1
        return SimpleNamespace(scalar_one_or_none=lambda: self.row)

    def add(self, row):
        self.row = row

    async def commit(self):
        self.commits += 1


@pytest.fixture
def setup_service(patched_source, monkeypatch):
    selected = {'provider': 'anthropic', 'model': 'synthetic-model', 'version': 1, 'embedding': 'none'}
    monkeypatch.setattr(provider.ai_config, 'read', lambda: selected)
    config = load('pinned_preference_config', patched_source/'app/config.py')
    module(monkeypatch, 'app.config', RAGSettings=config.RAGSettings)
    Base = declarative_base()

    class Setting(Base):
        __tablename__ = 'synthetic_settings'
        id = Column(Integer, primary_key=True)
        key = Column(String)
        value = Column(JSON)

    module(monkeypatch, 'app.models.database', Setting=Setting)
    module(monkeypatch, 'app.services.cache', PREFIX_SETTINGS='synthetic-settings')
    service_module = load('pinned_preference_service', patched_source/'app/services/settings.py')
    with provider.raw_model_settings():
        raw = config.RAGSettings(search_mode='vector', hyde_enabled=True,
                                 multi_query_enabled=True, chunking_strategy='semantic')
    db = Database(Setting(key='rag_settings', value=raw.model_dump()))
    cache = Cache()
    service = service_module.SettingsService(db=db, cache=cache)
    return SimpleNamespace(service=service, db=db, cache=cache, selected=selected,
                           raw=raw, cls=service_module.SettingsService, source=patched_source)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['vector', 'cascading'])
async def test_persisted_preferences_survive_keyword_runtime_and_unrelated_update(setup_service, mode):
    s = setup_service
    s.db.row.value['search_mode'] = mode
    effective = await s.service.get_settings()
    assert effective.search_mode == 'keyword'
    assert not effective.hyde_enabled and not effective.multi_query_enabled
    assert effective.chunking_strategy == 'auto'
    assert s.db.row.value['search_mode'] == mode
    assert s.cache.value['_catalog_raw_preferences'] is True
    assert s.cache.value['search_mode'] == mode
    assert s.cache.value['hyde_enabled'] is True
    preferences = await s.service.get_preferences()
    assert preferences.embedding_provider == 'none'
    assert preferences.search_mode == mode
    assert preferences.hyde_enabled and preferences.multi_query_enabled
    assert preferences.chunking_strategy == 'semantic'
    updated = await s.service.update_settings({'reranker_top_k': 7})
    assert updated.search_mode == mode
    assert s.db.commits == 1
    assert s.db.row.value['search_mode'] == mode
    assert s.db.row.value['chunking_strategy'] == 'semantic'
    assert s.db.row.value['hyde_enabled'] is True
    assert s.db.row.value['multi_query_enabled'] is True
    assert s.db.row.value['llm_model'] == s.raw.llm_model
    assert s.cache.invalidations == ['settings', 'search']
    s.selected['embedding'] = 'local'
    restored = await s.service.get_settings()
    assert restored.search_mode == mode
    assert restored.hyde_enabled and restored.multi_query_enabled
    assert restored.chunking_strategy == 'semantic'
    assert restored.reranker_top_k == 7


@pytest.mark.asyncio
async def test_old_effective_redis_entry_ignored_and_raw_cache_reused(setup_service):
    s = setup_service
    old = s.raw.model_dump()
    old.update(search_mode='keyword', hyde_enabled=False, multi_query_enabled=False, chunking_strategy='auto')
    s.cache.value = old
    assert (await s.service.get_preferences()).search_mode == 'vector'
    assert s.db.reads == 1
    fresh = s.cls(db=s.db, cache=s.cache)
    prefs = await fresh.get_preferences()
    assert prefs.search_mode == 'vector' and prefs.hyde_enabled
    assert s.db.reads == 1
    assert s.cache.value['_catalog_raw_preferences'] is True


@pytest.mark.asyncio
async def test_settings_callers_cannot_mutate_cached_nested_preferences(setup_service):
    s = setup_service
    a = await s.service.get_settings()
    b = await s.service.get_preferences()
    a.guardrails.hallucination_detection.judge_model = 'caller-mutated'
    b.guardrails.pii_detection.enabled = False
    b.search_mode = 'keyword'
    fresh = await s.service.get_preferences()
    assert fresh.search_mode == 'vector'
    assert fresh.guardrails.pii_detection.enabled is True
    assert fresh.guardrails.hallucination_detection.judge_model == 'synthetic-model'
    assert s.service._local_cache.guardrails.hallucination_detection.judge_model == s.raw.guardrails.hallucination_detection.judge_model


@pytest.mark.asyncio
async def test_real_request_override_function_cannot_bypass_embedding_prerequisites(setup_service):
    s = setup_service
    tree = ast.parse((s.source/'app/api/search.py').read_text())
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == '_apply_overrides')
    # Run the actual patched function without importing routers/network clients.
    scope = {'RAGSettings': type(s.raw), 'SearchRequest': SimpleNamespace}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'pinned-search-overrides', 'exec'), scope)
    base = await s.service.get_settings()
    request = SimpleNamespace(search_mode='vector', hyde_enabled=True, multi_query_enabled=True,
                              reranking_enabled=None, top_k=5)
    effective = await scope['_apply_overrides'](base, request)
    assert effective.search_mode == 'keyword'
    assert not effective.hyde_enabled and not effective.multi_query_enabled
    assert effective.reranker_top_k == 5
    assert base.reranker_top_k != 5
    assert (await s.service.get_preferences()).search_mode == 'vector'


@pytest.mark.asyncio
async def test_concurrent_unrelated_updates_preserve_both_changes(setup_service):
    import asyncio
    s = setup_service
    await s.service.get_preferences()
    original_save = s.service._save_to_db

    async def slow_save(updated):
        await asyncio.sleep(0)
        await original_save(updated)

    s.service._save_to_db = slow_save
    await asyncio.gather(
        s.service.update_settings({'reranker_top_k': 7}),
        s.service.update_settings({'chunk_size': 777}),
    )
    assert s.db.row.value['reranker_top_k'] == 7
    assert s.db.row.value['chunk_size'] == 777


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid_cache', [[], 'invalid', {'_catalog_raw_preferences': True, 'chunk_size': 'invalid'}])
async def test_malformed_redis_preferences_fall_back_to_database(setup_service, invalid_cache):
    s = setup_service
    s.cache.value = invalid_cache
    assert (await s.service.get_preferences()).search_mode == 'vector'
    assert s.db.reads == 1


def test_cache_decoder_requires_boolean_marker_and_preserves_input(setup_service):
    from code_agent.settings import decode_cached_preferences
    s = setup_service
    values = {**s.raw.model_dump(), '_catalog_raw_preferences': True}
    original = deepcopy(values)
    decoded = decode_cached_preferences(values)
    assert decoded.search_mode == 'vector'
    assert values == original
    for invalid in (None, [], 'invalid', {**values, '_catalog_raw_preferences': 'true'},
                    {**values, '_catalog_raw_preferences': 1}, {**values, 'chunk_size': 'invalid'}):
        assert decode_cached_preferences(invalid) is None


@pytest.mark.asyncio
async def test_failed_validation_releases_lock_and_raw_context(setup_service):
    from pydantic import ValidationError
    s = setup_service
    with pytest.raises(ValidationError):
        await s.service.update_settings({'chunk_size': 'invalid'})
    assert s.db.commits == 0
    updated = await s.service.update_settings({'chunk_size': 777})
    assert updated.chunk_size == 777
    assert (await s.service.get_settings()).search_mode == 'keyword'


def test_settings_api_lock_is_scoped_to_running_loop():
    import asyncio
    from code_agent.settings import settings_api_lock

    async def obtain():
        lock = settings_api_lock()
        assert settings_api_lock() is lock
        return lock

    assert asyncio.run(obtain()) is not asyncio.run(obtain())


@pytest.mark.asyncio
async def test_settings_api_lock_is_distinct_from_service_lock(setup_service):
    from code_agent.settings import settings_api_lock
    s = setup_service
    assert settings_api_lock() is not s.service._preference_lock()
    async with settings_api_lock():
        assert (await s.service.get_settings()).search_mode == 'keyword'


@pytest.mark.asyncio
async def test_actual_settings_dependency_retains_request_db_until_release(setup_service):
    import asyncio
    s = setup_service
    tree = ast.parse((s.source/'app/api/settings.py').read_text())
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == 'get_settings_service')
    scope = {'AsyncSession': object, 'Depends': lambda dependency: None,
             'get_db': lambda: None, '_settings_service': s.service}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'pinned-settings-dependency', 'exec'), scope)
    db1, db2 = object(), object()
    first, second = scope['get_settings_service'](db1), scope['get_settings_service'](db2)
    assert await first.__anext__() is s.service
    waiting = asyncio.create_task(second.__anext__())
    try:
        await asyncio.sleep(0)
        assert not waiting.done()
        assert s.service._db is db1
        await first.aclose()
        assert await asyncio.wait_for(waiting, 1) is s.service
        assert s.service._db is db2
    finally:
        if not waiting.done():
            waiting.cancel()
        await first.aclose()
        await second.aclose()
    assert s.service._db is None
