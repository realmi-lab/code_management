import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extensions'))
import pytest
from code_agent.store import Store
from code_agent.models import Actor,ImportCommit,Plan,Wording,Explanation
from code_agent.importer import parse_upload
from code_agent.compare import compare_message

ADMIN=Actor(id=1,role='admin',name='테스트 관리자')
USER=Actor(id=2,role='user',name='테스트 기획자')
OTHER=Actor(id=3,role='user',name='다른 테스트 사용자')
# Synthetic fixture, NOT a company code list. No production seeding exists.
CSV='코드번호,등록문구,메뉴,노출조건,상태\nAT-1923,메뉴확인 30초 이후에 인증해주세요.,인증,메뉴 확인 후 30초 미경과,사용중\nAT-1924,30초 이내에 인증해주세요.,인증,인증번호 발송 후,사용중\nAT-0100,이미 가입된 번호입니다.,회원가입,휴대폰 번호 중복,사용중\nAT-0999,사용하지 않는 문구입니다.,회원가입,이전 정책,폐기\n'

def seed(s,csv=CSV):
    p=s.save_preview(ADMIN,parse_upload(csv.encode(),'synthetic.csv'))
    return s.apply_preview(ADMIN,p['id'],ImportCommit(expected_catalog_version=p['catalog_version']))

class ScriptedGateway:
    """Test double replacing ONLY external LLM/retrieval. Never loaded in production."""
    def __init__(self,store): self.store=store;self.responses=[];self.calls=[];self.search_error=None
    async def json(self,schema,system,payload):
        self.calls.append(('llm',schema.__name__,payload))
        if self.responses:
            v=self.responses.pop(0)
            if isinstance(v,Exception): raise v
            return schema.model_validate(v)
        if schema is Plan:
            msg=payload['user']
            action='draft' if any(s in msg for s in ('작성','만들')) else 'compare' if '비교' in msg else 'explain' if any(s in msg for s in ('두번째','두 번째','설명')) else 'search'
            return Plan(action=action,query=msg)
        if schema is Wording: return Wording(message='30초 이후에 다시 인증해주세요.',menu='인증',trigger='메뉴 확인 후',explanation='합성 테스트 모델의 초안입니다.')
        return Explanation(text='조회한 등록 문구를 확인했습니다. 사용 조건은 기획자가 검토해야 합니다.',references=[c['code'] for c in payload.get('catalog',[])])
    async def search(self,q):
        self.calls.append(('search',q))
        if self.search_error: raise self.search_error
        _,items=self.store.snapshot()
        return items[:8],[{'name':'TEST_DOUBLE_RETRIEVAL','count':len(items)}]

def use_list(ui,value):
    """Browser checks: the list picker lives in the AI 설정 tab; switch there and come back."""
    current=ui.locator('[role=tab][aria-selected=true]').get_attribute('data-view')
    ui.locator('[data-view=ai-settings]').click()
    ui.locator('#catalog-namespace').select_option(value)
    ui.locator(f'[data-view={current}]').click()

@pytest.fixture
def store(tmp_path):
    s=Store('sqlite:///'+str(tmp_path/'test.db'));s.initialize();yield s;s.engine.dispose()
@pytest.fixture
def seeded(store): seed(store);return store
@pytest.fixture
def gateway(seeded): return ScriptedGateway(seeded)
