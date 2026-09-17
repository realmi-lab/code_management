import json
import pytest
from .conftest import add,upload,commit,xlsx_fixture,csv_file


def test_live_empty_and_demo_separate(client):
    assert client.get('/api/meta').json()['counts']['total']==0
    assert client.get('/api/meta?namespace=demo').json()['counts']['total']==16
    assert client.get('/api/codes/AT-1923').status_code==404
    assert client.get('/api/codes/AT-1923?namespace=demo').status_code==200


def test_exact_lookup_preserves_original(client):
    raw='  메뉴확인 30초 이후에 인증해주세요.\n{seconds}초  '
    add(client,message=raw)
    result=client.post('/api/search',json={'query':'at-1923 뭐야?'}).json()
    assert result['mode']=='exact'
    assert result['results'][0]['message']==raw
    assert raw in client.get('/api/codes/AT-1923/copy').json()['text']


def test_unknown_code_not_substituted(client):
    add(client)
    result=client.post('/api/search',json={'query':'AT-999999'}).json()
    assert result['results']==[] and result['missing_codes']==['AT-999999']


def test_multiple_exact_codes(client):
    add(client)
    r=client.post('/api/search',json={'query':'AT-1923과 AT-888은 뭐야'}).json()
    assert len(r['results'])==1 and r['missing_codes']==['AT-888']


def test_situation_search(client):
    r=client.post('/api/search',json={'query':'인증 전에 30초 기다리라는 알림','namespace':'demo'}).json()
    assert r['results'][0]['code']=='AT-1923'
    assert r['mode']=='basic'


def test_after_within_warn(client):
    add(client)
    r=client.post('/api/compare',json={'query':'unused','message':'메뉴확인 30초 이내에 인증해주세요.'}).json()
    match=r['results'][0]['match']
    assert match['verdict']=='different_conditions'
    assert any('방향' in d for d in match['differences'])


def test_same_text_without_context_not_confirmed(client):
    message='메뉴확인 30초 이후에 인증해주세요.'
    add(client,message=message)
    r=client.post('/api/compare',json={'query':message,'message':message}).json()
    assert r['results'][0]['match']['verdict']=='same_wording'


def test_exact_context_reuse_candidate(client):
    msg='메뉴확인 30초 이후에 인증해주세요.'
    add(client,message=msg,menu='인증',trigger='버튼 클릭')
    r=client.post('/api/compare',json={'query':msg,'message':msg,'menu':'인증','trigger':'버튼 클릭'}).json()
    assert r['results'][0]['match']['verdict']=='reuse_candidate'


def test_retired_excluded_but_exact_visible(client):
    r=client.post('/api/search',json={'query':'다시 인증','namespace':'demo'}).json()
    assert all(x['status']=='active' for x in r['results'])
    r=client.post('/api/search',json={'query':'EX-0901','namespace':'demo'}).json()
    assert r['results'][0]['status']=='retired'
    assert client.get('/api/codes/EX-0901/copy?namespace=demo').status_code==409


def test_basic_auth_required_for_data(secured):
    assert secured.get('/api/health').status_code==200
    assert secured.get('/').status_code==200
    for path in ['/api/meta','/api/codes','/api/audit','/api/export/codes.csv','/api/template.xlsx']:
        assert secured.get(path).status_code==401
        assert secured.get(path,headers={'Authorization':'Bearer test-only-secret'}).status_code==200


def test_cross_site_mutation_denied(client):
    r=client.post('/api/search',json={'query':'인증'},headers={'Origin':'https://evil.example'})
    assert r.status_code==403
    r=client.post('/api/search',json={'query':'인증'},headers={'Origin':'http://testserver'})
    assert r.status_code==200


def test_untrusted_host_denied(client):
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==400


def test_empty_and_invalid_search(client):
    assert client.post('/api/search',json={'query':'  '}).status_code==422
    assert client.post('/api/search',json={'query':'인증','namespace':'someone-else'}).status_code==422
    assert client.post('/api/search',json={'query':'인증','limit':9999}).status_code==422


def test_security_headers(client):
    r=client.get('/')
    assert "script-src 'self'" in r.headers['content-security-policy']
    assert r.headers['x-content-type-options']=='nosniff'


def test_import_preview_commit_and_idempotency(client):
    p=upload(client,[['코드번호','등록문구'],['AT-0123','표시 문구']]).json()
    assert p['counts']['new']==1
    assert client.get('/api/codes').json()['total']==0
    assert commit(client,p).json()['added']==1
    assert commit(client,p).status_code==409
    c=client.get('/api/codes/AT-0123').json()
    assert c['source']['cells']=='A2, B2' and c['code']=='AT-0123'


def test_reimport_same_skipped(client):
    add(client)
    p=upload(client,[['코드번호','등록문구'],['AT-1923','메뉴확인 30초 이후에 인증해주세요.']]).json()
    assert p['counts']['unchanged']==1
    assert commit(client,p).json()['added']==0


def test_conflict_cannot_silently_overwrite(client):
    add(client)
    p=upload(client,[['코드번호','등록문구'],['AT-1923','다른 문구'],['AT-222','신규 문구']]).json()
    assert p['counts']['conflict']==1
    assert commit(client,p).status_code==409
    assert commit(client,p,skip_conflicts=True).json()['added']==1
    assert client.get('/api/codes/AT-1923').json()['message']=='메뉴확인 30초 이후에 인증해주세요.'


