import io,json,uuid,zipfile
from pathlib import Path
import pytest
from fastapi import FastAPI,Header,HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from code_agent.api import create_router
from code_agent.store import DomainError
from conftest import ADMIN,USER,OTHER,ScriptedGateway,CSV


def app_for(store,gateway=None,enqueue=lambda:None,sample_gateway=None):
    class TestQuota:
        async def check(self,actor_id,operation): pass
    async def identity(authorization:str|None=Header(None)):
        values={'Bearer test-admin':ADMIN,'Bearer test-user':USER,'Bearer test-other':OTHER}
        if authorization not in values: raise HTTPException(401,'로그인 필요')
        return values[authorization]
    app=FastAPI()
    app.include_router(create_router(store,gateway or ScriptedGateway(store),identity,enqueue,quota=TestQuota(),sample_gateway=sample_gateway))
    @app.exception_handler(DomainError)
    async def handler(request,exc):return JSONResponse({'detail':exc.message},status_code=exc.status)
    return app

@pytest.fixture
def client(seeded):
    with TestClient(app_for(seeded)) as c:yield c

def headers(role='user'):return {'Authorization':'Bearer test-'+role}
def thread(client,role='user'):return client.post('/api/code-catalog/threads',headers=headers(role)).json()
def body(text='AT-1923',**extra):return dict(request_id=str(uuid.uuid4()),expected_version=0,text=text,**extra)

@pytest.mark.parametrize('path',['/status','/codes','/threads','/drafts','/audit','/export'])
def test_auth_required(client,path):assert client.get('/api/code-catalog'+path).status_code==401

def test_exact_api_returns_original(client):
    assert client.get('/api/code-catalog/codes/AT-1923',headers=headers()).json()['message']=='메뉴확인 30초 이후에 인증해주세요.'
def test_code_unknown_404(client):assert client.get('/api/code-catalog/codes/AT-7777',headers=headers()).status_code==404
def test_bad_code_422(client):assert client.get('/api/code-catalog/codes/nonsense',headers=headers()).status_code==422

def test_real_api_transaction_conversation(client):
    t=thread(client);payload=body();r=client.post('/api/code-catalog/threads/'+t['id']+'/turn',headers=headers(),json=payload)
    assert r.status_code==200 and r.json()['candidates'][0]['code']=='AT-1923'
    assert client.get('/api/code-catalog/threads/'+t['id'],headers=headers()).json()['version']==1
    assert client.get('/api/code-catalog/threads/'+t['id'],headers=headers('other')).status_code==404
    assert client.post('/api/code-catalog/threads/'+t['id']+'/turn',headers=headers(),json=payload).json()==r.json()

def test_request_cannot_spoof_actor_or_action(client):
    t=thread(client)
    p=body(actor_id=1);assert client.post('/api/code-catalog/threads/'+t['id']+'/turn',headers=headers(),json=p).status_code==422
    p=body(action='approve');assert client.post('/api/code-catalog/threads/'+t['id']+'/turn',headers=headers(),json=p).status_code==422

def test_empty_request_validation(client):
    t=thread(client);assert client.post('/api/code-catalog/threads/'+t['id']+'/turn',headers=headers(),json=body('  ')).status_code==422

def test_user_cannot_upload(client):
    r=client.post('/api/code-catalog/imports/preview',headers=headers(),files={'file':('x.csv',CSV.encode(),'text/csv')});assert r.status_code==403

def test_real_import_preview_commit_api(client):
    r=client.post('/api/code-catalog/imports/preview',headers=headers('admin'),files={'file':('x.csv','코드번호,등록문구\nAT-2000,추가 문구\n'.encode(),'text/csv')})
    assert r.status_code==200;r=r.json()
    assert client.get('/api/code-catalog/codes/AT-2000',headers=headers()).status_code==404
    response=client.post('/api/code-catalog/imports/'+r['id']+'/commit',headers=headers('admin'),json={'expected_catalog_version':1})
    assert response.status_code==200 and response.json()['changed']==1
    assert client.get('/api/code-catalog/codes/AT-2000',headers=headers()).status_code==200

@pytest.mark.parametrize('mapping',['[]','{"Sheet1":[]}','not json'])
def test_bad_mapping_422(client,mapping):
    r=client.post('/api/code-catalog/imports/preview',headers=headers('admin'),data={'mapping':mapping},files={'file':('x.csv',CSV.encode(),'text/csv')})
    assert r.status_code==422

