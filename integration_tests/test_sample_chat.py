from fastapi.testclient import TestClient
from sqlalchemy import select
from code_agent.store import Store,SampleStore,threads,thread_scopes
from conftest import ADMIN,USER,OTHER,ScriptedGateway
from test_api import app_for,headers,body


def test_sample_conversation_scope_owner_and_replay(seeded):
    sample=SampleStore(seeded)
    gateway=ScriptedGateway(sample)
    before=seeded.snapshot(True)
    with TestClient(app_for(seeded,sample_gateway=gateway)) as client:
        t=client.post('/api/code-catalog/threads?namespace=demo',headers=headers(),json={}).json()
        assert t['namespace']=='demo'
        url='/api/code-catalog/threads/'+t['id']+'/turn?namespace=demo'
        request=body('AT-1923 문구 알려줘')
        r=client.post(url,headers=headers(),json=request)
        assert r.status_code==200,r.text
        result=r.json();assert result['namespace']=='demo' and result['ai_used'] is False
        assert result['candidates'][0]['source']['synthetic'] is True
        assert client.post(url,headers=headers(),json=request).json()==result
        assert client.get('/api/code-catalog/threads',headers=headers()).json()==[]
        assert len(client.get('/api/code-catalog/threads?namespace=demo',headers=headers()).json())==1
        assert client.get('/api/code-catalog/threads/'+t['id'],headers=headers()).status_code==404
        assert client.get('/api/code-catalog/threads/'+t['id']+'?namespace=demo',headers=headers('other')).status_code==404
        restored=client.get('/api/code-catalog/threads/'+t['id']+'?namespace=demo',headers=headers()).json()
        assert restored['history'][-1]['ai_used'] is False
        r=client.post(url,headers=headers(),json=dict(body('첫 번째 후보는 어떤 상황이야?'),expected_version=1))
        assert r.status_code==200 and r.json()['candidates'][0]['code']=='AT-1923'
        r=client.post(url,headers=headers(),json=dict(body('새 문구 작성',action='draft',proposed_message='합성 초안'),expected_version=2))
        assert r.status_code==422
    assert seeded.snapshot(True)==before
    assert seeded.list_drafts(ADMIN)==[]
    assert sample.get_thread(USER,t['id'])['version']==2


def test_sample_search_uses_injected_gateway_and_never_production(seeded):
    sample=SampleStore(seeded);gateway=ScriptedGateway(sample)
    with TestClient(app_for(seeded,sample_gateway=gateway)) as client:
        t=client.post('/api/code-catalog/threads?namespace=demo',headers=headers(),json={}).json()
        r=client.post('/api/code-catalog/threads/'+t['id']+'/turn?namespace=demo',headers=headers(),json=body('인증 전에 30초 기다리라는 알림 있어?'))
        assert r.status_code==200,r.text
        assert any(x[0]=='search' for x in gateway.calls)
        assert any(x['code']=='AT-1923' for x in r.json()['candidates'])
        assert all(x['source']['synthetic'] for x in r.json()['candidates'])
        real=client.post('/api/code-catalog/threads',headers=headers(),json={}).json()
        r=client.post('/api/code-catalog/threads/'+real['id']+'/turn',headers=headers(),json=body('EX-0201'))
        assert r.json()['missing_codes']==['EX-0201']


def test_legacy_thread_without_scope_remains_production(seeded):
    from sqlalchemy import delete
    t=seeded.create_thread(USER)
    with seeded.engine.begin() as c:c.execute(delete(thread_scopes).where(thread_scopes.c.thread_id==t['id']))
    assert seeded.get_thread(USER,t['id'])['namespace']=='production'
    assert seeded.list_threads(USER)[0]['id']==t['id']
    assert SampleStore(seeded).list_threads(USER)==[]

def test_waiting_direction_prioritizes_after_without_inventing_candidates():
    from code_agent.compare import prioritize_waiting
    rows=[{'code':'EX-1','message':'30초 이내에 인증해주세요.'},{'code':'EX-2','message':'30초 이후에 다시 인증해주세요.'},{'code':'EX-3','message':'메뉴 확인 30초 이후에 인증해주세요.'}]
    assert [r['code'] for r in prioritize_waiting('인증 전에 30초 기다리라는 알림 있어?',rows)]==['EX-3','EX-2','EX-1']
    assert prioritize_waiting('30초 이내 인증',rows)==rows

def test_json_changes_do_not_overwrite_imported_database(seeded,monkeypatch):
    sample=SampleStore(seeded)
    before=seeded.status();old=sample.status();records,checksum=sample.source()
    monkeypatch.setattr(sample,'source',lambda:(records,'f'*64))
    sample.initialize_catalog()
    current=sample.status()
    assert current==old
    assert seeded.status()==before
