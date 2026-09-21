from sqlalchemy import update
from fastapi.testclient import TestClient
from code_agent.store import SampleStore,sample_codes
from code_agent import inspection
from conftest import ScriptedGateway
from test_api import app_for,headers

def test_seed_once_then_reads_db_without_json(seeded,monkeypatch):
    sample=SampleStore(seeded)
    with seeded.engine.begin() as c:c.execute(update(sample_codes).where(sample_codes.c.code=='EX-0101').values(message='DB 원문',title='DB 원문'))
    def missing():raise AssertionError('Runtime must not reopen JSON')
    monkeypatch.setattr(inspection,'sample_records',missing)
    sample.initialize_catalog()
    assert sample.get_code('EX-0101')['title']=='DB 원문'
    assert len(sample.snapshot(True)[1])==300 and len(sample.snapshot()[1])==279
    assert seeded.get_code('EX-0101') is None

def test_search_compare_review_share_sample_db_gateway(seeded):
    sample=SampleStore(seeded);gateway=ScriptedGateway(sample)
    with TestClient(app_for(seeded,sample_gateway=gateway)) as c:
        assert c.post('/api/code-catalog/search-test',json={'query':'인증'}).status_code==401
        r=c.post('/api/code-catalog/search-test',headers=headers(),json={'query':'인증','namespace':'demo'})
        assert r.status_code==200 and r.json()['storage']=='postgresql'
        assert r.json()['trace'][0]['name']=='TEST_DOUBLE_RETRIEVAL'
        for path,body in [('compare',{'message':'인증'}),('review',{'text':'인증'})]:
            r=c.post('/api/code-catalog/'+path,headers=headers(),json=dict(body,namespace='demo',mode='semantic'))
            assert r.status_code==200
        assert len(gateway.calls)==3
