"""Read-only catalogue comparison and line review, with explicit retrieval modes.

Rule matching is a user-selected feature, never a fallback for semantic search.
Bundled GitHub examples are separate from the production database and index.
"""
from pathlib import Path
import hashlib,json,re
from .models import CODE_IN_TEXT
from .compare import compare_message,normalized,similarity
from .store import DomainError


def sample_records():
    directory=Path(__file__).parent/'data'
    raw=(directory/'sample_catalog_300.json').read_bytes()
    provenance=json.loads((directory/'sample_catalog_300.provenance.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=provenance['sha256']:
        raise DomainError('샘플 원본 검증에 실패했습니다.',503)
    from .catalog_schema import normalized_record
    records=[]
    for item in json.loads(raw):
        meta=item.pop('_meta',{})
        records.append(normalized_record(dict(item,**meta)))
    return records


def snapshot(store,namespace,retired=True):
    if namespace=='demo':
        from .store import SampleStore
        return SampleStore(store).snapshot(retired)
    return store.snapshot(retired)


async def inspect_message(store,gateway,body,catalog=None):
    # catalog=(state,records) lets a multi-line review reuse ONE snapshot
    # instead of reloading the whole table per line.
    state,records=catalog if catalog is not None else snapshot(store,body.namespace,True)
    by_code={r['code']:r for r in records}
    explicit=list(dict.fromkeys(c.upper() for c in CODE_IN_TEXT.findall(body.message)))
    if len(explicit)>20: raise DomainError('한 줄에 코드 20개 이하로 입력해주세요.',422)
    missing=[code for code in explicit if code not in by_code]
    proposal=CODE_IN_TEXT.sub('',body.message).strip(' \t\n:：-–—|') if explicit else body.message
    if proposal.startswith(('"','“')) and proposal.endswith(('"','”')):proposal=proposal[1:-1]
    if explicit:
        candidates=[by_code[c] for c in explicit if c in by_code]
        mode='exact_lookup'
    elif body.mode=='semantic':
        candidates,_=await gateway.search(body.message)
        mode='semantic'
    else:
        ranked=[]
        terms=re.findall(r'[가-힣A-Za-z0-9]+',body.message.casefold())
        # Ranking needs only the similarity ratio; full rule comparison runs on the top 8 below.
        wanted=normalized(body.message)
        for rec in records:
            if rec['status']=='retired' and not body.include_retired:continue
            target=' '.join([rec['message'],rec.get('menu',''),rec.get('trigger','')]).casefold()
            overlap=sum(term in target for term in terms)/max(1,len(terms))
            score=max(similarity(wanted,normalized(rec['message'])),overlap)
            if score>=.2:ranked.append((score,rec))
        candidates=[rec for _,rec in sorted(ranked,key=lambda pair:(-pair[0],pair[1]['code']))[:8]]
        mode='catalog_rules'
    comparisons=[dict(code=rec['code'],**compare_message(proposal,rec,menu=body.menu,trigger=body.trigger)) for rec in candidates] if proposal else []
    if body.namespace=='production' and store.status()['version']!=state['version']:
        raise DomainError('검토 중 목록이 변경되었습니다. 다시 검토해주세요.')
    return {'candidates':candidates,'comparisons':comparisons,'missing_codes':missing,'catalog_version':state['version'],
            'namespace':body.namespace,'mode':mode,'summary':('미등록 코드: '+', '.join(missing)) if missing else '등록 원문과 조건을 확인하세요.' if candidates else '관련 후보가 없습니다.',
            'notice':'합성 예시 · 실제 회사 목록 아님' if body.namespace=='demo' else '현재 등록 목록 기준 · 재사용 확정은 별도 검토'}