def test_malformed_xlsx_422(client):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('xl/workbook.xml','<broken')
    r=client.post('/api/code-catalog/imports/preview',headers=headers('admin'),files={'file':('broken.xlsx',b.getvalue(),'application/octet-stream')})
    assert r.status_code==422

def test_template_real_xlsx_parser(client):
    r=Path(__file__).resolve().parents[1]/'catalog_legacy/examples/code_catalog_template.xlsx'
    response=client.post('/api/code-catalog/imports/preview',headers=headers('admin'),files={'file':('template.xlsx',r.read_bytes(),'application/octet-stream')})
    assert response.status_code==200 and response.json()['sheets']
    assert response.json()['errors'] # intentionally blank template, not fake live data

def test_large_upload_blocked(client):
    r=client.post('/api/code-catalog/imports/preview',headers=headers('admin'),files={'file':('large.csv',b'x'*(8*1024*1024+1),'text/csv')});assert r.status_code==413

def test_user_admin_endpoints_denied(client):
    assert client.post('/api/code-catalog/index',headers=headers(),json={}).status_code==403
    assert client.get('/api/code-catalog/audit',headers=headers()).status_code==403

def test_queue_failure_is_not_fake_success(seeded):
    def fails():raise RuntimeError('test only')
    with TestClient(app_for(seeded,enqueue=fails)) as c:assert c.post('/api/code-catalog/index',headers=headers('admin'),json={}).status_code==503

def test_export_format(client):
    r=client.get('/api/code-catalog/export',headers=headers());assert r.status_code==200
    assert '메뉴확인 30초 이후에 인증해주세요.' in r.text and 'code-catalog.csv' in r.headers['content-disposition']

def test_no_user_data_in_other_user_draft_list(client):
    t=thread(client);p=body('신규 초안',action='draft',proposed_message='추가 안내입니다.')
    assert client.post('/api/code-catalog/threads/'+t['id']+'/turn',headers=headers(),json=p).status_code==200
    assert len(client.get('/api/code-catalog/drafts',headers=headers()).json())==1
    assert client.get('/api/code-catalog/drafts',headers=headers('other')).json()==[]
    assert len(client.get('/api/code-catalog/drafts',headers=headers('admin')).json())==1

def test_catalog_filters_before_paging_and_preserves_default(client):
    base='/api/code-catalog/codes'
    assert client.get(base,headers=headers()).json()['total']==3
    result=client.get(base,params={'status':'all','q':'at-','offset':1,'limit':2},headers=headers()).json()
    assert result['total']==4 and [x['code'] for x in result['items']]==['AT-0999','AT-1923']
    result=client.get(base,params={'status':'retired','q':'사용하지'},headers=headers()).json()
    assert result['total']==1 and result['items'][0]['code']=='AT-0999'
    assert client.get(base,params={'status':'unknown'},headers=headers()).status_code==422
    assert client.get(base,params={'q':'없는문구'},headers=headers()).json()['total']==0

def test_catalog_original_columns_preserved_and_approval_required(client):
    def preview_csv(value):
        r=client.post('/api/code-catalog/imports/preview',headers=headers('admin'),files={'file':('original.csv',value.encode(),'text/csv')})
        assert r.status_code==200
        return r.json()
    p=preview_csv('메시지코드,업무구분,타입,타이틀,컨텐츠,용도,영문타이틀,영문컨텐츠\nAT-8000,인증,팝업, 원문 제목 , 원문 내용 ,실패 안내,Title,Content\n')
    assert p['counts']['new']==1
    r=client.post('/api/code-catalog/imports/'+p['id']+'/commit',headers=headers('admin'),json={'expected_catalog_version':p['catalog_version']})
    assert r.status_code==200
    r=client.get('/api/code-catalog/codes',params={'q':'원문 제목','status':'all'},headers=headers()).json()
    assert r['total']==1 and r['items'][0]['message']==' 원문 내용 '
    assert r['items'][0]['source']['catalog_fields']['title']==' 원문 제목 '
    p=preview_csv('메시지코드,타이틀,컨텐츠\nAT-8000,변경 제목, 원문 내용 \n')
    assert p['counts']['conflict']==1
    assert p['records'][0]['source']['catalog_fields']['business']=='인증'
    r=client.post('/api/code-catalog/imports/'+p['id']+'/commit',headers=headers('admin'),json={'expected_catalog_version':p['catalog_version']})
    assert r.status_code==409
    text=client.get('/api/code-catalog/export',headers=headers()).text
    assert '영문컨텐츠' in text and ' 원문 제목 ' in text and 'Title,Content' in text

