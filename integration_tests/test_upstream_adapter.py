"""Contract checks for the real production adapter; upstream IO is replaced here only.
These checks do not claim live PGVector, Nori, the neural reranker, or provider quality.
"""
import sys,types,uuid,json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import update
from code_agent.gateway import UrstoryGateway,INDEX,index_identity
from code_agent.models import Explanation, Plan, Wording, Turn
from pydantic import ValidationError
from code_agent.store import state,DomainError

def module(monkeypatch,name,**attrs):
    parts=name.split('.')
    for i in range(1,len(parts)+1):
        p='.'.join(parts[:i])
        if p not in sys.modules:
            m=types.ModuleType(p);m.__path__=[];monkeypatch.setitem(sys.modules,p,m)
            if i>1:monkeypatch.setattr(sys.modules['.'.join(parts[:i-1])],parts[i-1],m,raising=False)
    for k,v in attrs.items():monkeypatch.setattr(sys.modules[name],k,v,raising=False)

def fake_settings():return NS(llm_model='configured-model',llm_temperature=.17,embedding_model='configured-embedding')

@pytest.fixture(autouse=True)
def explicit_safety_double(monkeypatch):
    # This file isolates upstream adapter IO. Actual detectors are tested separately.
    class SafetyDouble:
        def redact(self,value): return value
        async def prepare(self,payload,llm): return payload
        async def validate(self,result,evidence,llm): pass
    monkeypatch.setattr('code_agent.gateway.CatalogSafety',SafetyDouble)

@pytest.mark.asyncio
async def test_structured_original_llm_call_and_cleanup(seeded):
    gateway=UrstoryGateway(seeded);llm=NS(generate=AsyncMock(return_value='```json\n{"text":"설명","references":[]}\n```'),client=NS(close=AsyncMock()))
    gateway._llm=AsyncMock(return_value=llm)
    r=await gateway.json(Explanation,'system policy',{'question':'테스트'})
    assert r.text=='설명'
    llm.generate.assert_awaited_once()
    args,kwargs=llm.generate.await_args
    assert args==('{"question": "테스트"}',)
    assert kwargs['system_prompt'].startswith('system policy')
    # Decode the embedded schema rather than depend on whitespace or its label.
    prompt=kwargs['system_prompt']
    embedded,_=json.JSONDecoder().raw_decode(prompt[prompt.index('{'):])
    assert embedded==Explanation.model_json_schema()
    llm.client.close.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize('schema,response,expected',[
    (Plan,{'action':'search','query':'로그인 실패 알림','proposed_message':None,'menu':None,'trigger':None},
     {'action':'search','query':'로그인 실패 알림','proposed_message':'','menu':'','trigger':''}),
    (Plan,{'action':'search','query':None},{'action':'search','query':'','proposed_message':'','menu':'','trigger':''}),
    (Wording,{'message':'다시 로그인해주세요.','menu':None,'trigger':None,'explanation':None},
     {'message':'다시 로그인해주세요.','menu':'','trigger':'','explanation':''}),
])
async def test_nullable_optional_ai_strings_are_normalized(seeded,schema,response,expected):
    gateway=UrstoryGateway(seeded)
    llm=NS(generate=AsyncMock(return_value=json.dumps(response,ensure_ascii=False)),client=NS(close=AsyncMock()))
    gateway._llm=AsyncMock(return_value=llm)
    result=await gateway.json(schema,'policy',{'question':'합성 테스트'})
    assert result.model_dump()==expected
    llm.client.close.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize('schema,response',[
    (Wording,{'message':None}),
    (Wording,{}),
    (Wording,{'message':'   '}),
    (Plan,{'action':None}),
    (Plan,{'action':'approve'}),
    (Plan,{'action':'search','unknown':None}),
    (Wording,{'message':'다시 로그인해주세요.','code':'AT-9999'}),
    (Plan,{'query':123}),
    (Wording,{'message':'다시 로그인해주세요.','menu':[]}),
    (Plan,{'query':'가'*3001}),
])
async def test_ai_contract_still_rejects_invalid_values(seeded,schema,response):
    gateway=UrstoryGateway(seeded)
    llm=NS(generate=AsyncMock(return_value=json.dumps(response,ensure_ascii=False)),client=NS(close=AsyncMock()))
    gateway._llm=AsyncMock(return_value=llm)
    with pytest.raises(DomainError) as error:
        await gateway.json(schema,'policy',{})
    assert error.value.status==502
    llm.client.close.assert_awaited_once()

@pytest.mark.parametrize('field',['proposed_message','menu','trigger'])
def test_user_turn_optional_strings_still_reject_null(field):
    payload={'request_id':str(uuid.uuid4()),'expected_version':0,'text':'로그인 실패 알림',field:None}
    with pytest.raises(ValidationError):
        Turn.model_validate(payload)

@pytest.mark.asyncio
@pytest.mark.parametrize('invalid',['not JSON',None,'{}'])
async def test_bad_json_closes_client_without_save(seeded,invalid):
    g=UrstoryGateway(seeded);llm=NS(generate=AsyncMock(return_value=invalid),client=NS(close=AsyncMock()));g._llm=AsyncMock(return_value=llm)
    with pytest.raises(DomainError):await g.json(Explanation,'',{})
    llm.client.close.assert_awaited_once()

