"""Provider selection, private key persistence and opt-out search contracts."""
import json,os,stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from code_agent import ai_config,provider
from code_agent.store import DomainError
from test_api import app_for,headers
from fastapi.testclient import TestClient
from test_provider import patched_source,load

@pytest.fixture
def config_path(tmp_path,monkeypatch):
    path=tmp_path/'private'/'ai.json';monkeypatch.setenv('CODE_AI_SETTINGS_FILE',str(path))
    monkeypatch.setenv('CODE_LLM_PROVIDER','openai');monkeypatch.setenv('CODE_EMBEDDING_PROVIDER','none')
    monkeypatch.delenv('CODE_LLM_MODEL',raising=False)
    monkeypatch.setenv('LOCAL_EMBEDDING_URL','http://local-embeddings:8080')
    monkeypatch.setattr(ai_config,'local_status',lambda:{'local_configured':True,'local_available':True,'local_state':'ready'})
    for key in ai_config.KEYS.values():monkeypatch.delenv(key,raising=False)
    return path

def body(provider='anthropic',version=0,embedding='none',key='synthetic-private-key'):
    return {'provider':provider,'version':version,'embedding':embedding,'api_key':key}


def test_settings_require_original_admin_and_hide_keys(seeded,config_path):
    with TestClient(app_for(seeded)) as client:
        assert client.get('/api/code-catalog/ai-settings').status_code==401
        assert client.put('/api/code-catalog/ai-settings',headers=headers(),json=body()).status_code==403
        saved=client.put('/api/code-catalog/ai-settings',headers=headers('admin'),json=body())
        assert saved.status_code==200
        assert 'synthetic-private-key' not in saved.text
        loaded=client.get('/api/code-catalog/ai-settings',headers=headers('admin'))
        assert loaded.json()['provider']=='anthropic' and loaded.json()['configured']['anthropic']
        assert 'synthetic-private-key' not in loaded.text
        assert stat.S_IMODE(config_path.stat().st_mode)==0o600
        assert json.loads(config_path.read_text())['updated_by']==1
        assert client.put('/api/code-catalog/ai-settings',headers=headers('admin'),json=body()).status_code==409
        assert client.put('/api/code-catalog/ai-settings',headers=headers('admin'),json=body(version=1,key='')).status_code==200
        assert ai_config.key('ANTHROPIC_API_KEY')=='synthetic-private-key'


def test_provider_choices_and_search_are_independent(config_path,patched_source):
    config=load('selectable_config',patched_source/'app/config.py')
    for i,p in enumerate(['deepseek','anthropic','openai','commandcode']):
        ai_config.save(body(p,version=i),1)
        settings=config.RAGSettings()
        assert settings.llm_provider==p and settings.search_mode=='keyword'
        assert settings.embedding_provider=='none'
        assert not settings.hyde_enabled and not settings.multi_query_enabled
        assert settings.llm_model==ai_config.MODELS[p]
    ai_config.save(body('anthropic',version=4,embedding='local',key=''),1)
    settings=config.RAGSettings()
    assert settings.search_mode=='hybrid' and settings.embedding_provider=='local'
    assert 'synthetic' not in str(ai_config.public())


def test_missing_key_never_reuses_other_provider(config_path):
    ai_config.save(body(),1)
    with pytest.raises(DomainError,match='키'):
        ai_config.save(body('deepseek',version=1,key=''),1)
    with pytest.raises(DomainError,match='OpenAI'):
        ai_config.save(body(version=1,key='',embedding='openai'),1)
    assert ai_config.read()['provider']=='anthropic'


@pytest.mark.asyncio
async def test_keyword_mode_never_calls_embedding(config_path):
    from code_agent.routing import RoutingEmbedding
    with pytest.raises(ValueError,match='disabled'):await RoutingEmbedding().embed_query('인증')
    from code_agent.embeddings import evaluation_embeddings
    with pytest.raises(ValueError,match='disabled'):evaluation_embeddings()


@pytest.mark.asyncio
async def test_keyword_document_index_stores_nulls_and_nori(config_path,patched_source,monkeypatch):
    import sys,types
    module=types.ModuleType('app.services.chunking.base');module.Chunk=object
    monkeypatch.setitem(sys.modules,'app.services.chunking.base',module)
    module=types.ModuleType('app.services.embedding.base');module.EmbeddingProvider=object
    monkeypatch.setitem(sys.modules,'app.services.embedding.base',module)
    indexer=load('keyword_indexer',patched_source/'app/services/document/indexer.py')
    embedder=SimpleNamespace(embed_documents=AsyncMock(side_effect=AssertionError('must not embed')))
    pg=SimpleNamespace(write=AsyncMock());es=SimpleNamespace(write=AsyncMock())
    chunks=[SimpleNamespace(content='인증 대기')]
    await indexer.DocumentIndexer(embedder,pg,es).index('synthetic',chunks)
    embedder.embed_documents.assert_not_awaited()
    assert pg.write.await_args.args[1]==[None]
    es.write.assert_awaited_once()


@pytest.mark.asyncio
async def test_claude_uses_native_messages_and_final_text(config_path,patched_source,monkeypatch):
    import httpx
    from anthropic import AsyncAnthropic
    from test_upstream_adapter import module
    ai_config.save(body(),1)
    exceptions=load('claude_exceptions',patched_source/'app/exceptions.py')
    module(monkeypatch,'app.exceptions',SearchServiceError=exceptions.SearchServiceError)
    upstream=load('claude_native',patched_source/'app/services/generation/claude.py')
    observed=[]
    def reply(request):
        observed.append(request)
        return httpx.Response(200,json={'id':'msg_test','type':'message','role':'assistant','model':ai_config.MODELS['anthropic'],
          'content':[{'type':'thinking','thinking':'private reasoning','signature':'sig'},{'type':'text','text':'검증 완료'}],
          'stop_reason':'end_turn','stop_sequence':None,'usage':{'input_tokens':7,'output_tokens':5}})
    monkeypatch.setattr(upstream,'AsyncAnthropic',lambda **kw:AsyncAnthropic(**kw,http_client=httpx.AsyncClient(transport=httpx.MockTransport(reply))))
    llm=upstream.ClaudeLLM(api_key='unused',model=provider.model_name(None))
    try:assert await llm.generate('합성 질문',system_prompt='원문 보존')=='검증 완료'
    finally:await llm.client.close()
    request=observed[0]
    assert str(request.url)=='https://api.anthropic.com/v1/messages'
    assert request.headers['x-api-key']=='synthetic-private-key'
    payload=json.loads(request.content)
    assert payload['model']=='claude-sonnet-5' and payload['system']=='원문 보존'
    assert 'temperature' not in payload and 'reasoning_effort' not in payload
    assert llm.last_usage['input_tokens']==7


def test_claude_truncation_never_saved():
    from code_agent.claude import response_text
    with pytest.raises(ValueError,match='truncated'):response_text(SimpleNamespace(stop_reason='max_tokens'))


def test_deepseek_direct_endpoint_and_secret(config_path):
    ai_config.save(body('deepseek'),1)
    assert provider.client_options(None)=={'api_key':'synthetic-private-key','base_url':'https://api.deepseek.com'}
    assert provider.model_name(None)=='deepseek-flash'
    assert provider.evaluation_options()['base_url']=='https://api.deepseek.com'
