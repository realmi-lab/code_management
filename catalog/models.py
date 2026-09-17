from __future__ import annotations
import re
import uuid
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

Namespace = Literal['live', 'demo']
# The supplied workbook uses S-T-1 / S-A-1 / S-C-1 as well as AT-1923.
# Hyphens belong to the token: never extract T-1 from an invalid/longer S-T-1.
CODE_PATTERN = r'[A-Z][A-Z0-9_]{0,15}(?:-[A-Z][A-Z0-9_]{0,15}){0,7}-[0-9]{1,12}'
CODE_RE = re.compile('^'+CODE_PATTERN+'$')
CODE_IN_TEXT = re.compile(r'(?<![A-Za-z0-9_-])'+CODE_PATTERN+r'(?![A-Za-z0-9_-])', re.I)
CATALOG_FIELDS = ('business','message_type','purpose','title','title_en','message_en')

def canonical_code(value: str) -> str:
    code = value.strip().upper()
    if not CODE_RE.fullmatch(code):
        raise ValueError('코드번호는 AT-1923 또는 S-T-1처럼 영문 접두어와 숫자로 구성되어야 합니다. 앞자리 0은 보존됩니다.')
    return code

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class SearchRequest(Strict):
    query: str = Field(min_length=1, max_length=3000)
    namespace: Namespace = 'live'
    limit: int = Field(default=8, ge=1, le=30)
    include_retired: bool = False
    use_ai: bool = False
    menu: str = Field(default='', max_length=200)
    trigger: str = Field(default='', max_length=1000)

    @field_validator('query')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('검색어를 입력해주세요.')
        return value.strip()

class CompareRequest(SearchRequest):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator('message')
    @classmethod
    def message_not_blank(cls,value):
        if not value.strip(): raise ValueError('비교할 문구를 입력해주세요.')
        return value

class DraftRequest(Strict):
    namespace: Namespace = 'live'
    message: str = Field(min_length=1, max_length=4000)
    menu: str = Field(default='', max_length=200)
    trigger: str = Field(default='', max_length=1000)
    notes: str = Field(default='', max_length=2000)
    kind: Literal['new','revision'] = 'new'
    target_code: str | None = None
    use_ai: bool = False

    @field_validator('message')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('문구를 입력해주세요.')
        return value  # Preserve literal wording, spaces and punctuation.

class ApprovalRequest(Strict):
    namespace: Namespace = 'live'
    expected_revision: int = Field(ge=1)
    expected_catalog_version: int = Field(ge=0)
    code: str | None = None
    prefix: str | None = None
    duplicate_ack: bool = False
    reason: str = Field(min_length=1, max_length=1000)

class StatusRequest(Strict):
    namespace: Namespace = 'live'
    expected_revision: int = Field(ge=1)
    status: Literal['active','retired']
    reason: str = Field(min_length=1, max_length=1000)

class ReviewRequest(Strict):
    namespace: Namespace = 'live'
    text: str = Field(min_length=1, max_length=16000)
    include_retired: bool = True

class ImportCommit(Strict):
    skip_conflicts: bool = False
    approved_updates: list[str] = Field(default_factory=list, max_length=10000)
    update_reason: str = Field(default='', max_length=1000)
    expected_catalog_version: int = Field(ge=0)

class SearchResult(BaseModel):
    """Minimal adapter matching urstory-rag's RRF result contract."""
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    score: float
    metadata: dict = Field(default_factory=dict)

class DraftUpdate(Strict):
    namespace: Namespace = 'live'
    expected_revision: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=4000)
    menu: str = Field(default='', max_length=200)
    trigger: str = Field(default='', max_length=1000)
    notes: str = Field(default='', max_length=2000)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator('message','reason')
    @classmethod
    def not_blank(cls,value):
        if not value.strip(): raise ValueError('문구와 수정 이유를 입력해주세요.')
        return value

class ExternalLink(Strict):
    namespace: Namespace = 'live'
    expected_revision: int = Field(ge=1)
    expected_catalog_version: int = Field(ge=0)
    code: str
    reason: str = Field(min_length=1, max_length=1000)
    differences_ack: bool = False

    @field_validator('code')
    @classmethod
    def validate_code(cls,value): return canonical_code(value)

    @field_validator('reason')
    @classmethod
    def validate_reason(cls,value):
        if not value.strip(): raise ValueError('등록 확인 이유를 입력해주세요.')
        return value
