from __future__ import annotations
import heapq
import json
import math
import re
import uuid
from collections import Counter, OrderedDict
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
    def __init__(self,db,ai):
        self.db=db; self.ai=ai; self.rrf=RRFCombiner()
        # Content-keyed features cannot outlive an edit as a stale row result.
        # Bound both entries and source text retained by this per-app cache.
        self._features_cache=OrderedDict()
        self._features_chars=0

    def _features(self,text):
        cached=self._features_cache.get(text)
        if cached is not None:
            self._features_cache.move_to_end(text)
            return cached
        def unit(counter):
            norm=math.sqrt(sum(value*value for value in counter.values()))
            return {key:value/norm for key,value in counter.items()} if norm else {}
        features=(unit(terms(text)),unit(ngrams(text)))
        if len(text)<=2*1024*1024:
            self._features_cache[text]=features
            self._features_chars+=len(text)
            while len(self._features_cache)>10000 or self._features_chars>2*1024*1024:
                expired,_=self._features_cache.popitem(last=False)
                self._features_chars-=len(expired)
        return features

    @staticmethod
    def _dot(a,b):
        if len(a)>len(b): a,b=b,a
        return sum(value*b.get(key,0) for key,value in a.items())

    def _snapshot(self,namespace,include_retired,codes=None):
        # Read rows, version and counts from the same SQLite snapshot. No read
        # transaction is held while an external model is running.
        with self.db.connect() as con:
            con.execute('BEGIN')
            version=self.db.version(namespace,con)
            total=self.db.count_codes(namespace,con=con)
            if codes is None:
                rows=self.db.all_codes(namespace,include_retired,con)
            else:
                rows=[row for code in codes if (row:=self.db.get_code(namespace,code,con))]
            vectors={}
            if codes is None and self.ai.embedding_enabled:
                byid={row['id']:row for row in rows}
                saved=con.execute('SELECT e.* FROM embeddings e JOIN codes c ON e.code_id=c.id WHERE c.namespace=? AND e.model=?',
                                  (namespace,self.ai.embedding_identity))
                for entry in saved:
                    row=byid.get(entry['code_id'])
                    if row is None or entry['fingerprint']!=fingerprint(row):
                        continue
                    try:
                        vector=json.loads(entry['vector'])
                        if not isinstance(vector,list) or not 1<=len(vector)<=8192:
                            continue
                        if not all(type(value) in (int,float) and math.isfinite(value) for value in vector):
                            continue
                    except (TypeError,ValueError):
                        continue
                    vectors[row['id']]=vector
        return {'rows':rows,'version':version,'total':total,'vectors':vectors}

    async def find(self,query,namespace='live',limit=8,include_retired=False,menu='',trigger='',comparison_text=None,use_ai=False):
        codes=list(dict.fromkeys(c.upper() for c in CODE_IN_TEXT.findall(query)))
        snapshot=self._snapshot(namespace,include_retired,codes=codes or None)
        rows=snapshot['rows']
        if codes:
            results=[]; present={row['code'] for row in rows}
            for row in rows:
                row['match']={'label':'코드번호 정확히 일치','verdict':'exact_code','differences':[]}
                if row['status']=='retired': row['match']={'label':'폐기된 코드 · 재사용 제외','verdict':'retired','differences':['정확한 번호 조회이므로 폐기 항목도 표시합니다.']}
                results.append(row)
            return self.response(namespace,results,mode='exact',missing=[code for code in codes if code not in present],snapshot=snapshot)
        if not rows: return self.response(namespace,[],mode='basic',snapshot=snapshot)
        ai_queries=[]; ai_cached=False; notice=''
        if use_ai and comparison_text is None:
            try:
                ai_queries,ai_cached=await self.ai.search_queries(query)
            except AIError as exc:
                notice=str(exc)
            snapshot=self._snapshot(namespace,include_retired)
        qvec=None
        if self.ai.embedding_enabled:
            if snapshot['vectors']:
                try:
                    qvec=(await self.ai.embeddings([query]))[0]
                except AIError as exc:
                    notice=str(exc)
                # Edits/retirement can occur during embedding inference too.
                snapshot=self._snapshot(namespace,include_retired)
            else:
                notice='아직 검색 임베딩이 생성되지 않아 기본 검색을 사용합니다.'
        rows=snapshot['rows']; byid={row['id']:row for row in rows}
        qt,qg=self._features(query)
        expansions=[self._features(q) for q in ai_queries]
        lexical={}; character={}
        for row in rows:
            rt,rg=self._features(embedding_text(row))
            lexical[row['id']]=max([self._dot(qt,rt)]+[0.85*self._dot(t,rt) for t,g in expansions])
            character[row['id']]=max([self._dot(qg,rg)]+[0.85*self._dot(g,rg) for t,g in expansions])
        valid=snapshot['vectors']
        if qvec is not None:
            valid={ident:vec for ident,vec in valid.items() if len(vec)==len(qvec)}
        coverage=len(valid); vector=character; mode='basic'
        if qvec is not None and valid:
            # Keep unindexed items available through character/keyword search.
            vector={ident:(max(0.0,cosine(qvec,valid[ident])) if ident in valid else character[ident]) for ident in byid}
            mode='embedding' if len(valid)==len(rows) else 'embedding_partial'
        elif qvec is not None:
            notice='목록이 변경되었거나 검색 임베딩이 맞지 않아 기본 검색을 사용합니다.'
        def ranked(scores,threshold):
            out=[]
            for ident,score in heapq.nlargest(80,scores.items(),key=lambda kv:kv[1]):
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
        if ai_queries and mode=='basic': mode='ai_query'
        response=self.response(namespace,results,mode=mode,notice=notice,coverage=coverage,snapshot=snapshot)
        response['ai_queries']=ai_queries
        response['ai_query_cached']=ai_cached
        return response

    def response(self,ns,results,mode,missing=None,notice='',coverage=0,snapshot=None):
        if missing: summary='다음 코드번호는 현재 목록에 없습니다: '+', '.join(missing)+'. 존재하는 코드로 대체하지 않았습니다.'
        elif mode=='exact': summary='등록된 코드의 원문입니다. 문구는 자동으로 수정하지 않았습니다.'
        elif results: summary=f'관련 후보 {len(results)}개를 찾았습니다. 원문과 노출 조건을 비교한 뒤 선택해주세요.'
        else: summary='현재 검색 범위에서 적합한 후보를 찾지 못했습니다. 신규 등록 전 다른 표현과 폐기 목록도 확인해주세요.'
        if snapshot is None:
            with self.db.connect() as con:
                con.execute('BEGIN')
                snapshot={'version':self.db.version(ns,con),'total':self.db.count_codes(ns,con=con)}
        return {'summary':summary,'results':results,'mode':mode,'notice':notice,'missing_codes':missing or [],
                'catalog_version':snapshot['version'],'embedding_coverage':coverage,
                'scope':{'namespace':ns,'catalog_count':snapshot['total']}}

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
