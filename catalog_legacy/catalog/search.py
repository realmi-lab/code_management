from __future__ import annotations
import json
import math
import re
import uuid
from collections import Counter
from .ai import AIError, embedding_text, fingerprint
from .compare import normalized, compare_message
from .models import SearchResult, CODE_IN_TEXT, canonical_code
from vendor.urstory_rag.rrf import RRFCombiner

# Transparent domain aliases. This offline mode is NOT represented as an LLM/embedding model.
CONCEPTS={
 'verify':['인증','본인확인','otp','인증번호'],
 'wait':['기다','대기','이후','지나','뒤에','후에','지연'],
 'deadline':['이내','안에','제한시간','만료'],
 'resend':['재전송','다시요청','재발급','재발송','다시보내'],
 'signup':['회원가입','가입'], 'login':['로그인','접속'],
 'phone':['휴대폰','핸드폰','전화번호','휴대전화'],
 'duplicate':['중복','이미사용','이미가입','사용중'],
 'password':['비밀번호','패스워드'], 'email':['이메일','메일주소'],
 'network':['네트워크','인터넷','통신','연결실패'], 'permission':['권한','접근'],
 'save':['저장','변경사항'], 'leave':['나가','이탈','화면종료'],
 'consent':['약관','동의'], 'error':['오류','실패','불일치','틀린','잘못된'],
}
STOP={'어떤','알림','문구','코드','있어','찾아줘','해주세요','알려줘','필요해','메뉴에서','이런','새로','비슷한'}

def terms(text):
    n=normalized(text)
    tokens=[t for t in re.findall(r'[가-힣]+|[a-z]+|\d+',text.lower()) if t not in STOP]
    for name,patterns in CONCEPTS.items():
        if any(p in n for p in patterns): tokens.extend(['@'+name]*2)
    tokens.extend(re.findall(r'\d+',text))
    return Counter(tokens)

def ngrams(text):
    t=normalized(text)
    return Counter(t[i:i+2] for i in range(max(0,len(t)-1)))

def cosine(a,b):
    if not a or not b: return 0.0
    if isinstance(a,dict):
        den=math.sqrt(sum(x*x for x in a.values())*sum(x*x for x in b.values()))
        return sum(v*b.get(k,0) for k,v in a.items())/den if den else 0.0
    if len(a)!=len(b): return 0.0
    den=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return sum(x*y for x,y in zip(a,b))/den if den else 0.0

