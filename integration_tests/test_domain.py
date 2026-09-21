import asyncio,json,uuid
import pytest
from pydantic import ValidationError
from sqlalchemy import select,insert,update
from code_agent.models import Turn,ImportCommit,Approval,Revision,Plan,Wording,Explanation
from code_agent.store import DomainError,codes,drafts,state
from code_agent.agent import Agent
from code_agent.importer import parse_upload,ImportError
from code_agent.compare import compare_message
from code_agent.indexer import validate_vectors,text_for
from conftest import ADMIN,USER,OTHER,CSV,seed,ScriptedGateway

def req(text,version=0,**kw): return Turn(request_id=uuid.uuid4(),expected_version=version,text=text,**kw)
def approval(v=1,**kw): return Approval(expected_catalog_version=v,expected_draft_revision=1,code='AT-2000',reason='테스트 승인',duplicate_ack=True,external_registered=True,**kw)

@pytest.mark.asyncio
async def test_exact_lookup_no_llm(seeded,gateway):
    t=seeded.create_thread(USER);r=await Agent(seeded,gateway).turn(USER,t['id'],req('AT-1923이 뭐야?'))
    assert r['candidates'][0]['message']=='메뉴확인 30초 이후에 인증해주세요.'
    assert gateway.calls==[] and not r['ai_used']
@pytest.mark.asyncio
async def test_unknown_id_is_not_generated(seeded,gateway):
    t=seeded.create_thread(USER);r=await Agent(seeded,gateway).turn(USER,t['id'],req('AT-999999 알려줘'))
    assert r['missing_codes']==['AT-999999'] and not r['candidates'] and not gateway.calls
@pytest.mark.asyncio
async def test_retired_visible_on_exact_only(seeded,gateway):
    r=await Agent(seeded,gateway).turn(USER,seeded.create_thread(USER)['id'],req('AT-0999'))
    assert r['candidates'][0]['status']=='retired'
    assert all(x['status']=='active' for x in seeded.snapshot()[1])
@pytest.mark.asyncio
async def test_thread_is_private(seeded,gateway):
    t=seeded.create_thread(USER)
    with pytest.raises(DomainError) as e: await Agent(seeded,gateway).turn(OTHER,t['id'],req('AT-1923'))
    assert e.value.status==404 and seeded.list_threads(OTHER)==[]
@pytest.mark.asyncio
async def test_replay_exactly_once(seeded,gateway):
    a=Agent(seeded,gateway);t=seeded.create_thread(USER);q=req('AT-1923');r=await a.turn(USER,t['id'],q)
    assert await a.turn(USER,t['id'],q)==r and seeded.get_thread(USER,t['id'])['version']==1
@pytest.mark.asyncio
async def test_replay_different_input_rejected(seeded,gateway):
    a=Agent(seeded,gateway);t=seeded.create_thread(USER);q=req('AT-1923');await a.turn(USER,t['id'],q)
    with pytest.raises(DomainError): await a.turn(USER,t['id'],q.model_copy(update={'text':'AT-1924'}))
@pytest.mark.asyncio
async def test_stale_conversation_version(seeded,gateway):
    t=seeded.create_thread(USER);a=Agent(seeded,gateway);await a.turn(USER,t['id'],req('AT-1923'))
    with pytest.raises(DomainError): await a.turn(USER,t['id'],req('AT-1924'))
@pytest.mark.asyncio
async def test_conversation_search_compare_draft_approve(seeded,gateway):
    a=Agent(seeded,gateway);t=seeded.create_thread(USER)
    r=await a.turn(USER,t['id'],req('인증을 기다리는 알림 찾아줘'))
    assert r['version']==1 and r['candidates']
    r=await a.turn(USER,t['id'],req('두 번째 후보와 비교해줘',1,action='compare',proposed_message='30초 이내에 인증해주세요.'))
    assert r['version']==2 and r['comparisons']
    r=await a.turn(USER,t['id'],req('새로 작성해줘',2,action='draft',proposed_message='안내를 확인하고 진행해주세요.',menu='신규 메뉴',trigger='버튼 클릭'))
    d=r['draft'];assert d['status']=='draft' and d['registered_code'] is None
    assert seeded.get_code('AT-2000') is None
    out=seeded.approve(ADMIN,d['id'],approval());assert out['code']=='AT-2000'
    assert seeded.get_code('AT-2000')['message']=='안내를 확인하고 진행해주세요.'
    assert any(x['actor']==ADMIN.id and x['action']=='approve' for x in seeded.audit_log(ADMIN))
