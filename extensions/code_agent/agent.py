"""Bounded conversational workflow: plan -> retrieve -> compare/write -> persist.

The model can choose read/compose operations only. Formal registration is NOT a
model tool. It is a separate authenticated, versioned administrator request.
"""
from __future__ import annotations
import re
from .models import CODE_IN_TEXT, Plan, Wording, Explanation, Turn
from .store import DomainError, digest
from .compare import compare_message, signature

from .skillbook import instructions as skill_instructions

PLANNER = skill_instructions('plan')
WRITER = skill_instructions('draft')
EXPLAINER = skill_instructions('search_explanation')

def requests_authoring(text):
    """Require an instruction outside quoted wording before accepting auto-draft.

    The explicit draft action remains authoritative. Ambiguous situations are
    read operations, even when the planner suggests composing a new message.
    """
    text=re.sub(r'"[^"\n]*"|\'[^\'\n]*\'|“[^”]*”|‘[^’]*’|`[^`]*`','',text)
    if re.search(r'(?:찾아|찾는|검색|조회|있어\s*[?？]?|있나요|있는지|있을까)',text):
        return False
    text=re.sub(r'(?:작성|생성|수정|변경|제안|다듬)[가-힣 ]{0,8}(?:하지\s*말[고아]|하지\s*마|하지\s*않|말고)|만들지\s*(?:말[고아]|마|않)','',text)
    return bool(re.search(
        r'(?:(?:작성|생성|수정|변경|제안)(?:해(?:\s*(?:줘|주세요|주실래|줄래|봐))?|하자|하기|요청|\s*$)'
        r'|(?:만들어|고쳐|바꿔|다듬어|줄여)(?:\s*(?:줘|주세요|봐))?|써\s*(?:줘|주세요)|새\s*초안\s*부탁)(?=$|[.!?？\s])',text))

