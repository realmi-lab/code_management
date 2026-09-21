"""Real patched provider transports with HTTP doubles; no paid requests or live claims."""
import json
import sys
from types import SimpleNamespace
import httpx
import pytest
from code_agent import ai_config, provider
from code_agent.routing import RoutingLLM
from test_ai_settings import config_path, body
from test_provider import patched_source, load
from test_upstream_adapter import module


def native_modules(monkeypatch, source):
    exceptions=load('routing_exceptions',source/'app/exceptions.py')
    module(monkeypatch,'app.exceptions',CircuitBreakerOpenError=exceptions.CircuitBreakerOpenError,
           SearchServiceError=exceptions.SearchServiceError)
    resilience=load('routing_resilience',source/'app/services/resilience.py')
    module(monkeypatch,'app.services.resilience',CircuitBreaker=resilience.CircuitBreaker)
    openai=load('routing_openai',source/'app/services/generation/openai.py')
    claude=load('routing_claude',source/'app/services/generation/claude.py')
    monkeypatch.setitem(sys.modules,'app.services.generation.openai',openai)
    monkeypatch.setitem(sys.modules,'app.services.generation.claude',claude)
    return openai,claude


def anthropic_response():
    return {'id':'msg_test','type':'message','role':'assistant','model':'synthetic-claude',
        'content':[{'type':'thinking','thinking':'hidden','signature':'sig'},
                   {'type':'text','text':'first '},{'type':'text','text':'second'}],
        'stop_reason':'end_turn','stop_sequence':None,'usage':{'input_tokens':7,'output_tokens':5}}


