"""Wrong planner drafts must not turn read requests into writes or sample errors."""
import pytest
from code_agent.agent import Agent,requests_authoring
from code_agent.store import SampleStore,DomainError
from conftest import USER,ScriptedGateway
from test_domain import req


@pytest.mark.asyncio
@pytest.mark.parametrize('query',[
    '인증번호 전송에 성공했을 때 보여줄 문구',
    '인증을 30초 안에 끝내야 한다는 안내',
    '기존 회원 전화번호로 다시 가입하려는 경우',
    '수정 내용을 저장하지 않고 화면을 나갈 때 알림',
    '"신청서를 작성해주세요."라는 문구',
    '새로 작성하지 말고 기존 알림 찾아줘',
    '초안을 작성해달라는 알림',
])
@pytest.mark.parametrize('namespace',['demo','production'])
async def test_misclassified_lookup_discards_draft_guesses(seeded,query,namespace):
    store=SampleStore(seeded) if namespace=='demo' else seeded
    before=seeded.snapshot(True)
    gateway=ScriptedGateway(store)
    gateway.responses=[{'action':'draft','query':'잘못된 검색어','proposed_message':'AI가 만든 새 문구','menu':'추측','trigger':'추측'}]
    thread=store.create_thread(USER)
    result=await Agent(store,gateway).turn(USER,thread['id'],req(query))
    assert result['action']=='search' and result['candidates'] and result['draft'] is None
    assert ('search',query) in gateway.calls
    assert not seeded.list_drafts(USER) and seeded.snapshot(True)==before
    assert store.get_thread(USER,thread['id'])['version']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('query',[
    '인증 안내를 새로 작성해줘',
    '"문구를 작성해주세요."라는 문구로 작성해줘',
    '새 안내 만들어 주세요',
    'AT-1923 문구를 수정해줘',
])
async def test_explicit_natural_authoring_still_creates_unregistered_draft(seeded,query):
    gateway=ScriptedGateway(seeded)
    gateway.responses=[{'action':'draft','query':query}]
    thread=seeded.create_thread(USER)
    result=await Agent(seeded,gateway).turn(USER,thread['id'],req(query,proposed_message='새 안내입니다.'))
    assert result['action']=='draft' and result['draft']['payload']['message']=='새 안내입니다.'
    assert len(seeded.snapshot(True)[1])==4


@pytest.mark.asyncio
async def test_sample_explicit_natural_draft_remains_blocked(seeded):
    sample=SampleStore(seeded);gateway=ScriptedGateway(sample)
    thread=sample.create_thread(USER)
    with pytest.raises(DomainError,match='샘플 대화'):
        await Agent(sample,gateway).turn(USER,thread['id'],req('새 문구 작성해줘'))
    assert sample.get_thread(USER,thread['id'])['version']==0
    assert seeded.list_drafts(USER)==[]


@pytest.mark.parametrize('text',[
    '새 문구 작성하지 마', '새로 작성하지 말아줘', '문구 만들지 말고 설명해줘',
    '가입 정보를 수정할 때 안내', '“다시 작성해줘”라는 안내',
])
def test_negated_and_quoted_authoring_is_not_permission(text):
    assert not requests_authoring(text)