@pytest.mark.asyncio
async def test_missing_ordinal_rejected(seeded,gateway):
    with pytest.raises(DomainError): await Agent(seeded,gateway).turn(USER,seeded.create_thread(USER)['id'],req('두 번째 설명해줘'))
@pytest.mark.asyncio
async def test_stale_candidate_rejected(seeded,gateway):
    a=Agent(seeded,gateway);t=seeded.create_thread(USER);await a.turn(USER,t['id'],req('AT-1923'))
    seeded.revise_code(ADMIN,'AT-1923',Revision(expected_revision=1,expected_catalog_version=1,message='변경된 문구',reason='테스트'))
    with pytest.raises(DomainError): await a.turn(USER,t['id'],req('첫번째 설명',1))
@pytest.mark.asyncio
async def test_missing_comparison_requests_wording(seeded,gateway):
    a=Agent(seeded,gateway);r=await a.turn(USER,seeded.create_thread(USER)['id'],req('AT-1923 비교',action='compare'))
    assert '비교할 새 문구' in r['answer']
@pytest.mark.asyncio
async def test_llm_cannot_invent_existing_code(seeded,gateway):
    gateway.responses=[{'text':'AT-9999를 쓰세요','references':['AT-9999']}]
    t=seeded.create_thread(USER)
    with pytest.raises(DomainError): await Agent(seeded,gateway).turn(USER,t['id'],req('AT-1923 설명',action='explain'))
    assert seeded.get_thread(USER,t['id'])['version']==0
@pytest.mark.asyncio
async def test_generated_draft_does_not_register(seeded,gateway):
    a=Agent(seeded,gateway);t=seeded.create_thread(USER);q=req('30초 이후에 인증하도록 새로 작성',action='draft')
    r=await a.turn(USER,t['id'],q);assert r['draft']['payload']['message']=='30초 이후에 다시 인증해주세요.'
    assert len(seeded.snapshot(True)[1])==4
    again=await a.turn(USER,t['id'],q);assert again['draft']['id']==r['draft']['id']
    assert len(seeded.list_drafts(USER))==1
@pytest.mark.asyncio
async def test_model_failure_leaves_no_partial_thread_or_draft(seeded,gateway):
    gateway.responses=[DomainError('external failed',502)];t=seeded.create_thread(USER)
    with pytest.raises(DomainError): await Agent(seeded,gateway).turn(USER,t['id'],req('새 문구 만들기',action='draft'))
    assert seeded.get_thread(USER,t['id'])['history']==[] and seeded.list_drafts(USER)==[]
@pytest.mark.asyncio
async def test_live_catalog_change_before_commit_rejected(seeded,gateway):
    class Mutating(ScriptedGateway):
        async def search(self,q):
            old=await super().search(q)
            with self.store.engine.begin() as c:c.execute(update(state).values(version=2).where(state.c.id==1))
            return old
    t=seeded.create_thread(USER)
    with pytest.raises(DomainError): await Agent(seeded,Mutating(seeded)).turn(USER,t['id'],req('안내 찾아줘',action='search'))
    assert seeded.get_thread(USER,t['id'])['version']==0
@pytest.mark.parametrize('prompt,message',[
 ('30초 이후 인증 안내','30초 이내에 인증해주세요.'),('30초 이후 인증','60초 이후에 인증해주세요.'),
 ('인증 안내','AT-3000을 사용하세요.'),('{seconds}초 인증','30초 이후 인증해주세요.'),('인증 불가','인증해주세요.')])