class Agent:
    def __init__(self,store,gateway): self.store=store; self.gateway=gateway
    def _resolve(self,t,request):
        if request.selected_code:
            allowed={x['code'] for x in t['candidates']}|{m.upper() for m in CODE_IN_TEXT.findall(request.text)}
            if request.selected_code not in allowed: raise DomainError('현재 대화의 후보에서 코드를 선택해주세요.',422)
            previous=next((x for x in t['candidates'] if x['code']==request.selected_code),None)
            current=self.store.get_code(request.selected_code)
            if previous and (not current or current['revision']!=previous['revision']): raise DomainError('선택한 후보가 변경되었습니다. 다시 검색해주세요.')
            return request.selected_code
        m=re.search(r'(?<![\dA-Za-z])(\d{1,2})\s*(?:번째|번\s*(?:후보|항목|코드|결과))',request.text)
        korean=[('첫 번째',1),('첫번째',1),('두 번째',2),('두번째',2),('세 번째',3),('세번째',3)]
        n=int(m.group(1)) if m else next((n for term,n in korean if term in request.text),None)
        if n is not None:
            if not 1<=n<=len(t['candidates']): raise DomainError('해당 순번의 후보가 없습니다. 먼저 코드를 검색해주세요.',422)
            item=t['candidates'][n-1]; current=self.store.get_code(item['code'])
            if not current or current['revision']!=item['revision']: raise DomainError('선택한 후보가 변경되었습니다. 다시 검색해주세요.')
            return item['code']
        return None
    async def turn(self,actor,thread_id,request:Turn):
        fingerprint=digest(request.model_dump(mode='json',exclude={'expected_version'}))
        # Read (and ownership-check) the thread once; replay reuses that check.
        t=self.store.get_thread(actor,thread_id)
        replay=self.store.replay(actor,thread_id,str(request.request_id),fingerprint,checked=True)
        if replay is not None: return replay
        if request.expected_version!=t['version']: raise DomainError('대화가 변경되었습니다. 새로 불러온 뒤 다시 보내주세요.')
        version=self.store.status()['version']; selected=self._resolve(t,request)
        explicit=list(dict.fromkeys(c.upper() for c in CODE_IN_TEXT.findall(request.text)))
        if len(explicit)>20: raise DomainError('한 번에 코드 20개 이하로 조회해주세요.',422)
        plan=Plan(action='search',query=request.text,proposed_message=request.proposed_message,menu=request.menu,trigger=request.trigger)
        trace=[]; candidates=[]; missing=[]; comparison=[]; new_draft=None; ai_error=None
        if request.action!='auto': plan.action=request.action
        elif (not selected and not t['history'] and not request.proposed_message
              and re.search(r'찾아|검색|조회',request.text) and not re.search(r'비교|차이|설명|작성|초안|수정',request.text)
              and not requests_authoring(request.text)):
            pass  # Explicit lookup intent; retrieval still uses the unchanged query.
        elif not (explicit and re.fullmatch(r'[\s\w가-힣?.,!\-]+',request.text) and not requests_authoring(request.text) and not any(x in request.text for x in ('비교','차이'))):
            plan=await self.gateway.json(Plan,PLANNER,{'user':request.text,'history':[{k:v for k,v in entry.items() if k in ('role','content')} for entry in t['history'][-10:]], 'candidates':t['candidates'], 'previous_draft':t.get('draft')})
        if request.action=='auto' and plan.action=='draft' and not requests_authoring(request.text):
            # Discard guessed draft fields before proposal validation. A lookup
            # must not fail because the planner also invented proposed wording.
            plan=Plan(action='search',query=request.text)
        # Explicit form fields are authoritative; model guesses never overwrite them.
        for key in ('proposed_message','menu','trigger'):
            if getattr(request,key): setattr(plan,key,getattr(request,key))
        if plan.proposed_message and not request.proposed_message:
            prior=(t.get('draft') or {}).get('payload',{}).get('message','')
            if plan.proposed_message not in request.text and plan.proposed_message!=prior:
                raise DomainError('AI가 사용자가 작성하지 않은 비교 문구를 넣어 차단했습니다. 문구를 직접 입력해주세요.',502)
        if selected and plan.action=='search' and request.action=='auto': plan.action='explain'
        if selected or explicit:
            wanted=list(dict.fromkeys(([selected] if selected else [])+explicit))
            found=self.store.get_codes(wanted)
            for code in wanted:
                rec=found.get(code)
                if rec: candidates.append(rec)
                else: missing.append(code)
            trace.append({'name':'exact_lookup','count':len(candidates)})
        elif plan.action=='explain' and t['candidates']:
            found=self.store.get_codes([item['code'] for item in t['candidates']])
            for item in t['candidates']:
                rec=found.get(item['code'])
                if rec and rec['revision']==item['revision']: candidates.append(rec)
            if not candidates: raise DomainError('이전 후보가 변경되었습니다. 다시 검색해주세요.')
        else:
            candidates,trace=await self.gateway.search(plan.query or request.text)
        if plan.action=='draft' and self.store.namespace=='demo':
            raise DomainError('샘플 대화에서는 검색·비교·설명만 제공합니다. 정식 등록용 초안은 실제 목록에서 작성해주세요.',422)

        async def read_only_explanation(comparison):
            nonlocal ai_error
            try:
                return await self.explain(request.text,candidates,comparison)
            except DomainError as exc:
                if plan.action not in ('search','explain','compare') or exc.status not in (422,502,503,504):raise
                # Preserve independently verified DB/rule results. A rejected
                # explanation never becomes the answer or persisted history.
                ai_error={'status':exc.status,'message':exc.message}
                answer=('문구 비교는 완료했지만 AI 설명을 만들지 못했습니다. 아래 DB 원문 후보와 비교 결과를 확인해주세요.'
                        if plan.action=='compare' else
                        '검색은 완료했지만 AI 설명을 만들지 못했습니다. 아래 DB 원문 후보를 확인해주세요.')
                return answer,set()

        if plan.action=='compare':
            proposal=plan.proposed_message or (t.get('draft') or {}).get('payload',{}).get('message','')
            if not proposal:
                answer='비교할 새 문구를 입력해주세요. 기존 후보는 아래에 표시했습니다.'
            else:
                comparison=[dict(code=c['code'],**compare_message(proposal,c,menu=plan.menu,trigger=plan.trigger)) for c in candidates]
                answer,_=await read_only_explanation(comparison)
        elif plan.action=='draft':
            if plan.proposed_message:
                wording=Wording(message=plan.proposed_message,menu=plan.menu,trigger=plan.trigger,explanation='기획자가 입력한 원문을 보존한 미등록 초안입니다.')
            else:
                wording=await self.gateway.json(Wording,WRITER,{'request':request.text,'history':[{k:v for k,v in entry.items() if k in ('role','content')} for entry in t['history'][-8:]],'previous_draft':t.get('draft'),'candidates':candidates})
                constraints=request.text
                requested=signature(constraints)
                if not requested['quantities'] and not requested['placeholders'] and t.get('draft'):
                    constraints=t['draft']['payload']['message']
                self.validate_wording(constraints,wording.message)
            candidates,search_trace=await self.gateway.search(wording.message)
            trace.extend(search_trace)
            comparison=[dict(code=c['code'],**compare_message(wording.message,c,menu=wording.menu,trigger=wording.trigger)) for c in candidates]
            new_draft=wording.model_dump(); new_draft['candidates']=[{'code':c['code'],'revision':c['revision']} for c in candidates]
            answer='미등록 초안을 작성했습니다. 아래 유사 후보와 사용 조건을 검토한 뒤 등록을 요청하세요.'
            if wording.explanation: answer+='\n'+wording.explanation
        elif candidates and (plan.action=='explain' or not explicit):
            answer,cited=await read_only_explanation([])
            if plan.action=='search' and not cited and ai_error is None:
                # Citation absence does not establish that DB hits are irrelevant.
                # Keep the independently retrieved candidates and their order.
                trace.append({'name':'no_cited_candidate','count':len(candidates)})
        elif candidates:
            answer='등록된 코드의 원문을 찾았습니다. 아래 문구는 DB에 저장된 그대로입니다.'
        else:
            # Only emptiness matters here; do not load the whole catalogue.
            if not self.store.has_codes():
                answer='연결된 DB에 알림 코드가 없습니다. DB 데이터 연동 상태를 확인해주세요.' if self.store.namespace!='demo' else '샘플 목록이 비어 있습니다. 실제 목록과 샘플 목록의 상태를 확인해주세요.'
            else:
                answer='일치하는 알림 코드를 찾지 못했습니다. 코드번호나 핵심 단어로 다시 검색하거나 코드 목록에서 확인해주세요.'
        if missing: answer+='\n미등록 코드: '+', '.join(missing)
        search_info={'shown':len(candidates),'complete':bool(explicit),'quantity':None}
        from .discovery import quantity_terms,quantity_page
        if plan.action in ('search','explain') and quantity_terms(request.text):
            page=quantity_page(self.store,request.text,limit=1,version=version)
            search_info['quantity']={k:v for k,v in page.items() if k not in ('items','offset','limit','has_more')}
        result={'action':plan.action,'answer':answer,'candidates':candidates,'comparisons':comparison,'missing_codes':missing,
                'search_info':search_info,'ai_error':ai_error,'selected_code':selected,'catalog_version':version,'trace':trace,'draft':None,'ai_used':ai_error is None and (bool(new_draft) or (bool(candidates) and (plan.action in ('compare','explain') or not explicit)))}
        return self.store.finish_turn(actor,t,str(request.request_id),fingerprint,request.text,result,new_draft)
    async def explain(self,query,candidates,comparison):
        """Return (text, codes the explanation actually cited). Cited codes are always a subset of candidates."""
        if not candidates: return '관련 후보를 확인하지 못했습니다. 다른 표현으로 검색해주세요.',set()
        result=await self.gateway.json(Explanation,EXPLAINER,{'question':query,'catalog':candidates,'rule_comparison':comparison})
        allowed={c['code'] for c in candidates}
        mentioned={v.upper() for v in CODE_IN_TEXT.findall(result.text)}|{v.upper() for v in result.references}
        if not mentioned<=allowed: raise DomainError('AI 설명에 조회되지 않은 코드가 포함되어 결과를 차단했습니다. 다시 시도해주세요.',502)
        return result.text,mentioned
    @staticmethod
    def validate_wording(request,message):
        if CODE_IN_TEXT.search(message): raise DomainError('AI가 초안에 임의 코드번호를 넣어 차단했습니다.',502)
        a,b=signature(request),signature(message)
        if a['quantities']!=b['quantities'] or a['placeholders']!=b['placeholders']:
            raise DomainError('AI가 요청의 숫자·조건·변수를 바꿔 초안을 저장하지 않았습니다. 표시 문구를 직접 입력해주세요.',502)
        if a['negation'] and not b['negation']:
            raise DomainError('AI가 부정 조건을 누락해 초안을 차단했습니다.',502)
