import asyncio
import json
import pytest
from catalog.ai import AI, AIError
from catalog.config import Settings
from .conftest import add, upload, commit

def mock_search(client,monkeypatch,queries=None):
    ai=client.app.state.ai
    ai.settings.ai_enabled=True
    ai.settings.ai_chat_model='test-model'
    seen=[]
    async def request(endpoint,payload):
        seen.append(payload)
        return {'choices':[{'message':{'content':json.dumps({'queries':queries or ['휴대폰 번호 중복 가입']})}}]}
    monkeypatch.setattr(ai,'request',request)
    return seen

def test_ai_search_queries_only_catalog_originals_and_cache(client,monkeypatch):
    original='  이미 가입된 전화번호입니다.\n확인해 주세요.  '
    add(client,code='AT-100',message=original)
    calls=mock_search(client,monkeypatch)
    req={'query':'예전에 쓰던 번호로 다시 들어오려는 사람 안내','use_ai':True}
    result=client.post('/api/search',json=req).json()
    assert result['mode']=='ai_query' and result['results'][0]['message']==original
    assert result['results'][0]['code']=='AT-100'
    assert len(calls)==1 and original not in json.dumps(calls,ensure_ascii=False)
    second=client.post('/api/search',json=req).json()
    assert second['ai_query_cached'] and len(calls)==1
    add(client,code='AT-101',message='휴대폰 번호 중복 가입을 확인해 주세요.')
    refreshed=client.post('/api/search',json=req).json()
    assert refreshed['scope']['catalog_count']==2 and len(calls)==1

def test_ai_search_exact_missing_empty_and_opt_out_never_call(client,monkeypatch):
    calls=mock_search(client,monkeypatch)
    assert client.post('/api/search',json={'query':'가입','use_ai':True}).json()['results']==[]
    add(client)
    for query,use_ai in [('AT-1923',True),('AT-9999',True),('가입',False)]:
        assert client.post('/api/search',json={'query':query,'use_ai':use_ai}).status_code==200
    assert calls==[]

@pytest.mark.parametrize('queries',[
    ['AT-9999'],['인증 999초 후'],['a','b','c','d'],[''],[123],
])
def test_bad_ai_queries_fall_back(client,monkeypatch,queries):
    add(client)
    mock_search(client,monkeypatch,queries)
    r=client.post('/api/search',json={'query':'30초 인증','use_ai':True}).json()
    assert r['mode']=='basic' and r['results']
    assert r['notice'] and not r.get('ai_queries')

def test_ai_unavailable_falls_back(client,monkeypatch):
    add(client)
    ai=client.app.state.ai
    async def fail(q):raise AIError('연결 실패')
    monkeypatch.setattr(ai,'search_queries',fail)
    r=client.post('/api/search',json={'query':'인증','use_ai':True}).json()
    assert r['mode']=='basic' and r['notice']=='연결 실패' and r['results']

def test_ai_search_refreshes_rows_after_model_wait(client,monkeypatch):
    add(client)
    async def expand(query):
        db=client.app.state.db
        with db.connect(write=True) as con:
            con.execute("UPDATE codes SET status='retired' WHERE namespace='live'")
            db.bump(con,'live')
        return ['인증'],False
    monkeypatch.setattr(client.app.state.ai,'search_queries',expand)
    r=client.post('/api/search',json={'query':'대기','use_ai':True}).json()
    assert r['results']==[]

def draft(client,message='새 문구',**kwargs):
    r=client.post('/api/drafts',json={'message':message,**kwargs})
    assert r.status_code==200,r.text
    return r.json()['draft']

def handoff(client,d):
    r=client.post(f"/api/drafts/{d['id']}/handoff?expected_revision={d['revision']}")
    assert r.status_code==200,r.text
    return r.json()

def status(client,d):
    return client.get(f"/api/drafts/{d['id']}/review").json()['draft']

def imported(client,d,code='AT-8000',marker=False,message=None):
    p=upload(client,[['코드번호','등록문구','사용메뉴','노출조건','비고'],
        [code,message if message is not None else d['message'],d['menu'],d['trigger'],'[draft:'+d['id']+']' if marker else '']]).json()
    result=commit(client,p)
    assert result.status_code==200,result.text
    return result.json()

