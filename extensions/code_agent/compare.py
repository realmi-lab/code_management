"""Conservative reusable-message checks; never equate similarity with policy equality."""
from __future__ import annotations
import re
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher
from functools import lru_cache

PLACEHOLDER = re.compile(r'\$\{[^{}]+\}|\{\{[^{}]+\}\}|\{[^{}]+\}|%(?:\d+\$)?[sdif]')
QUANTITY = re.compile(r'(\d+(?:\.\d+)?)\s*(초|분|시간|일|회|자|원|%)')
OPERATORS = [('after',r'이후|뒤|후'),('within',r'이내|안에'),('lt',r'미만'),('lte',r'이하'),('gt',r'초과'),('gte',r'이상')]
# Precompiled once: signature() runs for every candidate in every comparison.
_OPERATOR_AFTER = [(name,re.compile(r'\s*(?:'+pat+r')')) for name,pat in OPERATORS]
_OPERATOR_ANY = [(name,re.compile(pat)) for name,pat in OPERATORS]
_NON_WORD = re.compile(r'[^a-z0-9가-힣{}%$]+')
_NEGATION = re.compile(r'불가|불가능|할 수 없|사용할 수 없|안 됩니다|안됩니다|금지|허용되지|차단|취소할 수 없')
_UNITS = {'초':('time',1),'분':('time',60),'시간':('time',3600),'일':('time',86400)}

@lru_cache(maxsize=8192)
def normalized(text):
    text = unicodedata.normalize('NFKC',text).lower()
    return _NON_WORD.sub('',text)

def signature(text):
    # Pure function of the text; cached, returned as a fresh dict so callers may mutate it.
    quantities,operators,placeholders,negation = _signature(text)
    return {'quantities':list(quantities),'operators':list(operators),
            'placeholders':list(placeholders),'negation':negation}

@lru_cache(maxsize=8192)
def _signature(text):
    units = _UNITS
    quantities = []
    operators = set()
    # Keep number-to-operator relationship, so swapping two time conditions is not a match.
    for m in QUANTITY.finditer(text):
        unit,factor = units.get(m.group(2),(m.group(2),1))
        tail = text[m.end():m.end()+8]
        op = next((name for name,pat in _OPERATOR_AFTER if pat.match(tail)), '')
        value = str((Decimal(m.group(1))*factor).normalize())
        quantities.append((unit,value,op))
        if op:
            operators.add(op)
    if not quantities:
        for name,pat in _OPERATOR_ANY:
            if pat.search(text):
                operators.add(name)
    negation = bool(_NEGATION.search(text))
    return (tuple(sorted(quantities)),tuple(sorted(operators)),
            tuple(sorted(PLACEHOLDER.findall(text))),negation)

def compare_message(message, existing, *, menu='', trigger=''):
    a,b = signature(message),signature(existing['message'])
    warnings=[]
    if a['quantities'] and b['quantities']:
        numeric_a=sorted((u,v) for u,v,_ in a['quantities'])
        numeric_b=sorted((u,v) for u,v,_ in b['quantities'])
        if numeric_a!=numeric_b:
            warnings.append('명시된 시간·숫자·단위가 다릅니다.')
        elif all(op for _,_,op in a['quantities']+b['quantities']) and a['quantities']!=b['quantities']:
            warnings.append('수치별 적용 조건이 다릅니다.')
    if a['operators'] and b['operators'] and a['operators'] != b['operators']:
        warnings.append('이후/이내/이상/미만 등의 조건 방향이 다릅니다.')
    if a['placeholders'] != b['placeholders']:
        warnings.append('문구의 변수(자리표시자)가 다릅니다.')
    if a['negation'] != b['negation']:
        warnings.append('가능/불가 등 부정 표현이 달라 의미가 반대일 수 있습니다.')
    if bool(a['quantities']) != bool(b['quantities']):
        warnings.append('한쪽 문구에만 수치 조건이 명시되어 있습니다.')
    if trigger:
        ta,tb = signature(trigger),signature(existing.get('trigger',''))
        if ta['quantities'] and tb['quantities'] and ta['quantities'] != tb['quantities']:
            warnings.append('입력한 노출 조건의 수치와 기존 노출 조건이 다릅니다.')
    literal_equal = message == existing['message']
    norm_a,norm_b = normalized(message),normalized(existing['message'])
    wording_equal = norm_a == norm_b
    ratio=similarity(norm_a,norm_b)
    context_equal = bool(menu and trigger and existing.get('menu') and existing.get('trigger')) and (
       normalized(menu)==normalized(existing['menu']) and normalized(trigger)==normalized(existing['trigger']))
    if existing['status']=='retired':
        verdict='retired'; label='폐기된 코드 · 재사용 제외'
    elif warnings:
        verdict='different_conditions'; label='유사하지만 조건이 다름'
    elif wording_equal and context_equal:
        verdict='reuse_candidate'; label='문구·명시 조건 일치 후보'
    elif wording_equal:
        verdict='same_wording'; label='같은 문구 · 사용 조건 확인'
    else:
        verdict='similar'; label='관련 후보 · 사용 조건 확인'
    if not context_equal and not warnings and existing['status']!='retired':
        warnings.append('문구 유사성만으로 재사용을 확정하지 않습니다. 메뉴와 노출 조건을 확인해주세요.')
    return {'verdict':verdict,'label':label,'differences':warnings,
            'literal_equal':literal_equal,'wording_equal':wording_equal,
            'similarity':ratio,'input_signature':a,'existing_signature':b}


@lru_cache(maxsize=16384)
def similarity(a,b):
    """Rounded ratio of two normalized() strings; the rounding is part of ranking ties."""
    return round(SequenceMatcher(None,a,b,autojunk=False).ratio(),4)


def prioritize_waiting(query,records):
    """Order retrieved candidates by explicit timing; does not add search results."""
    requested=signature(query)
    if requested['operators'] or not re.search(r'기다리|대기|지나야',query):return records
    quantities={(unit,value) for unit,value,_ in requested['quantities']}
    def priority(rec):
        candidate=signature(rec['message'])
        values={(unit,value) for unit,value,_ in candidate['quantities']}
        time_match=not quantities or quantities<=values
        direction=1 if 'after' in candidate['operators'] else -1 if 'within' in candidate['operators'] else 0
        retry_penalty=int('다시' in rec['message'] and not re.search(r'다시|재시도|재발송',query))
        return (time_match,direction,-retry_penalty)
    return sorted(records,key=priority,reverse=True)
