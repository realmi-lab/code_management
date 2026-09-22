"""Original upstream reranker inputs and preservation of uncited DB hits.

Test doubles only: no neural model, no PGVector/Nori, no provider call.
"""
import sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extensions'))
import pytest
from types import SimpleNamespace as NS
from weakref import WeakKeyDictionary
from code_agent import rerank_runtime
from code_agent.gateway import CatalogReranker
from code_agent.agent import Agent
from code_agent.models import Turn,Explanation,Plan
from conftest import USER


@pytest.fixture(autouse=True)
def isolated_reranker_runtime(monkeypatch):
    """Exercise the real worker adapter without importing Torch for fake models."""
    monkeypatch.setattr(rerank_runtime,'_executor',None)
    monkeypatch.setattr(rerank_runtime,'_gates',WeakKeyDictionary())
    monkeypatch.setattr(rerank_runtime,'_init_worker',lambda:None)
    try:
        yield
    finally:
        executor=rerank_runtime._executor
        if executor is not None:executor.shutdown(wait=True,cancel_futures=True)

class Doc:
    def __init__(self,code,content='업무구분: X\n타입: Y\n영문컨텐츠: long english copy\n'+'비고: '+'x'*400,score=0.0,metadata=None):
        self.metadata={'code':code,'revision':1} if metadata is None else metadata
        self.content=content;self.score=score
    def model_copy(self,update):
        d=Doc(self.metadata['code'],self.content,self.score,dict(self.metadata))
        for key,value in update.items():setattr(d,key,value)
        return d

class Base:
    def __init__(self):self.calls=[]
    async def rerank(self,query,documents,top_k=5,score_mode='calibrated',alpha=0.7):
        self.calls.append((query,documents,top_k,score_mode,alpha))
        return documents[:top_k]

def req(text):return Turn(request_id=uuid.uuid4(),expected_version=0,text=text)

@pytest.mark.asyncio
async def test_reranker_passes_every_original_indexed_chunk_and_options():
    base=Base();docs=[Doc(f'AT-{i:04d}') for i in range(40)]+[Doc('AT-9999')]
    original=[(d.content,dict(d.metadata)) for d in docs]
    out=await CatalogReranker(base).rerank('질의',docs,top_k=8,score_mode='replace',alpha=0.3)
    query,received,top_k,mode,alpha=base.calls[0]
    assert query=='질의' and top_k==8 and mode=='replace' and alpha==0.3
    assert received is docs and len(received)==41
    assert [(d.content,d.metadata) for d in docs]==original
    assert len(out)==8
    assert all(out[i] is docs[i] for i in range(8))

@pytest.mark.asyncio
async def test_adapter_does_not_truncate_split_or_rewrite_long_chunks():
    base=Base();docs=[Doc('ZZ-0001','raw field '*100)]
    out=await CatalogReranker(base).rerank('q',docs,top_k=2)
    assert len(base.calls)==1 and base.calls[0][1] is docs
    assert len(base.calls[0][1][0].content)==1000
    assert out==docs and out[0] is docs[0]


@pytest.mark.asyncio
async def test_adapter_preserves_upstream_result_count_order_scores_and_metadata():
    docs=[Doc('QA-1','first',metadata={'code':'QA-1','revision':7,'source':{'row':1}}),
          Doc('QA-2','second',metadata={'code':'QA-2','revision':8,'source':{'row':2}})]
    upstream=[docs[1].model_copy(update={'score':0.93})]
    class ResultBase:
        async def rerank(self,query,documents,top_k,**options):
            assert top_k==5 and documents is docs
            return upstream
    result=await CatalogReranker(ResultBase()).rerank('q',docs,top_k=5)
    assert result is upstream and len(result)==1 and result[0].score==0.93
    assert result[0].metadata==docs[1].metadata and result[0].content=='second'

@pytest.mark.asyncio
async def test_uncited_explanation_preserves_search_candidates(seeded,gateway):
    _,expected=seeded.snapshot()
    gateway.responses=[Plan(action='search',query='부산 날씨').model_dump(),Explanation(text='날씨에 해당하는 등록 코드는 확인되지 않았습니다.',references=[]).model_dump()]
    t=seeded.create_thread(USER);r=await Agent(seeded,gateway).turn(USER,t['id'],req('내일 부산 날씨 어때'))
    assert r['candidates']==expected and r['ai_used'] and r['ai_error'] is None
    assert r['search_info']['shown']==len(expected)
    assert {'name':'no_cited_candidate','count':len(expected)} in r['trace']
    assert not any(s['name']=='no_relevant_candidate' for s in r['trace'])
    assert seeded.get_thread(USER,t['id'])['candidates']==[
        {'code':c['code'],'revision':c['revision']} for c in expected]
    assert '확인되지 않았습니다' in r['answer']

@pytest.mark.asyncio
async def test_partially_cited_explanation_keeps_all_candidates(seeded,gateway):
    _,expected=seeded.snapshot()
    gateway.responses=[Plan(action='search',query='인증 대기').model_dump(),
        Explanation(text='조회한 등록 문구를 확인했습니다.',references=[expected[0]['code']]).model_dump()]
    t=seeded.create_thread(USER);r=await Agent(seeded,gateway).turn(USER,t['id'],req('인증 전에 30초 기다리라는 알림 있어?'))
    assert r['candidates']==expected and r['search_info']['shown']==len(expected)
    assert not any(s['name'] in ('no_relevant_candidate','no_cited_candidate') for s in r['trace'])