class Search:
    def __init__(self,db,ai): self.db=db; self.ai=ai; self.rrf=RRFCombiner()

    async def find(self,query,namespace='live',limit=8,include_retired=False,menu='',trigger='',comparison_text=None):
        codes=list(dict.fromkeys(c.upper() for c in CODE_IN_TEXT.findall(query)))
        if codes:
            results=[]; missing=[]
            for code in codes:
                row=self.db.get_code(namespace,code)
                if row:
                    row['match']={'label':'코드번호 정확히 일치','verdict':'exact_code','differences':[]}
                    if row['status']=='retired': row['match']={'label':'폐기된 코드 · 재사용 제외','verdict':'retired','differences':['정확한 번호 조회이므로 폐기 항목도 표시합니다.']}
                    results.append(row)
                else: missing.append(code)
            return self.response(namespace,results,mode='exact',missing=missing)
        rows=self.db.all_codes(namespace,include_retired)
        if not rows: return self.response(namespace,[],mode='basic')
        qt,qg=terms(query),ngrams(query)
        lexical={}; character={}; byid={x['id']:x for x in rows}
        for row in rows:
            text=embedding_text(row)
            lexical[row['id']]=cosine(qt,terms(text))
            character[row['id']]=cosine(qg,ngrams(text))
        vector=character; mode='basic'; notice=''; coverage=0
        if self.ai.embedding_enabled:
            with self.db.connect() as con:
                embeds={r['code_id']:r for r in con.execute('SELECT e.* FROM embeddings e JOIN codes c ON e.code_id=c.id WHERE c.namespace=? AND e.model=?',(namespace,self.ai.embedding_identity))}
            valid={i:json.loads(e['vector']) for i,e in embeds.items() if i in byid and e['fingerprint']==fingerprint(byid[i])}
            coverage=len(valid)
            if valid:
                try:
                    qvec=(await self.ai.embeddings([query]))[0]
                    # Keep unindexed items available through character/keyword search.
                    vector={i:(max(0.0,cosine(qvec,valid[i])) if i in valid else character[i]) for i in byid}
                    mode='embedding' if len(valid)==len(rows) else 'embedding_partial'
                except AIError as exc: notice=str(exc)
            else: notice='아직 검색 임베딩이 생성되지 않아 기본 검색을 사용합니다.'
        def ranked(scores,threshold):
            out=[]
            for ident,score in sorted(scores.items(),key=lambda kv:kv[1],reverse=True)[:80]:
                if score<threshold: continue
                row=byid[ident]
                out.append(SearchResult(chunk_id=uuid.UUID(ident),document_id=uuid.UUID(ident),content=row['message'],score=score,metadata={'code':row['code']}))
            return out
        fused=self.rrf.combine(ranked(vector,0.16 if mode.startswith('embedding') else 0.09),ranked(lexical,0.09))
        results=[]
        for item in fused[:limit]:
            row=dict(byid[str(item.chunk_id)])
            row['rank_score']=round(item.score,6)  # Ranking only; never an accuracy/confidence percentage.
            if comparison_text is not None:
                row['match']=compare_message(comparison_text,row,menu=menu,trigger=trigger)
            else:
                row['match']={'verdict':'retired' if row['status']=='retired' else 'related',
                    'label':'폐기된 코드 · 재사용 제외' if row['status']=='retired' else '관련 코드 후보',
                    'differences':[]}
            results.append(row)
        return self.response(namespace,results,mode=mode,notice=notice,coverage=coverage)

    def response(self,ns,results,mode,missing=None,notice='',coverage=0):
        if missing: summary='다음 코드번호는 현재 목록에 없습니다: '+', '.join(missing)+'. 존재하는 코드로 대체하지 않았습니다.'
        elif mode=='exact': summary='등록된 코드의 원문입니다. 문구는 자동으로 수정하지 않았습니다.'
        elif results: summary=f'관련 후보 {len(results)}개를 찾았습니다. 원문과 노출 조건을 비교한 뒤 선택해주세요.'
        else: summary='현재 검색 범위에서 적합한 후보를 찾지 못했습니다. 신규 등록 전 다른 표현과 폐기 목록도 확인해주세요.'
        return {'summary':summary,'results':results,'mode':mode,'notice':notice,'missing_codes':missing or [],
                'catalog_version':self.db.version(ns),'embedding_coverage':coverage,
                'scope':{'namespace':ns,'catalog_count':len(self.db.all_codes(ns))}}

    async def reindex(self,ns):
        if not self.ai.embedding_enabled: raise AIError('임베딩 모델이 연결되지 않았습니다.')
        rows=self.db.all_codes(ns)
        with self.db.connect() as con:
            existing={x['code_id']:x['fingerprint'] for x in con.execute('SELECT * FROM embeddings WHERE model=?',(self.ai.embedding_identity,))}
        todo=[r for r in rows if existing.get(r['id'])!=fingerprint(r)]
        count=0
        for offset in range(0,len(todo),16):
            batch=todo[offset:offset+16]; vectors=await self.ai.embeddings([embedding_text(x) for x in batch])
            with self.db.connect(write=True) as con:
                for row,vec in zip(batch,vectors):
                    current=self.db.get_code(ns,row['code'],con)
                    if not current or fingerprint(current)!=fingerprint(row): continue
                    con.execute('INSERT OR REPLACE INTO embeddings(code_id,model,fingerprint,vector) VALUES(?,?,?,?)',
                       (row['id'],self.ai.embedding_identity,fingerprint(row),json.dumps(vec)))
                    count+=1
        return {'indexed':count,'total':len(rows)}
