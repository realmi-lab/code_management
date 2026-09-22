"""Bounded neural reranking for catalogue hits and dropping uncited hits from a turn.

Test doubles only: no neural model, no PGVector/Nori, no provider call.
"""
import sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extensions'))
import pytest
from types import SimpleNamespace as NS
from code_agent.gateway import CatalogReranker,rerank_text,RERANK_CANDIDATES
from code_agent.agent import Agent
from code_agent.models import Turn,Explanation,Plan
from conftest import USER

class Doc:
    def __init__(self,code,content='업무구분: X\n타입: Y\n영문컨텐츠: long english copy\n'+'비고: '+'x'*400):
        self.metadata={'code':code,'revision':1};self.content=content
    def model_copy(self,update):
        d=Doc(self.metadata['code']);d.content=update['content'];return d

class Base:
    def __init__(self):self.calls=[]
    async def rerank(self,query,documents,top_k=5,score_mode='calibrated',alpha=0.7):
        self.calls.append((query,[d.content for d in documents],top_k,score_mode,alpha))
        return documents[:top_k]

def req(text):return Turn(request_id=uuid.uuid4(),expected_version=0,text=text)

@pytest.mark.asyncio
async def test_reranker_scores_only_top_hits_on_registered_wording():
    records={f'AT-{i:04d}':{'code':f'AT-{i:04d}','message':f'문구 {i}','menu':'인증' if i%2 else '','trigger':f'조건 {i}'} for i in range(40)}
    base=Base();docs=[Doc(f'AT-{i:04d}') for i in range(40)]+[Doc('AT-9999')]
    out=await CatalogReranker(base,records,redact=lambda v:v.replace('문구','[R]')).rerank('질의',docs,top_k=8,score_mode='replace',alpha=0.3)
    query,contents,top_k,mode,alpha=base.calls[0]
    assert len(contents)==RERANK_CANDIDATES and top_k==8 and mode=='replace' and alpha==0.3
    assert contents[0]=='[R] 0\n노출 조건: 조건 0' and contents[1]=='[R] 1\n메뉴: 인증\n노출 조건: 조건 1'
    assert all('영문컨텐츠' not in c for c in contents) and len(out)==8

@pytest.mark.asyncio
async def test_reranker_keeps_unknown_hit_text_and_top_k_floor():
    base=Base();docs=[Doc('ZZ-0001','raw')]*3
    await CatalogReranker(base,{},limit=1).rerank('q',docs,top_k=2)
    assert base.calls[0][1]==['raw','raw']

def test_rerank_text_omits_empty_fields():
    assert rerank_text({'message':'m','menu':'','trigger':''})=='m'

@pytest.mark.asyncio
async def test_uncited_explanation_drops_search_candidates(seeded,gateway):
    gateway.responses=[Plan(action='search',query='부산 날씨').model_dump(),Explanation(text='날씨에 해당하는 등록 코드는 확인되지 않았습니다.',references=[]).model_dump()]
    t=seeded.create_thread(USER);r=await Agent(seeded,gateway).turn(USER,t['id'],req('내일 부산 날씨 어때'))
    assert r['candidates']==[] and r['ai_used'] and {'name':'no_relevant_candidate','count':3} in r['trace']
    assert seeded.get_thread(USER,t['id'])['candidates']==[]
    assert '확인되지 않았습니다' in r['answer']

@pytest.mark.asyncio
async def test_cited_explanation_keeps_candidates(seeded,gateway):
    t=seeded.create_thread(USER);r=await Agent(seeded,gateway).turn(USER,t['id'],req('인증 전에 30초 기다리라는 알림 있어?'))
    assert [c['code'] for c in r['candidates']] and not any(s['name']=='no_relevant_candidate' for s in r['trace'])