def test_stale_import_rejected(client):
    p=upload(client,[['코드번호','등록문구'],['AT-111','문구']]).json()
    add(client)
    assert commit(client,p).status_code==409


def test_duplicate_code_inside_file_blocks_all(client):
    p=upload(client,[['코드번호','등록문구'],['AT-111','문구'],['AT-111','문구2']]).json()
    assert p['errors']
    assert commit(client,p).status_code==422
    assert client.get('/api/codes').json()['total']==0


def test_duplicate_message_different_code_warns(client):
    p=upload(client,[['코드번호','등록문구'],['AT-111','문구'],['AT-112','문구']]).json()
    assert p['records'][1]['same_message_codes']==['AT-111']


def test_xlsx_provenance_and_literal_text(client):
    p=upload(client,xlsx_fixture(),filename='실제표.xlsx').json()
    assert p['errors']==[]
    assert p['records'][0]['code']=='AT-001'
    assert commit(client,p).status_code==200
    row=client.get('/api/codes/AT-001').json()
    assert row['message']=='  원문\n둘째 줄 {seconds}  '
    assert row['source']['sheet']=='알림 목록' and row['source']['cell_map']['message']=='B2'


def test_formula_not_imported(client):
    p=upload(client,xlsx_fixture(formula=True),filename='formulas.xlsx').json()
    assert any('수식' in e for e in p['errors'])
    assert commit(client,p).status_code==422


def test_merged_identifier_not_fanned_out(client):
    p=upload(client,xlsx_fixture(merged=True),filename='merged.xlsx').json()
    assert any('세로 병합' in e for e in p['errors'])


def test_xml_entities_rejected(client):
    assert upload(client,xlsx_fixture(doctype=True),filename='entity.xlsx').status_code==422


def test_manual_column_mapping(client):
    p=upload(client,[['내부번호','안내글'],['AT-101','메시지']],mapping={'CSV':{'header_row':1,'columns':{'code':'A','message':'B'}}}).json()
    assert not p['errors'] and p['records'][0]['code']=='AT-101'


def test_unsupported_file_and_upload_limits(client):
    assert upload(client,b'not excel',filename='x.xls').status_code==422
    assert upload(client,b'not excel',filename='x.xlsx').status_code==422
    assert upload(client,b'a'*(8*1024*1024+1)).status_code==413


def test_unknown_status_rejected(client):
    p=upload(client,[['코드번호','등록문구','상태'],['AT-101','문구','아무거나']]).json()
    assert p['errors']


def test_export_csv_formula_injection_protected(client):
    add(client,message='=HYPERLINK("https://bad.example")')
    r=client.get('/api/export/codes.csv')
    assert "'=HYPERLINK" in r.text
    assert client.get('/api/codes/AT-1923').json()['message'].startswith('=')


def test_filename_traversal_not_used_as_path(client):
    p=upload(client,[['코드번호','등록문구'],['AT-111','문구']],filename='../../bad.csv').json()
    assert p['filename']=='bad.csv'


def test_same_code_can_exist_in_separate_catalog(client):
    add(client,code='AT-1923',message='실제 원문')
    assert client.get('/api/codes/AT-1923').json()['message']=='실제 원문'
    assert client.get('/api/codes/AT-1923?namespace=demo').json()['message']!='실제 원문'


def test_review_unknown_and_existing(client):
    r=client.post('/api/review',json={'namespace':'demo','text':'AT-1923\nAT-9999\n인증번호 오류'}).json()
    assert len(r['items'])==3
    assert r['items'][0]['results'][0]['code']=='AT-1923'
    assert r['items'][1]['missing_codes']==['AT-9999']


def test_review_line_limit(client):
    assert client.post('/api/review',json={'text':'인증\n'*31}).status_code==422
    assert client.post('/api/review',json={'text':'\n\n'}).status_code==422


def test_import_update_requires_selection_and_reason(client):
    add(client)
    p=upload(client,[['코드번호','등록문구','상태'],['AT-1923','승인된 새 원문','폐기']]).json()
    assert commit(client,p,approved_updates=['AT-1923']).status_code==422
    r=commit(client,p,approved_updates=['AT-1923'],update_reason='최신 승인 규격 반영')
    assert r.status_code==200 and r.json()['updated']==1
    row=client.get('/api/codes/AT-1923').json()
    assert row['message']=='승인된 새 원문' and row['revision']==2 and row['status']=='retired'
    logs=client.get('/api/audit').json()['items']
    assert any(x['action']=='code.source_updated' and '30초' in x['before_json'] for x in logs)


def test_import_update_only_selected_codes(client):
    add(client)
    add(client,code='AT-2222',message='다른 기존 문구')
    p=upload(client,[['코드번호','등록문구'],['AT-1923','변경 원문'],['AT-2222','다른 변경 원문']]).json()
    r=commit(client,p,approved_updates=['AT-1923'],update_reason='선택 확인',skip_conflicts=True)
    assert r.status_code==200 and r.json()['skipped_conflicts']==1
    assert client.get('/api/codes/AT-2222').json()['message']=='다른 기존 문구'


def test_import_cannot_update_code_outside_preview(client):
    p=upload(client,[['코드번호','등록문구'],['AT-123','신규']]).json()
    assert commit(client,p,approved_updates=['AT-999'],update_reason='확인').status_code==422


def test_natural_search_does_not_claim_unspecified_condition_conflict(client):
    r=client.post('/api/search',json={'query':'인증 전에 30초 기다리라는 알림','namespace':'demo'}).json()
    assert r['results'][0]['match']['verdict']=='related'