@pytest.mark.parametrize('endpoint,payload',[('/compare',{'message':'test'}),('/review',{'text':'AT-1923'})])
def test_inspection_requires_original_identity(client,endpoint,payload):
    assert client.post('/api/code-catalog'+endpoint,json=payload).status_code==401

def test_compare_rules_returns_original_and_condition_differences(client):
    result=client.post('/api/code-catalog/compare',headers=headers(),json={'message':'30초 이내에 인증해주세요.'}).json()
    assert result['mode']=='catalog_rules'
    comparison=next(x for x in result['comparisons'] if x['code']=='AT-1923')
    assert comparison['verdict']=='different_conditions'
    assert next(x for x in result['candidates'] if x['code']=='AT-1923')['message']=='메뉴확인 30초 이후에 인증해주세요.'

def test_review_lines_missing_retired_and_original(client):
    result=client.post('/api/code-catalog/review',headers=headers(),json={'text':'AT-1923\n\nAT-1923: 30초 이내에 인증해주세요.\nAT-9999\nAT-0999'}).json()
    assert [item['line'] for item in result['items']]==[1,3,4,5]
    assert result['items'][0]['comparisons']==[]
    assert result['items'][1]['comparisons'][0]['verdict']=='different_conditions'
    assert result['items'][2]['missing_codes']==['AT-9999']
    assert result['items'][3]['candidates'][0]['status']=='retired'

@pytest.mark.parametrize('text',[' ','\n'.join(['AT-1923']*31),'a'*4001])
def test_review_bounds(client,text):
    assert client.post('/api/code-catalog/review',headers=headers(),json={'text':text}).status_code==422

def test_semantic_failure_is_not_rule_fallback(seeded):
    from code_agent.store import DomainError
    gateway=ScriptedGateway(seeded);gateway.search_error=DomainError('인덱스 미준비',409)
    with TestClient(app_for(seeded,gateway)) as c:
        r=c.post('/api/code-catalog/compare',headers=headers(),json={'message':'인증 문구','mode':'semantic'})
        assert r.status_code==409 and '인덱스' in r.json()['detail']

def test_github_samples_are_separate_and_readonly(client):
    before=client.get('/api/code-catalog/codes',params={'status':'all'},headers=headers()).json()
    samples=client.get('/api/code-catalog/codes',params={'namespace':'demo','status':'all'},headers=headers()).json()
    assert samples['total']==300 and all(r['source']['synthetic'] for r in samples['items'])
    result=client.post('/api/code-catalog/review',headers=headers(),json={'namespace':'demo','text':'EX-0201\nEX-0901\nEX-9999'}).json()
    assert result['items'][0]['candidates'][0]['message']=='이미 가입된 휴대폰 번호입니다. 로그인해주세요.'
    assert result['items'][1]['candidates'][0]['status']=='retired'
    assert result['items'][2]['missing_codes']==['EX-9999']
    assert client.get('/api/code-catalog/codes/EX-0201',headers=headers()).status_code==404
    assert client.get('/api/code-catalog/codes',params={'status':'all'},headers=headers()).json()==before


def test_json_samples_export_and_isolation(client):
    from code_agent.models import canonical_code
    response=client.get('/api/code-catalog/export.json?namespace=demo',headers=headers())
    assert response.status_code==200 and 'application/json' in response.headers['content-type']
    data=response.json();items=data['items']
    assert data['synthetic'] is True and data['total']==len(items)==300
    assert len({r['message_code'] for r in items})==300
    assert all(canonical_code(r['message_code'])==r['message_code'] and r['title'].strip() and r['_meta']['source']['synthetic'] for r in items)
    assert sum(r['_meta']['status']=='retired' for r in items)==21
    generated=[r for r in items if r['_meta']['source']['kind']=='synthetic_json']
    assert len(generated)==284 and len({r['_meta']['source']['catalog_fields']['business'] for r in generated})==21
    assert client.get('/api/code-catalog/export.json').status_code==401
    real=client.get('/api/code-catalog/export.json',headers=headers()).json()
    assert real['total']==4 and real['synthetic'] is False
    last=client.get('/api/code-catalog/codes?namespace=demo&status=all&offset=270&limit=30',headers=headers()).json()
    assert last['total']==300 and len(last['items'])==30