def test_generated_constraints_guard(prompt,message):
    with pytest.raises(DomainError): Agent.validate_wording(prompt,message)

def test_import_preview_does_not_write(store):
    p=store.save_preview(ADMIN,parse_upload(CSV.encode(),'test.csv'));assert p['counts']['new']==4 and store.snapshot(True)[1]==[]
def test_import_preserves_original_whitespace(store):
    c='코드번호,등록문구\nAT-0001,"  안내\n{seconds} 확인  "\n';seed(store,c)
    assert store.get_code('at-0001')['message']=='  안내\n{seconds} 확인  ' and store.get_code('AT-0001')['code']=='AT-0001'
def test_import_conflict_not_overwritten(seeded):
    p=seeded.save_preview(ADMIN,parse_upload(CSV.replace('메뉴확인','수정된').encode(),'x.csv'))
    with pytest.raises(DomainError): seeded.apply_preview(ADMIN,p['id'],ImportCommit(expected_catalog_version=1))
    assert seeded.get_code('AT-1923')['revision']==1
    r=seeded.apply_preview(ADMIN,p['id'],ImportCommit(expected_catalog_version=1,updates=['AT-1923'],reason='승인된 원문 변경'))
    assert r['changed']==1 and seeded.get_code('AT-1923')['revision']==2
    assert seeded.apply_preview(ADMIN,p['id'],ImportCommit(expected_catalog_version=1))==r

def test_conflict_reason_required(seeded):
    p=seeded.save_preview(ADMIN,parse_upload(CSV.replace('메뉴확인','수정된').encode(),'x.csv'))
    with pytest.raises(DomainError):seeded.apply_preview(ADMIN,p['id'],ImportCommit(expected_catalog_version=1,updates=['AT-1923']))

def test_import_no_deletion_of_missing_codes(seeded):
    seed(seeded,'코드번호,등록문구\nAT-2000,새 문구\n');assert seeded.get_code('AT-1923')
def test_import_owner_isolation(seeded):
    p=seeded.save_preview(ADMIN,parse_upload(CSV.encode(),'x.csv'))
    with pytest.raises(DomainError): seeded.apply_preview(ActorAdmin2,p['id'],ImportCommit(expected_catalog_version=1))
from code_agent.models import Actor
ActorAdmin2=Actor(id=42,role='admin')
def test_non_admin_cannot_import(store):
    with pytest.raises(DomainError) as e:store.save_preview(USER,parse_upload(CSV.encode(),'x.csv'))
    assert e.value.status==403

def test_bad_upload_headers_and_duplicates(store):
    p=parse_upload('코드번호,등록문구\nAT-1,a\nAT-1,b'.encode(),'x.csv');assert p['errors']
    imp=store.save_preview(ADMIN,p)
    with pytest.raises(DomainError):store.apply_preview(ADMIN,imp['id'],ImportCommit(expected_catalog_version=0))

@pytest.mark.asyncio
async def test_nonadmin_cannot_approve(seeded,gateway):
    t=seeded.create_thread(USER);r=await Agent(seeded,gateway).turn(USER,t['id'],req('작성',action='draft',proposed_message='새 문구'))
    with pytest.raises(DomainError) as e:seeded.approve(USER,r['draft']['id'],approval())
    assert e.value.status==403
@pytest.mark.asyncio
async def test_approve_collision_rolls_back(seeded,gateway):
    t=seeded.create_thread(USER);r=await Agent(seeded,gateway).turn(USER,t['id'],req('작성',action='draft',proposed_message='새 문구'))
    body=approval().model_copy(update={'code':'AT-0999'})
    with pytest.raises(DomainError):seeded.approve(ADMIN,r['draft']['id'],body)
    assert seeded.status()['version']==1
@pytest.mark.asyncio
async def test_approval_requires_external_confirmation(seeded,gateway,monkeypatch):
    monkeypatch.setenv("CODE_CATALOG_AUTHORITY", "excel")
    t=seeded.create_thread(USER);r=await Agent(seeded,gateway).turn(USER,t['id'],req('작성',action='draft',proposed_message='새 문구'))
    with pytest.raises(DomainError):seeded.approve(ADMIN,r['draft']['id'],approval().model_copy(update={'external_registered':False}))
