"""Exact quantity exploration is independent of semantic ranking and AI context."""
from decimal import Decimal
import re
from .store import DomainError

# Do not match a numeric suffix in malformed grouping (e.g. 1,00원 -> 00원).
QUANTITY = re.compile(r'(?<![\d,.+\-])([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(초|분|시간|일|회|자|원|%)')

def quantity_terms(query):
    return list(dict.fromkeys((str(Decimal(m.group(1).replace(',','')).normalize()),m.group(2)) for m in QUANTITY.finditer(query)))

def quantity_matches(record,terms):
    # Business wording and conditions only, not notes, filenames, IDs, or timestamps.
    values=quantity_terms(' '.join(str(record.get(k,'')) for k in ('message','menu','trigger')))
    return all(term in values for term in terms)

def quantity_page(store,query,offset=0,limit=20,version=None):
    terms=quantity_terms(query)
    if not terms or len(query)>4000 or offset<0 or not 1<=limit<=100:
        raise DomainError('수치와 단위를 포함한 검색 조건 및 목록 범위를 확인해주세요.',422)
    state,records=store.snapshot()
    if version is not None and state['version']!=version:
        raise DomainError('목록이 변경되었습니다. 다시 검색해주세요.',409)
    matched=[r for r in records if quantity_matches(r,terms)]
    label=' · '.join(f'{format(Decimal(n),"f")}{unit}' for n,unit in terms)
    return {'query':label,'label':label,'total':len(matched),'offset':offset,'limit':limit,
            'catalog_version':state['version'],'namespace':store.namespace,'items':matched[offset:offset+limit],
            'scope':'active_message_menu_trigger','has_more':offset+limit<len(matched)}