@pytest.mark.asyncio
async def test_existing_llm_switches_all_four_native_endpoints(config_path,patched_source,monkeypatch):
    from openai import AsyncOpenAI
    from anthropic import AsyncAnthropic
    original,claude=native_modules(monkeypatch,patched_source)
    requests=[]
    def response(request):
        requests.append(request)
        if request.url.host=='api.anthropic.com':return httpx.Response(200,json=anthropic_response())
        return httpx.Response(200,json={'id':'test','object':'chat.completion','created':0,'model':'synthetic',
            'choices':[{'index':0,'message':{'role':'assistant','content':'first second'},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':7,'completion_tokens':5,'total_tokens':12}})
    monkeypatch.setattr(original,'AsyncOpenAI',lambda **kw:AsyncOpenAI(**kw,http_client=httpx.AsyncClient(transport=httpx.MockTransport(response))))
    monkeypatch.setattr(claude,'AsyncAnthropic',lambda **kw:AsyncAnthropic(**kw,http_client=httpx.AsyncClient(transport=httpx.MockTransport(response))))
    # The same startup instance survives every admin settings change.
    llm=original.OpenAILLM(api_key='stale-do-not-use',model='stale-model')
    assert isinstance(llm,RoutingLLM)
    for version,(selected,host) in enumerate([('commandcode','api.commandcode.ai'),('anthropic','api.anthropic.com'),('deepseek','api.deepseek.com'),('openai','api.openai.com')]):
        ai_config.save(body(selected,version=version,key='synthetic-'+selected),1)
        assert await llm.generate('합성 질문',system_prompt='원문 보존')=='first second'
        request=requests[-1];payload=json.loads(request.content)
        assert request.url.host==host and payload['model']==ai_config.MODELS[selected]
        assert request.headers.get('x-api-key')=='synthetic-anthropic' if selected=='anthropic' else request.headers['authorization']=='Bearer synthetic-'+selected
        assert llm.last_usage
        if selected!='commandcode':assert 'reasoning_effort' not in payload
    assert len(requests)==4


@pytest.mark.asyncio
async def test_provider_missing_key_never_calls_previous_client(config_path,patched_source,monkeypatch):
    native_modules(monkeypatch,patched_source)
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({'version':1,'provider':'anthropic','model':'synthetic-claude','embedding':'none','keys':{'OPENAI_API_KEY':'do-not-use'}}))
    llm=RoutingLLM();llm.last_usage={'previous_tokens':123}
    with pytest.raises(ValueError,match='ANTHROPIC_API_KEY'):await llm.generate('question')
    assert llm.last_usage is None


@pytest.mark.asyncio
async def test_env_only_keyword_embedding_never_constructs_sdk(config_path,patched_source,monkeypatch):
    monkeypatch.delenv('CODE_AI_SETTINGS_FILE')
    monkeypatch.setenv('CODE_EMBEDDING_PROVIDER','none')
    exceptions=load('disabled_exceptions',patched_source/'app/exceptions.py')
    monkeypatch.setitem(sys.modules,'app.exceptions',exceptions)
    resilience=load('disabled_resilience',patched_source/'app/services/resilience.py')
    monkeypatch.setitem(sys.modules,'app.services.resilience',resilience)
    upstream=load('disabled_embeddings',patched_source/'app/services/embedding/openai.py')
    def forbidden(**kwargs):raise AssertionError('OpenAI client must not be constructed')
    monkeypatch.setattr(upstream,'AsyncOpenAI',forbidden)
    embedder=upstream.OpenAIEmbedding(api_key='must-not-use')
    with pytest.raises(ValueError,match='disabled'):await embedder.embed_query('인증')
    with pytest.raises(ValueError,match='disabled'):await embedder.embed_documents(['인증'])
    await embedder.client.close()


@pytest.mark.parametrize('reason',['pause_turn','tool_use','refusal',None])
def test_incomplete_claude_never_returns_partial_text(reason):
    from code_agent.claude import response_text
    with pytest.raises(ValueError,match='final text'):
        response_text(SimpleNamespace(stop_reason=reason,content=[SimpleNamespace(type='text',text='partial')]))


@pytest.mark.asyncio
async def test_claude_ragas_adapter_sync_async_preserves_roles(config_path,monkeypatch):
    import anthropic
    from anthropic import Anthropic,AsyncAnthropic
    from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
    ai_config.save(body(),1)
    from code_agent.claude_judge import ClaudeJudge
    observed=[]
    def response(request):
        observed.append(request)
        return httpx.Response(200,json=anthropic_response())
    monkeypatch.setattr(anthropic,'Anthropic',lambda **kw:Anthropic(**kw,http_client=httpx.Client(transport=httpx.MockTransport(response))))
    monkeypatch.setattr(anthropic,'AsyncAnthropic',lambda **kw:AsyncAnthropic(**kw,http_client=httpx.AsyncClient(transport=httpx.MockTransport(response))))
    messages=[SystemMessage(content='Judge faithfully'),HumanMessage(content='example'),AIMessage(content='answer'),HumanMessage(content=[{'type':'text','text':'question'}])]
    judge=ClaudeJudge()
    assert judge.invoke(messages,stop=['END']).content=='first second'
    assert (await judge.ainvoke(messages,stop=['END'])).content=='first second'
    for request in observed:
        payload=json.loads(request.content)
        assert request.url.host=='api.anthropic.com'
        assert payload['system']=='Judge faithfully' and payload['stop_sequences']==['END']
        assert [m['role'] for m in payload['messages']]==['user','assistant','user']
        assert payload['messages'][-1]['content']=='question'
    assert judge._identifying_params=={'model':ai_config.MODELS['anthropic']}


@pytest.mark.asyncio
@pytest.mark.parametrize('response',[
    'faithfulness_score: 1\nfaithfulness_score: 2\nverdict: FAITHFUL',
    'faithfulness_score: 1\nverdict: FAITHFUL\nverdict: UNFAITHFUL',
    None,
])
async def test_claude_or_other_judge_ambiguous_output_fails_closed(response):
    from unittest.mock import AsyncMock
    from code_agent.safety import StrictJudge
    from code_agent.store import DomainError
    judge=StrictJudge(SimpleNamespace(generate=AsyncMock(return_value=response)),'faithfulness_score',{'FAITHFUL','UNFAITHFUL'})
    with pytest.raises(DomainError) as error:await judge.generate('synthetic')
    assert error.value.status==502


@pytest.mark.asyncio
async def test_telemetry_failures_do_not_fail_successful_provider_response():
    from code_agent.operations import turn_trace,TrackedLLM
    from unittest.mock import AsyncMock
    class BrokenTrace:
        def start_span(self,**kw):return self
        def update(self,**kw):raise OSError('telemetry unavailable')
        def end(self):raise OSError('telemetry unavailable')
    monitor=SimpleNamespace(create_trace=lambda *args:BrokenTrace())
    llm=SimpleNamespace(generate=AsyncMock(return_value='result'),model='synthetic',last_usage={})
    with turn_trace(monitor,1,'thread','request'):
        assert await TrackedLLM(llm,'Explanation').generate('synthetic')=='result'
    llm.generate.assert_awaited_once()


def test_startup_openai_without_explicit_model_has_real_default(config_path):
    assert RoutingLLM().model==ai_config.MODELS['openai']
    assert provider.public_settings()['model']==ai_config.MODELS['openai']