@pytest.mark.asyncio
async def test_recheck_draft_after_catalog_change(seeded,gateway):
    r=await Agent(seeded,gateway).turn(USER,seeded.create_thread(USER)['id'],req('작성',action='draft',proposed_message='새 문구'));ident=r['draft']['id']
    seed(seeded,'코드번호,등록문구\nAT-8888,나중에 들어온 문구\n')
    with pytest.raises(DomainError):seeded.approve(ADMIN,ident,approval())
    reviewed=seeded.review_draft(USER,ident,seeded.snapshot()[1],2)
    body=approval(v=2).model_copy(update={'expected_draft_revision':reviewed['revision']});seeded.approve(ADMIN,ident,body)
    assert seeded.get_code('AT-2000')

def test_rule_after_within(seeded):
    r=compare_message('30초 이내에 인증해주세요.',seeded.get_code('AT-1923'))
    assert r['verdict']=='different_conditions'
def test_standalone_invalid_code_returns_domain_error(seeded):
    with pytest.raises(DomainError):seeded.get_code('../../etc/passwd')
@pytest.mark.parametrize('vectors,count',[([],1),([[0.0]*10],1),([[float('nan')]*1536],1)])
def test_invalid_embeddings_never_publish(vectors,count):
    with pytest.raises(ValueError):validate_vectors(vectors,count)
def test_valid_embedding_shape():validate_vectors([[0.0]*1536],1)

@pytest.mark.asyncio
async def test_retry_count_not_mistaken_for_candidate_ordinal(seeded,gateway):
    t=seeded.create_thread(USER)
    r=await Agent(seeded,gateway).turn(USER,t['id'],Turn(request_id=uuid.uuid4(),expected_version=0,text='인증 3번 실패할 때 알림 찾아줘'))
    assert r['candidates'] and r['action']=='search'

@pytest.mark.asyncio
async def test_planner_cannot_invent_user_proposal(seeded,gateway):
    t=seeded.create_thread(USER)
    gateway.responses=[{'action':'compare','query':'인증','proposed_message':'사용자가 작성하지 않은 문구'}]
    with pytest.raises(DomainError):await Agent(seeded,gateway).turn(USER,t['id'],Turn(request_id=uuid.uuid4(),expected_version=0,text='인증 관련 문구 비교해줘'))
    assert seeded.get_thread(USER,t['id'])['version']==0

@pytest.mark.asyncio
async def test_user_quoted_draft_is_preserved(seeded,gateway):
    t=seeded.create_thread(USER);raw='메뉴를 확인하고 다시 진행해주세요.'
    gateway.responses=[{'action':'draft','query':'메뉴 확인','proposed_message':raw}]
    r=await Agent(seeded,gateway).turn(USER,t['id'],Turn(request_id=uuid.uuid4(),expected_version=0,text='"'+raw+'"라는 문구로 작성해줘'))
    assert r['draft']['payload']['message']==raw
    assert [x[1] for x in gateway.calls if x[0]=='llm']==['Plan']

@pytest.mark.asyncio
async def test_explanation_keeps_original_search_candidate_order(seeded,gateway):
    a=Agent(seeded,gateway);t=seeded.create_thread(USER)
    first=await a.turn(USER,t['id'],Turn(request_id=uuid.uuid4(),expected_version=0,text='인증 찾아줘'))
    second=await a.turn(USER,t['id'],Turn(request_id=uuid.uuid4(),expected_version=1,text='두 번째 설명해줘',action='explain'))
    third=await a.turn(USER,t['id'],Turn(request_id=uuid.uuid4(),expected_version=2,text='3번째 후보는 어때',action='explain'))
    assert second['candidates'][0]['code']==first['candidates'][1]['code']
    assert third['candidates'][0]['code']==first['candidates'][2]['code']
    assert seeded.get_thread(USER,t['id'])['history'][-1]['selected_code']==third['candidates'][0]['code']
