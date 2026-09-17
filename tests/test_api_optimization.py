import asyncio
import os
import pytest
from catalog import main, db as db_module
from .conftest import add, upload, commit

def test_paged_codes_preserve_unicode_and_literal_filters(client):
    rows=[['코드번호','등록문구','사용메뉴','노출조건','상태'],
          ['AT-0001','ÉCOLE 100%_확인','가입','확인','사용 중'],
          ['AT-0002','다른 문구','가입','조건','폐기'],
          ['AT-0003','세 번째 원문','메뉴','조건','사용 중']]
    preview=upload(client,rows).json();assert commit(client,preview).status_code==200
    page=client.get('/api/codes',params={'limit':1,'offset':1,'status':'active'}).json()
    assert page['total']==2 and page['items'][0]['code']=='AT-0003'
    for query in ['école','100%_','at-0001 école']:
        result=client.get('/api/codes',params={'q':query}).json()
        assert result['total']==1 and result['items'][0]['message']=='ÉCOLE 100%_확인'
    assert client.get('/api/codes',params={'offset':999}).json()['items']==[]
    assert client.get('/api/meta').json()['counts']=={'total':3,'active':2,'retired':1,'drafts':0}

def test_page_decodes_only_selected_rows_and_meta_decodes_none(client,monkeypatch):
    for i in range(5):add(client,code=f'AT-{i}')
    decoded=[]
    real=db_module.decode_code
    def tracked(row):
        decoded.append(row['code']);return real(row)
    monkeypatch.setattr(db_module,'decode_code',tracked)
    assert client.get('/api/meta').json()['counts']['total']==5
    assert decoded==[]
    assert len(client.get('/api/codes',params={'offset':2,'limit':2}).json()['items'])==2
    assert len(decoded)==2

def test_failed_original_storage_never_leaves_committable_preview(client,monkeypatch):
    def fail(_):raise OSError('sensitive internal path must not reach the client')
    monkeypatch.setattr(os,'fsync',fail)
    result=upload(client,[['코드번호','등록문구'],['AT-9','문구']])
    assert result.status_code==503
    assert 'sensitive' not in result.text
    with client.app.state.db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM imports').fetchone()[0]==0
    assert list((client.app.state.settings.data_dir/'uploads').iterdir())==[]

def test_original_file_exists_before_preview_row_visible(client,monkeypatch):
    real=main.dumps
    checked=[]
    def serialization(value):
        if isinstance(value,dict) and 'import_id' in value:
            original=client.app.state.settings.data_dir/'uploads'/(value['import_id']+'.csv')
            assert original.exists() and original.stat().st_size>0
            assert original.stat().st_mode & 0o777==0o600
            checked.append(True)
        return real(value)
    monkeypatch.setattr(main,'dumps',serialization)
    result=upload(client,[['코드번호','등록문구'],['AT-9','원문']])
    assert result.status_code==200 and checked

def test_spreadsheet_parser_runs_off_event_loop(client,monkeypatch):
    real=main.parse_upload;on_loop=[]
    def parse(*args):
        try:asyncio.get_running_loop()
        except RuntimeError:on_loop.append(False)
        else:on_loop.append(True)
        return real(*args)
    monkeypatch.setattr(main,'parse_upload',parse)
    assert upload(client,[['코드번호','등록문구'],['AT-9','문구']]).status_code==200
    assert on_loop==[False]

def test_non_ascii_auth_header_is_unauthorized_not_server_error(secured):
    assert secured.get('/api/meta',headers={b'authorization':b'Bearer \xff'}).status_code==401

def test_comparison_rejects_blank_message(client):
    assert client.post('/api/compare',json={'query':'사용자 질문','message':' \n\t '}).status_code==422
