"""Tracked, fail-closed changes to the build copy of the pinned upstream only."""
import ast
import hashlib
import json
from pathlib import Path
import sys


def apply(root):
    root = Path(root)
    edits = []

    def replace(path, old, new):
        p = root / path
        source = p.read_text()
        if source.count(old) != 1:
            raise RuntimeError(f'Upstream provider contract changed: {path}')
        result = source.replace(old, new)
        ast.parse(result)
        p.write_text(result)
        edits.append({'path': path, 'before_sha256': hashlib.sha256(source.encode()).hexdigest(),
                      'after_sha256': hashlib.sha256(result.encode()).hexdigest()})

    replace('app/services/generation/openai.py',
            '    _NO_TEMPERATURE_MODELS =',
            '    def __new__(cls, api_key=None, model=None, temperature=0.3):\n'
            '        import os\n'
            '        if cls is not OpenAILLM: return super().__new__(cls)\n'
            '        if os.getenv("CODE_AI_SETTINGS_FILE"):\n'
            '            from code_agent.routing import RoutingLLM\n'
            '            return RoutingLLM(api_key, model, temperature)\n'
            '        from code_agent.provider import anthropic_enabled\n'
            '        if anthropic_enabled():\n'
            '            from code_agent.claude import make_llm\n'
            '            return make_llm()\n'
            '        return super().__new__(cls)\n\n'
            '    _NO_TEMPERATURE_MODELS =')
    replace('app/services/generation/claude.py',
            '        self.client = AsyncAnthropic(api_key=api_key)',
            '        from code_agent.provider import anthropic_enabled, anthropic_options\n'
            '        self.client = AsyncAnthropic(**anthropic_options()) if anthropic_enabled() else AsyncAnthropic(api_key=api_key)')
    replace('app/services/generation/claude.py',
            '            return response.content[0].text',
            '            from code_agent.claude import response_text\n'
            '            self.last_usage = response.usage.model_dump()\n'
            '            return response_text(response)')
    replace('app/services/generation/openai.py',
            '        self.client = AsyncOpenAI(api_key=api_key)\n        self.model = model',
            '        from code_agent.provider import client_options, model_name\n'
            '        self.client = AsyncOpenAI(**client_options(api_key))\n'
            '        self.model = model_name(model)')
    replace('app/services/generation/openai.py',
            '        kwargs: dict = {"model": self.model, "messages": messages}',
            '        from code_agent.provider import reasoning_options\n'
            '        kwargs: dict = {"model": self.model, "messages": messages, **reasoning_options()}')
    replace('app/services/generation/openai.py',
            '                return response.choices[0].message.content',
            '                self.last_usage = response.usage.model_dump() if response.usage else None\n'
            '                return response.choices[0].message.content')
    replace('app/services/evaluation/ragas.py',
            '        evaluator_llm = LangchainLLMWrapper(\n            ChatOpenAI(model="gpt-4o", temperature=0)\n        )',
            '        from code_agent.provider import evaluation_llm\n'
            '        evaluator_llm = LangchainLLMWrapper(evaluation_llm())')
    replace('app/services/evaluation/ragas.py',
            '            OpenAIEmbeddings(model="text-embedding-3-small")',
            '            __import__("code_agent.embeddings", fromlist=["evaluation_embeddings"]).evaluation_embeddings()')
    replace('app/services/evaluation/ragas.py',
            '        evaluator_embeddings = LangchainEmbeddingsWrapper(',
            '        from code_agent.embeddings import keyword_only\n'
            '        evaluator_embeddings = None if keyword_only() else LangchainEmbeddingsWrapper(')
    replace('app/services/evaluation/ragas.py',
            '            ResponseRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings),',
            '            *([] if evaluator_embeddings is None else [ResponseRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings)]),')
    replace('app/services/evaluation/ragas.py',
            '    async def evaluate(self, dataset_id: str, run_id: str) -> None:',
            '    @__import__("code_agent.config_scope", fromlist=["pinned_configuration"]).pinned_configuration\n'
            '    async def evaluate(self, dataset_id: str, run_id: str) -> None:')
    replace('app/services/evaluation/ragas.py',
            '            resp = await client.post(',
            '            from code_agent.config_scope import assert_current\n'
            '            assert_current()\n'
            '            resp = await client.post(')
    replace('app/services/evaluation/ragas.py',
            '            data = resp.json()',
            '            assert_current()\n'
            '            data = resp.json()')
    replace('app/tasks/indexing.py',
            'async def _run_indexing(doc_id: str):',
            '@__import__("code_agent.config_scope", fromlist=["pinned_configuration"]).pinned_configuration\n'
            'async def _run_indexing(doc_id: str):')
    replace('app/services/embedding/openai.py',
            '    MAX_TOKENS = 8191',
            '    def __new__(cls, api_key=None, model=None, dimensions=None):\n'
            '        import os\n'
            '        if cls is not OpenAIEmbedding: return super().__new__(cls)\n'
            '        if os.getenv("CODE_AI_SETTINGS_FILE"):\n'
            '            from code_agent.routing import RoutingEmbedding\n'
            '            return RoutingEmbedding(api_key, model, dimensions)\n'
            '        from code_agent.embeddings import local_enabled, keyword_only, LocalEmbedding, DisabledEmbedding\n'
            '        if keyword_only(): return DisabledEmbedding()\n'
            '        if local_enabled():\n'
            '            return LocalEmbedding(api_key=api_key, model=model, dimensions=dimensions)\n'
            '        return super().__new__(cls)\n\n'
            '    MAX_TOKENS = 8191')
    replace('app/config.py',
            '        explicitly_set = self.model_fields_set',
            '        from code_agent.provider import apply_model_settings\n'
            '        apply_model_settings(self)\n'
            '        explicitly_set = self.model_fields_set')
    replace('app/api/settings.py',
            '    return models',
            '    from code_agent.provider import selected_provider, model_name\n'
            '    if selected_provider() in ("commandcode", "anthropic", "deepseek"):\n'
            '        models[selected_provider()] = [model_name(None)]\n'
            '    return models')
    replace('app/api/health.py',
            '    openai_ok = await check_openai()',
            '    from code_agent.health import llm_connected, embedding_connected, descriptions\n'
            '    openai_ok = await llm_connected()\n'
            '    embedding_ok = await embedding_connected()\n'
            '    llm_description, embedding_description = descriptions()')
    replace('app/api/health.py', '            "openai": {',
            '            "embedding": {\n'
            '                "status": "disabled" if __import__("code_agent.embeddings", fromlist=["keyword_only"]).keyword_only() else "connected" if embedding_ok else "disconnected",\n'
            '                "required": False, "description": embedding_description,\n'
            '                "impact": "disconnected 시 인덱싱 및 의미 검색 불가",\n'
            '            },\n'
            '            "llm": {')
    replace('app/api/health.py', '"description": "OpenAI API (임베딩, LLM 생성, 평가)"',
            '"description": llm_description')
    replace('app/api/system.py', '    components = {',
            '    from code_agent.health import llm_connected, embedding_connected\n'
            '    from code_agent.embeddings import keyword_only\n'
            '    components = {')
    replace('app/api/system.py', '        "openai": await check_openai(),',
            '        "llm": await llm_connected(),')
    replace('app/api/system.py', '    all_ok = all(v == "connected" for v in components.values())',
            '    if not keyword_only(): components["embedding"] = await embedding_connected()\n'
            '    all_ok = all(components.values())')
    replace('app/services/settings.py', 'class SettingsService:', 'class UpstreamSettingsService:')
    replace('app/services/settings.py', '        await self._db.commit()',
            '        await self._db.commit()\n\n'
            'from code_agent.settings import PreferenceSettingsMixin\n\n'
            'class SettingsService(PreferenceSettingsMixin, UpstreamSettingsService):\n'
            '    pass')
    # Ignore pre-upgrade Redis entries that contained effective overrides.
    replace('app/services/settings.py', '            if cached is not None:\n                self._local_cache = RAGSettings(**cached)',
            '            from code_agent.settings import decode_cached_preferences\n'
            '            decoded = decode_cached_preferences(cached)\n'
            '            if decoded is not None:\n'
            '                self._local_cache = decoded')
    replace('app/services/settings.py', 'settings.model_dump(), ttl=60',
            '{**settings.model_dump(), "_catalog_raw_preferences": True}, ttl=60')
    replace('app/api/settings.py', '    settings = await service.get_settings()',
            '    settings = await service.get_preferences()')
    replace('app/api/settings.py',
            '''def get_settings_service(db: AsyncSession = Depends(get_db)) -> SettingsService:
    global _settings_service
    if _settings_service is None:
        from app.api.search import get_cache_service
        _settings_service = SettingsService(db, cache=get_cache_service())
    _settings_service._db = db
    return _settings_service''',
            '''async def get_settings_service(db: AsyncSession = Depends(get_db)):
    from code_agent.settings import settings_api_lock
    global _settings_service
    async with settings_api_lock():
        if _settings_service is None:
            from app.api.search import get_cache_service
            _settings_service = SettingsService(db, cache=get_cache_service())
        _settings_service._db = db
        try:
            yield _settings_service
        finally:
            _settings_service._db = None''')
    replace('app/api/search.py', '        return base.model_copy(update=overrides)',
            '        result = base.model_copy(update=overrides, deep=True)\n'
            '        from code_agent.provider import apply_model_settings\n'
            '        apply_model_settings(result)\n'
            '        return result')
    replace('app/services/document/indexer.py',
            '        embeddings = await self.embedding_provider.embed_documents(texts)',
            '        from code_agent.embeddings import keyword_only\n'
            '        embeddings = [None] * len(texts) if keyword_only() else await self.embedding_provider.embed_documents(texts)')
    replace('app/services/document/stores/pgvector_store.py',
            '                embedding_str = f"[{\',\'.join(str(v) for v in embedding)}]"',
            '                embedding_str = None if embedding is None else f"[{\',\'.join(str(v) for v in embedding)}]"')
    replace('app/services/document/stores/pgvector_store.py',
            '"meta": json.dumps(chunk.metadata or {}, ensure_ascii=False)',
            '"meta": json.dumps({**(chunk.metadata or {}), "embedding_model": __import__("code_agent.embeddings", fromlist=["storage_identity"]).storage_identity()}, ensure_ascii=False)')
    replace('app/services/search/vector.py',
            '        FROM chunks c\n        ORDER BY',
            '        FROM chunks c\n        WHERE c.embedding IS NOT NULL AND c.metadata->>\'embedding_model\' = :embedding_model\n        ORDER BY')
    replace('app/services/search/vector.py',
            '        WHERE c.document_id = :doc_id\n',
            '        WHERE c.document_id = :doc_id AND c.embedding IS NOT NULL AND c.metadata->>\'embedding_model\' = :embedding_model\n')
    replace('app/services/search/vector.py',
            '                    "top_k": top_k,',
            '                    "top_k": top_k,\n'
            '                    "embedding_model": __import__("code_agent.embeddings", fromlist=["storage_identity"]).storage_identity(),')
    (root / 'catalog-provider-patches.json').write_text(json.dumps(edits, indent=2))
    return edits


if __name__ == '__main__':
    apply(sys.argv[1] if len(sys.argv) > 1 else '/app')
