from __future__ import annotations
import re
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

CODE_RE = re.compile(r'^[A-Z][A-Z0-9_]{0,15}-[0-9]{1,12}$')
CODE_IN_TEXT = re.compile(r'(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]{0,15}-[0-9]{1,12}(?![A-Za-z0-9_])')

def canonical_code(value: str) -> str:
    code=value.strip().upper()
    if not CODE_RE.fullmatch(code):
        raise ValueError('코드번호는 AT-1923처럼 접두어-숫자 형식이어야 합니다. 앞자리 0은 보존합니다.')
    return code

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Actor(Strict):
    id: int
    role: str='user'
    name: str=''

class Turn(Strict):
    request_id: uuid.UUID
    expected_version: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=4000)
    action: Literal['auto','search','compare','draft','explain']='auto'
    selected_code: str | None=None
    proposed_message: str = Field(default='',max_length=4000)
    menu: str=Field(default='',max_length=200)
    trigger: str=Field(default='',max_length=1000)
    @field_validator('text')
    @classmethod
    def nonblank(cls,v):
        if not v.strip(): raise ValueError('질문을 입력해주세요.')
        return v
    @field_validator('selected_code')
    @classmethod
    def code(cls,v): return canonical_code(v) if v else None

class Plan(Strict):
    action: Literal['search','compare','draft','explain']='search'
    query: str=Field(default='',max_length=3000)
    proposed_message: str=Field(default='',max_length=4000)
    menu: str=Field(default='',max_length=200)
    trigger: str=Field(default='',max_length=1000)

    @field_validator('query','proposed_message','menu','trigger',mode='before')
    @classmethod
    def empty_optional_text(cls,v):
        # Providers may represent an absent optional value as JSON null.
        return '' if v is None else v

class Wording(Strict):
    message: str=Field(min_length=1,max_length=4000)
    menu: str=Field(default='',max_length=200)
    trigger: str=Field(default='',max_length=1000)
    explanation: str=Field(default='',max_length=1500)
    @field_validator('menu','trigger','explanation',mode='before')
    @classmethod
    def empty_optional_text(cls,v):
        return '' if v is None else v

    @field_validator('message')
    @classmethod
    def nonblank(cls,v):
        if not v.strip(): raise ValueError('빈 문구는 저장할 수 없습니다.')
        return v

class Explanation(Strict):
    text: str=Field(min_length=1,max_length=3500)
    references: list[str]=Field(default_factory=list,max_length=20)

class ImportCommit(Strict):
    expected_catalog_version: int=Field(ge=0)
    updates: list[str]=Field(default_factory=list,max_length=10000)
    skip_conflicts: bool=False
    reason: str=Field(default='',max_length=1000)

class Approval(Strict):
    expected_catalog_version: int=Field(ge=0)
    expected_draft_revision: int=Field(ge=1)
    code: str
    reason: str=Field(min_length=1,max_length=1000)
    duplicate_ack: bool=False
    external_registered: bool=False
    @field_validator('code')
    @classmethod
    def code_valid(cls,v): return canonical_code(v)
    @field_validator('reason')
    @classmethod
    def reason_valid(cls,v):
        if not v.strip(): raise ValueError('등록 사유를 입력해주세요.')
        return v

class Revision(Strict):
    business: str | None=Field(default=None,max_length=200)
    message_type: str | None=Field(default=None,max_length=100)
    purpose: str | None=Field(default=None,max_length=1000)
    title: str | None=Field(default=None,max_length=4000)
    spelling_check: str | None=Field(default=None,max_length=1000)
    title_en: str | None=Field(default=None,max_length=4000)
    contents_en: str | None=Field(default=None,max_length=8000)
    notes: str | None=Field(default=None,max_length=4000)
    added_date: str | None=Field(default=None,max_length=10)
    expected_revision: int=Field(ge=1)
    expected_catalog_version: int=Field(ge=0)
    message: str=Field(min_length=1,max_length=4000)
    menu: str=Field(default='',max_length=200)
    trigger: str=Field(default='',max_length=1000)
    status: Literal['active','retired']='active'
    reason: str=Field(min_length=1,max_length=1000)
    @field_validator('added_date')
    @classmethod
    def valid_added_date(cls,v):
        if v:
            from datetime import date
            if date.fromisoformat(v).isoformat()!=v:raise ValueError('추가날짜는 YYYY-MM-DD 형식입니다.')
        return v
    @field_validator('title')
    @classmethod
    def valid_title(cls,v):
        if v is not None and not v.strip():raise ValueError('title은 비워둘 수 없습니다.')
        return v
    @field_validator('message','reason')
    @classmethod
    def not_blank(cls,v):
        if not v.strip(): raise ValueError('빈 값은 저장할 수 없습니다.')
        return v

class CatalogComparison(Strict):
    message: str=Field(min_length=1,max_length=4000)
    menu: str=Field(default='',max_length=200)
    trigger: str=Field(default='',max_length=1000)
    namespace: Literal['production','demo']='production'
    mode: Literal['catalog_rules','semantic']='catalog_rules'
    include_retired: bool=False
    @field_validator('message')
    @classmethod
    def nonblank(cls,v):
        if not v.strip():raise ValueError('비교할 문구를 입력해주세요.')
        return v

class DocumentReview(Strict):
    text: str=Field(min_length=1,max_length=16000)
    namespace: Literal['production','demo']='production'
    mode: Literal['catalog_rules','semantic']='catalog_rules'
    @field_validator('text')
    @classmethod
    def valid_lines(cls,v):
        lines=[line for line in v.splitlines() if line.strip()]
        if not lines or len(lines)>30:raise ValueError('검토할 문구를 1~30줄로 입력해주세요.')
        if any(len(line)>4000 for line in lines):raise ValueError('한 줄은 4,000자 이하로 입력해주세요.')
        return v

class CatalogSearchTest(Strict):
    query: str=Field(min_length=1,max_length=4000)
    namespace: Literal['production','demo']='demo'
    @field_validator('query')
    @classmethod
    def not_empty(cls,v):
        if not v.strip():raise ValueError('검색어를 입력해주세요.')
        return v
