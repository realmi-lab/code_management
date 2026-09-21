import json
from sqlalchemy import inspect,text
from code_agent.catalog_schema import FIELDS
from code_agent.store import Store
from code_agent.models import Revision
from conftest import ADMIN
from test_api import app_for,headers
from fastapi.testclient import TestClient

def test_old_db_migrates_without_losing_original(tmp_path):
    s=Store('sqlite:///'+str(tmp_path/'legacy.db'))
    with s.engine.begin() as c:
        c.execute(text('CREATE TABLE cm_codes (id VARCHAR(36) PRIMARY KEY, code VARCHAR(40) UNIQUE NOT NULL, message TEXT NOT NULL, menu TEXT, trigger TEXT, notes TEXT, status VARCHAR(20), revision INTEGER, source JSON, updated_at VARCHAR(40))'))
        c.execute(text("INSERT INTO cm_codes VALUES ('old','AT-0001',' 원문 유지 ','인증','대기','비고','active',3,'{}','2026-09-01')"))
    s.initialize();s.initialize()
    r=s.get_code('AT-0001')
    assert r['message_code']=='AT-0001' and r['title']==r['message']==' 원문 유지 '
    assert r['revision']==3 and r['spelling_check']=='미검사'
    assert r['added_date']=='' # Unknown creation dates must not be invented.
    assert s.status()['version']==1
    assert set(k for k,_ in FIELDS)<=set(c['name'] for c in inspect(s.engine).get_columns('cm_codes'))

def test_business_revision_and_export(seeded):
    old=seeded.get_code('AT-1923');date=old['added_date']
    b=Revision(expected_revision=1,expected_catalog_version=1,message='새 원문',title='새 title',business='인증 업무',message_type='alert',purpose='검증',title_en='New title',contents_en='New contents',reason='구조 검증')
    seeded.revise_code(ADMIN,'AT-1923',b)
    r=seeded.get_code('AT-1923');assert r['message']==r['title']=='새 title'
    assert r['added_date']==date and r['contents_en']=='New contents'
    with TestClient(app_for(seeded)) as client:
        data=client.get('/api/code-catalog/export.json',headers=headers()).json()
        assert data['schema_version']==2
        item=next(r for r in data['items'] if r['message_code']=='AT-1923')
        assert set(item)=={k for k,_ in FIELDS}|{'_meta'}
        assert client.get('/api/code-catalog/codes?q=New%20contents',headers=headers()).json()['total']==1

def test_all_samples_have_business_structure():
    from code_agent.inspection import sample_records
    from code_agent.catalog_schema import export_record
    rows=sample_records()
    assert len(rows)==300
    for r in rows:
        assert all(key in export_record(r) for key,_ in FIELDS)
        assert r['message_code']==r['code'] and r['title']==r['message']
        assert r['spelling_check']=='미검사' and r['title_en'] and r['contents_en']
