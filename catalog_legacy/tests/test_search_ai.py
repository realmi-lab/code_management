import asyncio
import json
import uuid
import httpx
import pytest
from catalog.compare import signature,compare_message
from catalog.ai import AI,AIError
from catalog.config import Settings
from catalog.models import SearchResult
from vendor.urstory_rag.rrf import RRFCombiner
from .conftest import add


def test_upstream_rrf_combines_by_rank():
    i,j=uuid.uuid4(),uuid.uuid4()
    a=SearchResult(chunk_id=i,document_id=i,content='A',score=0.1)
    b=SearchResult(chunk_id=j,document_id=j,content='B',score=0.9)
    r=RRFCombiner().combine([a,b],[b],vector_weight=0.5,keyword_weight=0.5)
    assert r[0].chunk_id==j
    assert r[0].score==pytest.approx(.5/62+.5/61)


def test_time_unit_normalization():
    assert signature('60초 이후에 인증해주세요.')==signature('1분 이후에 인증해주세요.')


def test_swapped_number_conditions_not_equated():
    assert signature('30초 이후 60초 이내')!=signature('60초 이후 30초 이내')


def test_placeholders_preserved():
    row={'message':'{seconds}초 이후에 인증해주세요.','status':'active'}
    r=compare_message('{timeout}초 이후에 인증해주세요.',row)
    assert r['verdict']=='different_conditions'
    assert any('변수' in d for d in r['differences'])


def test_negation_difference_flagged():
    r=compare_message('인증할 수 있습니다.',{'message':'인증할 수 없습니다.','status':'active'})
    assert any('부정' in d for d in r['differences'])


def test_external_ai_requires_consent(tmp_path):
    with pytest.raises(ValueError): Settings(data_dir=tmp_path,ai_enabled=True,ai_base_url='https://external.example/v1')
    with pytest.raises(ValueError): Settings(data_dir=tmp_path,ai_enabled=True,ai_allow_external=True,ai_base_url='http://external.example/v1')


def test_no_external_calls_in_basic_search(client,monkeypatch):
    async def reject(*a,**kw): raise AssertionError('Network must not be called')
    monkeypatch.setattr(httpx.AsyncClient,'post',reject)
    r=client.post('/api/search',json={'query':'인증','namespace':'demo'})
    assert r.status_code==200 and r.json()['mode']=='basic'


def test_ai_draft_disabled_preserves_original(tmp_path):
    ai=AI(Settings(data_dir=tmp_path))
    out,note=asyncio.run(ai.draft(' 원문 30초 이후 ', '', '', []))
    assert out==' 원문 30초 이후 ' and '미연결' in note


def test_ai_cannot_change_conditions(tmp_path,monkeypatch):
    ai=AI(Settings(data_dir=tmp_path,ai_enabled=True,ai_chat_model='test'))
    async def response(*args): return {'choices':[{'message':{'content':json.dumps({'message':'30초 이내에 인증해주세요.'})}}]}
    monkeypatch.setattr(ai,'request',response)
    with pytest.raises(AIError): asyncio.run(ai.draft('30초 이후에 인증해주세요.','','',[]))


def test_ai_cannot_invent_code(tmp_path,monkeypatch):
    ai=AI(Settings(data_dir=tmp_path,ai_enabled=True,ai_chat_model='test'))
    async def response(*args): return {'choices':[{'message':{'content':json.dumps({'message':'AT-9999 저장해주세요.'})}}]}
    monkeypatch.setattr(ai,'request',response)
    with pytest.raises(AIError): asyncio.run(ai.draft('저장해주세요.','','',[]))


def test_ai_valid_rewording(tmp_path,monkeypatch):
    ai=AI(Settings(data_dir=tmp_path,ai_enabled=True,ai_chat_model='test'))
    async def response(*args): return {'choices':[{'message':{'content':json.dumps({'message':'30초 이후에 인증해 주세요.','rationale':'띄어쓰기 개선'})}}]}
    monkeypatch.setattr(ai,'request',response)
    result,_=asyncio.run(ai.draft('30초 이후에 인증해주세요.','','',[]))
    assert result=='30초 이후에 인증해 주세요.'


def test_embeddings_validate_nan(tmp_path,monkeypatch):
    ai=AI(Settings(data_dir=tmp_path,ai_enabled=True,ai_embedding_model='test'))
    async def response(*args): return {'data':[{'index':0,'embedding':[float('nan'),1]}]}
    monkeypatch.setattr(ai,'request',response)
    with pytest.raises(AIError): asyncio.run(ai.embeddings(['문구']))


def test_embedding_index_and_refresh(client,monkeypatch):
    add(client)
    app=client.app
    app.state.settings.ai_enabled=True;app.state.settings.ai_embedding_model='test'
    async def embed(texts): return [[1.,0.,0.] for _ in texts]
    monkeypatch.setattr(app.state.ai,'embeddings',embed)
    assert client.post('/api/ai/reindex').json()['indexed']==1
    assert client.post('/api/ai/reindex').json()['indexed']==0
    r=client.post('/api/search',json={'query':'대기 안내'}).json()
    assert r['mode']=='embedding' and r['results'][0]['code']=='AT-1923'


def test_ai_failure_falls_back_to_basic(client,monkeypatch):
    add(client)
    ai=client.app.state.ai;settings=client.app.state.settings
    settings.ai_enabled=True;settings.ai_embedding_model='test'
    async def ok(texts): return [[1.,0.] for _ in texts]
    monkeypatch.setattr(ai,'embeddings',ok)
    client.post('/api/ai/reindex')
    async def fail(texts): raise AIError('연결 실패')
    monkeypatch.setattr(ai,'embeddings',fail)
    r=client.post('/api/search',json={'query':'30초 인증 대기'}).json()
    assert r['mode']=='basic' and r['results'] and '실패' in r['notice']