@pytest.mark.asyncio
async def test_catalogue_requires_current_index(seeded):
    g=UrstoryGateway(seeded)
    with pytest.raises(DomainError,match='인덱싱'):await g.search('인증')

@pytest.mark.asyncio
async def test_empty_catalogue_makes_no_upstream_call(store):
    g=UrstoryGateway(store);g._settings=AsyncMock(side_effect=AssertionError('unnecessary'))
    found,trace=await g.search('인증');assert found==[] and trace[0]['name']=='empty_catalogue'

@pytest.mark.asyncio
async def test_full_orchestrator_and_snapshot_scoped_engines(monkeypatch,seeded):
    settings=fake_settings();snapshot=str(uuid.uuid4());calls=[];constructed={}
    with seeded.engine.begin() as c:c.execute(update(state).values(indexed_version=1,snapshot=snapshot,indexed_model=index_identity(settings.embedding_model)))
    class V:
        def __init__(self,session_factory):self.factory=session_factory
        async def search(self,q,top_k=20,doc_id=None):calls.append(('vector',q,top_k,doc_id));return []
    class K:
        def __init__(self,**kw):constructed['keyword']=kw;self.close=AsyncMock()
        async def search(self,q,top_k=20,doc_id=None):calls.append(('keyword',q,top_k,doc_id));return []
    class E:
        def __init__(self,**kw):constructed['embedder']=kw;self.client=NS(close=AsyncMock())
    reranker=object();monitor=object()
    class O:
        def __init__(self,**kw):constructed['engine']=kw
        async def search(self,q,s,generate_answer=True):
            assert s is settings and not generate_answer
            await constructed['engine']['vector_engine'].search([1.0],top_k=7,doc_id='attempt-other-snapshot')
            await constructed['engine']['keyword_engine'].search(q,top_k=6,doc_id='attempt-other-snapshot')
            return NS(documents=[NS(metadata={'code':'AT-1923','revision':1},content='INDEX TEXT MUST NOT REPLACE RAW'),NS(metadata={'code':'AT-1924','revision':99}),NS(metadata={'code':'AT-9999','revision':1})],trace=[NS(model_dump=lambda:{'name':'mock-orchestrator'})])
    module(monkeypatch,'app.api.search',get_orchestrator=lambda:NS(reranker=reranker))
    module(monkeypatch,'app.config',get_settings=lambda:NS(openai_api_key='synthetic',elasticsearch_url='http://es'))
    module(monkeypatch,'app.models.database',_async_session_factory=object())
    module(monkeypatch,'app.services.search.vector',VectorSearchEngine=V)
    module(monkeypatch,'app.services.search.keyword_es',ElasticsearchNoriEngine=K)
    module(monkeypatch,'app.services.search.hybrid',HybridSearchOrchestrator=O)
    module(monkeypatch,'app.services.embedding.openai',OpenAIEmbedding=E)
    module(monkeypatch,'app.services.hyde.generator',HyDEGenerator=lambda **kw:kw)
    g=UrstoryGateway(seeded,monitor);g._settings=AsyncMock(return_value=settings)
    llm=NS(client=NS(close=AsyncMock()));g._llm=AsyncMock(return_value=llm)
    found,trace=await g.search('인증')
    assert found[0]['message']=='메뉴확인 30초 이후에 인증해주세요.' and len(found)==1
    assert constructed['engine']['reranker'].base is reranker and constructed['engine']['langfuse_monitor'] is monitor
    assert constructed['keyword']['index_name']==INDEX
    assert [x[-1] for x in calls]==[snapshot,snapshot]
    assert 'cm_search_chunks' in str(constructed['engine']['vector_engine']._FILTERED_SQL)
    llm.client.close.assert_awaited_once();constructed['engine']['keyword_engine'].close.assert_awaited_once()
    constructed['engine']['embedder'].client.close.assert_awaited_once()

@pytest.mark.asyncio
async def test_configured_model_used_not_hardcoded(monkeypatch,seeded):
    values={}
    def make(**kw):values.update(kw);return object()
    module(monkeypatch,'app.config',get_settings=lambda:NS(openai_api_key='synthetic'))
    module(monkeypatch,'app.services.generation.openai',OpenAILLM=make)
    g=UrstoryGateway(seeded);g._settings=AsyncMock(return_value=fake_settings());await g._llm()
    assert values['model']=='configured-model' and values['temperature']==.17

@pytest.mark.asyncio
async def test_provider_failure_does_not_expose_secret_response(seeded):
    g=UrstoryGateway(seeded);llm=NS(generate=AsyncMock(side_effect=RuntimeError('synthetic-private-key-must-not-leak')),client=NS(close=AsyncMock()));g._llm=AsyncMock(return_value=llm)
    with pytest.raises(DomainError) as err:await g.json(Explanation,'',{})
    assert err.value.status==503 and 'synthetic-private' not in str(err.value)
    llm.client.close.assert_awaited_once()
