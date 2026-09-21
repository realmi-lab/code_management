from concurrent.futures import ThreadPoolExecutor
from .conftest import add


def draft(client,message='저장하지 않고 나가시겠습니까?',ns='live',**kwargs):
    r=client.post('/api/drafts',json={'message':message,'namespace':ns,**kwargs})
    assert r.status_code==200,r.text
    return r.json()['draft']


def approval(client,d,code=None,prefix=None,ack=False,version=None):
    version=client.get('/api/meta?namespace='+d['namespace']).json()['version'] if version is None else version
    return client.post('/api/drafts/'+d['id']+'/approve',json={'namespace':d['namespace'],'expected_revision':d['revision'],
      'expected_catalog_version':version,'code':code,'prefix':prefix,'reason':'기획 검토 완료','duplicate_ack':ack})


def test_draft_has_no_code_and_does_not_register(client):
    d=draft(client)
    assert d['registered_code'] is None and d['state']=='draft'
    assert client.get('/api/meta').json()['counts']['total']==0


def test_excel_authority_prevents_number_issuance(client):
    d=draft(client)
    assert approval(client,d,'AT-9999').status_code==409
    assert client.get('/api/codes').json()['total']==0


def test_handoff_is_not_registration(client):
    d=draft(client)
    r=client.post('/api/drafts/'+d['id']+'/handoff?expected_revision=1')
    assert r.json()['state']=='pending_external'
    assert r.json()['registered_code'] is None
    assert client.get('/api/meta').json()['counts']['total']==0
    assert client.post('/api/drafts/'+d['id']+'/handoff?expected_revision=1').status_code==409


def test_system_registration_is_idempotent(system_client):
    d=draft(system_client)
    r=approval(system_client,d,'AT-9999')
    assert r.status_code==200,r.text
    assert r.json()['code']['message']==d['message']
    assert approval(system_client,d,'AT-9999').json()['idempotent'] is True
    assert system_client.get('/api/codes').json()['total']==1


def test_code_conflict_returns_409(system_client):
    add(system_client)
    d=draft(system_client,'네트워크가 끊어졌습니다.')
    assert approval(system_client,d,'AT-1923').status_code==409


def test_duplicate_requires_ack(system_client):
    add(system_client)
    d=draft(system_client,'메뉴확인 30초 이후에 인증해주세요.')
    assert approval(system_client,d,'AT-5555').status_code==409
    assert approval(system_client,d,'AT-5555',ack=True).status_code==200


def test_auto_numbering_requires_explicit_rule(system_client):
    d=draft(system_client)
    assert approval(system_client,d,prefix='UNKNOWN').status_code==422
    assert approval(system_client,d,prefix='AT').json()['code']['code']=='AT-2000'


def test_stale_catalog_recheck(system_client):
    d=draft(system_client)
    old=system_client.get('/api/meta').json()['version']
    add(system_client)
    assert approval(system_client,d,'AT-9090',version=old).status_code==409


def test_revision_requires_current_source(system_client):
    add(system_client)
    d1=draft(system_client,'메뉴 확인 30초 이후에 인증해주세요.',kind='revision',target_code='AT-1923')
    d2=draft(system_client,'메뉴 확인 40초 이후에 인증해주세요.',kind='revision',target_code='AT-1923')
    r=approval(system_client,d1)
    assert r.status_code==200,r.text
    assert r.json()['code']['revision']==2
    assert approval(system_client,d2).status_code==409


def test_retirement_revision_checked(system_client):
    add(system_client)
    payload={'expected_revision':1,'status':'retired','reason':'폐기 확인'}
    assert system_client.patch('/api/codes/AT-1923/status',json=payload).status_code==200
    assert system_client.patch('/api/codes/AT-1923/status',json=payload).status_code==409
    assert system_client.get('/api/codes/AT-1923/copy').status_code==409


def test_live_excel_status_not_changed(client):
    add(client)
    assert client.patch('/api/codes/AT-1923/status',json={'expected_revision':1,'status':'retired','reason':'확인'}).status_code==409


def test_parallel_registration_no_duplicate_numbers(system_client):
    d1=draft(system_client,'첫 번째 알림입니다.');d2=draft(system_client,'두 번째 알림입니다.')
    version=system_client.get('/api/meta').json()['version']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda d:approval(system_client,d,prefix='AT',ack=True,version=version),[d1,d2]))
    assert sorted(r.status_code for r in results)==[200,409]
    loser=[d1,d2][[r.status_code for r in results].index(409)]
    retry=approval(system_client,loser,prefix='AT',ack=True)
    assert retry.status_code==200
    codes=system_client.get('/api/codes').json()['items']
    assert {c['code'] for c in codes}=={'AT-2000','AT-2001'}


def test_audit_contains_old_new(system_client):
    add(system_client)
    d=draft(system_client,'바뀐 문구',kind='revision',target_code='AT-1923')
    assert approval(system_client,d).status_code==200
    logs=system_client.get('/api/audit').json()['items']
    item=next(x for x in logs if x['action']=='code.revised')
    assert '30초' in item['before_json'] and '바뀐 문구' in item['after_json']


def test_demo_approval_is_separate_from_live_authority(client):
    d=draft(client,'전혀 새로운 예시 저장 안내',ns='demo')
    assert approval(client,d,prefix='EX',ack=True).status_code==200
    assert client.get('/api/meta').json()['counts']['total']==0


def test_blank_or_invalid_drafts(client):
    assert client.post('/api/drafts',json={'message':'  '}).status_code==422
    assert client.post('/api/drafts',json={'message':'내용','kind':'revision'}).status_code==422
    assert client.post('/api/drafts',json={'message':'내용','target_code':'AT-1923'}).status_code==422