def test_edit_pending_draft_reverts_and_guards_revision(client):
    d=handoff(client,draft(client))
    body={'expected_revision':d['revision'],'message':'수정 원문','reason':'조건 검토','menu':'가입'}
    r=client.patch('/api/drafts/'+d['id'],json=body)
    assert r.status_code==200 and r.json()['state']=='draft'
    assert r.json()['revision']==d['revision']+1
    assert client.patch('/api/drafts/'+d['id'],json=body).status_code==409
    audit=client.get('/api/audit').json()['items']
    assert any(x['action']=='draft.updated' for x in audit)

def test_import_marker_exact_match_auto_completes(client):
    d=handoff(client,draft(client,message=' 원문\n그대로 ',menu='가입',trigger='조건'))
    result=imported(client,d,marker=True)
    assert result['linked_drafts']==[{'draft_id':d['id'],'code':'AT-8000'}]
    assert status(client,d)['state']=='registered'
    body={'expected_revision':status(client,d)['revision'],'message':'변경','reason':'수정'}
    assert client.patch('/api/drafts/'+d['id'],json=body).status_code==409

def test_import_no_marker_or_difference_does_not_auto_link(client):
    d=handoff(client,draft(client))
    assert imported(client,d)['linked_drafts']==[]
    assert status(client,d)['state']=='pending_external'
    assert imported(client,d,code='AT-8001',marker=True,message='다른 문구')['linked_drafts']==[]
    assert status(client,d)['state']=='pending_external'

def test_ambiguous_marker_does_not_auto_link(client):
    d=handoff(client,draft(client))
    p=upload(client,[['코드번호','등록문구','비고'],
                    ['AT-8000',d['message'],'[draft:'+d['id']+']'],
                    ['AT-8001',d['message'],'[draft:'+d['id']+']']]).json()
    assert commit(client,p).json()['linked_drafts']==[]
    assert status(client,d)['state']=='pending_external'

def test_manual_external_link_has_stale_and_difference_guards(client):
    d=handoff(client,draft(client))
    imported(client,d,message='담당자 확정 문구')
    v=client.get('/api/meta').json()['version']
    body={'expected_revision':d['revision'],'expected_catalog_version':v,'code':'AT-8000','reason':'확정 내용 확인'}
    url='/api/drafts/'+d['id']+'/link-external'
    assert client.post(url,json={**body,'expected_catalog_version':v-1}).status_code==409
    assert client.post(url,json=body).status_code==409
    body['differences_ack']=True
    assert client.post(url,json=body).status_code==200
    assert client.post(url,json=body).json()['idempotent']
    assert client.get('/api/codes/AT-8000').json()['message']=='담당자 확정 문구'
    assert client.post(url,json={**body,'code':'AT-8001'}).status_code==409

def test_external_matching_and_export_marker(client):
    d=handoff(client,draft(client))
    imported(client,d)
    r=client.get('/api/drafts/'+d['id']+'/external-matches').json()
    assert r['items'][0]['code']=='AT-8000' and r['items'][0]['differences']==[]
    assert '[draft:'+d['id']+']' in client.get('/api/export/drafts.csv').text

def test_external_link_namespace_and_state_boundaries(client):
    d=draft(client);imported(client,d)
    body={'expected_revision':d['revision'],'expected_catalog_version':client.get('/api/meta').json()['version'],'code':'AT-8000','reason':'확인'}
    url='/api/drafts/'+d['id']+'/link-external'
    assert client.post(url,json=body).status_code==409
    assert client.post(url,json={**body,'namespace':'demo'}).status_code==404

def test_revision_draft_cannot_link_different_code(client):
    add(client)
    d=handoff(client,draft(client,kind='revision',target_code='AT-1923'))
    imported(client,d,marker=True)
    assert status(client,d)['state']=='pending_external'
    body={'expected_revision':d['revision'],'expected_catalog_version':client.get('/api/meta').json()['version'],'code':'AT-8000','reason':'확인'}
    assert client.post('/api/drafts/'+d['id']+'/link-external',json=body).status_code==409
