"""Check explicit registered-field assertions against the referenced DB row.

This is a rejection check, not a substitute for semantic validation of free prose.
No query, code, quantity, or expected answer is special-cased.
"""
import re
from .models import CODE_IN_TEXT

FIELDS={'문구':'message','등록 문구':'message','메뉴':'menu','노출 조건':'trigger','노출조건':'trigger',
        '제목':'title','영문 제목':'title_en','영문 문구':'contents_en'}
LINE=re.compile(r'^\s*(?:[-*•]\s+)?(?P<label>[^:：\n]{1,16})\s*[:：]\s*(?P<value>.*?)\s*$')
CODE_LABELS={'메시지코드','코드','코드번호'}
WRAPPERS=(('**','**'),('__','__'),('`','`'),('"','"'),("'","'"),('“','”'),('‘','’'))


def presentation_variants(value):
    """Remove only balanced outer presentation marks, never alter field contents."""
    variants=[value.strip()]
    while variants[-1]:
        current=variants[-1]
        pair=next(((left,right) for left,right in WRAPPERS
                   if len(current)>len(left)+len(right) and current.startswith(left) and current.endswith(right)),None)
        if pair is None:break
        variants.append(current[len(pair[0]):-len(pair[1])].strip())
    return variants


def standalone_code(value):
    value=presentation_variants(value)[-1]
    return value.upper() if CODE_IN_TEXT.fullmatch(value) else None


def check_registered_fields(text,references,records):
    rows={row['code']:row for row in records if isinstance(row,dict) and 'code' in row}
    mentioned={value.upper() for value in CODE_IN_TEXT.findall(text)}|{value.upper() for value in references}
    violations=[];checked=0;code=None
    if mentioned-set(rows):violations.append({'field':'code','reason':'not_in_evidence'})
    for line in text.splitlines():
        if not line.strip():continue
        # A standalone code is an unambiguous new block; free prose mentioning
        # a code is not. Strip heading/list decoration only, not wording.
        heading=re.sub(r'^\s*(?:#{1,6}\s+|[-*•]\s+)','',line).strip()
        new_code=standalone_code(heading)
        if new_code:
            code=new_code
            continue
        line=presentation_variants(line)[-1]
        match=LINE.fullmatch(line)
        if not match:
            # Never let an earlier row leak across a prose/comparison boundary.
            # Ambiguous scope remains the semantic judges' responsibility.
            code=None
            continue
        label=match['label'].strip();value=match['value'].strip()
        # Also recognize a label whose closing markdown mark follows the colon:
        # **메시지코드:** QA-1. This changes no characters inside the value.
        for mark in ('**','__','`'):
            if label.startswith(mark) and value.startswith(mark) and label[len(mark):].strip() in CODE_LABELS|set(FIELDS):
                label=label[len(mark):].strip();value=value[len(mark):].strip()
                break
        label=presentation_variants(label)[-1]
        if label in CODE_LABELS:
            code=standalone_code(value)
            continue
        field=FIELDS.get(label)
        if field is None:
            code=None
            continue
        if code not in rows or field not in rows[code]:continue
        expected=rows[code][field]
        # A multiline field cannot be judged from a single displayed line.
        if not isinstance(expected,str) or '\n' in expected or '\r' in expected:continue
        checked+=1
        candidates=presentation_variants(value)
        if expected.strip() not in candidates:violations.append({'field':field,'reason':'different_registered_value'})
    return {'checked_fields':checked,'violations':violations}
