import json,uuid
import pytest
from code_agent.agent import Agent
from code_agent.models import Turn,Explanation
from code_agent.store import DomainError,SampleStore
from code_agent.discovery import quantity_page,quantity_terms,quantity_matches
from code_agent.compare import compare_message
from conftest import ADMIN,USER,ScriptedGateway
from test_api import app_for,headers
from fastapi.testclient import TestClient

def test_quantity_is_exact_and_not_notes_or_another_unit():
    terms=quantity_terms('30 초 관련 메시지')
    assert quantity_matches({'message':'30초 이내'},terms)
    assert quantity_matches({'message':'30.0초 이후'},terms)
    assert not quantity_matches({'message':'130초 이후'},terms)
    assert not quantity_matches({'message':'30분','notes':'30초'},terms)

def test_quantity_thousands_separators_and_signs_are_not_numeric_suffixes():
    terms=quantity_terms('1,000원 관련 코드')
    assert quantity_matches({'message':'1000원 이상'},terms)
    assert quantity_matches({'message':'1,000.00원 이상'},terms)
    assert not quantity_matches({'message':'9,000원 이상'},terms)
    assert not quantity_matches({'message':'0원'},terms)
    assert not quantity_terms('1,00원')
    assert not quantity_matches({'message':'-30초'},quantity_terms('30초'))

def test_all_matches_pagination_isolated_and_version_checked(seeded):
    sample=SampleStore(seeded)
    first=quantity_page(sample,'30초 관련',0,7)
    rest=quantity_page(sample,'30초 관련',7,100,first['catalog_version'])
    assert first['total']>8 and first['total']==len(first['items'])+len(rest['items'])
    assert not ({r['code'] for r in first['items']}&{r['code'] for r in rest['items']})
    assert all(r['status']=='active' for r in first['items']+rest['items'])
    assert quantity_page(seeded,'30초')['total']==2
    with pytest.raises(DomainError) as error:quantity_page(sample,'30초',version=999)
    assert error.value.status==409
    with TestClient(app_for(seeded)) as client:
        assert client.get('/api/code-catalog/quantity-matches?q=30초').status_code==401
        r=client.get('/api/code-catalog/quantity-matches?q=30초&namespace=demo&limit=7',headers=headers())
        assert r.status_code==200 and r.json()['total']==first['total']

@pytest.mark.asyncio
async def test_failed_ai_still_exposes_verified_db_search_and_restores_scope(seeded):
    store=SampleStore(seeded);g=ScriptedGateway(store)
    original=g.json
    async def generate(schema,system,payload):
        if schema is Explanation:raise DomainError('합성 모델 장애',502)
        return await original(schema,system,payload)
    g.json=generate
    t=store.create_thread(USER)
    result=await Agent(store,g).turn(USER,t['id'],Turn(request_id=uuid.uuid4(),expected_version=0,text='30초 관련 메시지 찾아줘'))
    assert result['ai_error']['status']==502 and result['ai_used'] is False
    assert len(result['candidates'])==8 and result['search_info']['quantity']['total']>8
    history=store.get_thread(USER,t['id'])['history']
    assert history[-1]['search_info']==result['search_info'] and history[-1]['ai_used'] is False
    assert not any(call[0]=='llm' and call[1]=='Plan' for call in g.calls)

@pytest.mark.asyncio
async def test_retrieval_failure_is_not_saved_as_empty_search(seeded):
    g=ScriptedGateway(seeded);g.search_error=DomainError('검색 실패',503)
    t=seeded.create_thread(USER)
    with pytest.raises(DomainError):await Agent(seeded,g).turn(USER,t['id'],Turn(request_id=uuid.uuid4(),expected_version=0,text='30초 코드 찾아줘'))
    assert seeded.get_thread(USER,t['id'])['version']==0


@pytest.mark.asyncio
@pytest.mark.parametrize('action',['search','explain','compare'])
@pytest.mark.parametrize('status',[422,502,503,504])
async def test_read_only_ai_failure_preserves_originals_comparison_and_replay(seeded,action,status):
    g=ScriptedGateway(seeded)
    original=g.json
    async def generate(schema,system,payload):
        if schema is Explanation:raise DomainError('합성 설명 실패',status)
        return await original(schema,system,payload)
    g.json=generate
    expected=seeded.snapshot()[1]
    proposal='30초 이내에 인증해주세요.' if action=='compare' else ''
    t=seeded.create_thread(USER)
    request=Turn(request_id=uuid.uuid4(),expected_version=0,text='30초 인증 안내',action=action,proposed_message=proposal)
    agent=Agent(seeded,g)
    result=await agent.turn(USER,t['id'],request)
    assert result['action']==action and result['candidates']==expected
    assert result['ai_error']=={'status':status,'message':'합성 설명 실패'}
    assert result['ai_used'] is False and result['draft'] is None
    if action=='compare':
        assert result['comparisons']==[dict(code=row['code'],**compare_message(proposal,row)) for row in expected]
        assert any(row['verdict']=='different_conditions' for row in result['comparisons'])
    else:
        assert result['search_info']['quantity']['total']==2
    saved=seeded.get_thread(USER,t['id'])
    assert saved['history'][-1]['content']==result['answer']
    assert saved['history'][-1]['ai_error']==result['ai_error']
    assert saved['history'][-1]['ai_used'] is False
    assert seeded.list_drafts(USER)==[]
    calls=list(g.calls)
    # Stored JSON converts the comparison signature's tuples to arrays; the
    # public JSON response must remain identical on replay.
    assert await agent.turn(USER,t['id'],request)==json.loads(json.dumps(result))
    assert g.calls==calls and seeded.get_thread(USER,t['id'])['version']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('action',['search','explain','compare'])
@pytest.mark.parametrize('status',[401,403,404,409,500])
async def test_other_explanation_failures_still_raise_without_history(seeded,action,status):
    g=ScriptedGateway(seeded)
    g.responses=[DomainError('다른 단계 오류',status)]
    t=seeded.create_thread(USER)
    with pytest.raises(DomainError) as error:
        await Agent(seeded,g).turn(USER,t['id'],Turn(request_id=uuid.uuid4(),expected_version=0,
            text='인증 안내',action=action,proposed_message='30초 이내에 인증해주세요.' if action=='compare' else ''))
    assert error.value.status==status
    assert seeded.get_thread(USER,t['id'])['history']==[]


@pytest.mark.asyncio
async def test_planner_failure_does_not_become_read_only_fallback(seeded):
    g=ScriptedGateway(seeded)
    g.responses=[DomainError('의도 분류 실패',503)]
    t=seeded.create_thread(USER)
    with pytest.raises(DomainError) as error:
        await Agent(seeded,g).turn(USER,t['id'],Turn(request_id=uuid.uuid4(),expected_version=0,text='어떤 안내가 맞을까?'))
    assert error.value.status==503
    assert [call[:2] for call in g.calls]==[('llm','Plan')]
    assert seeded.get_thread(USER,t['id'])['history']==[]
