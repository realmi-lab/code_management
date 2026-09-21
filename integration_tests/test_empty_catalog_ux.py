import pytest
from code_agent.agent import Agent
from code_agent.store import DomainError
from conftest import USER, ScriptedGateway
from test_domain import req

@pytest.mark.asyncio
async def test_empty_catalog_explains_import_and_is_not_ai_prose(store):
    gateway = ScriptedGateway(store)
    thread = store.create_thread(USER)
    result = await Agent(store, gateway).turn(USER, thread['id'], req('알림 찾아줘'))
    assert '연결된 DB에 알림 코드가 없습니다' in result['answer']
    assert 'DB 데이터 연동 상태' in result['answer']
    assert result['ai_used'] is False
    saved = store.get_thread(USER, thread['id'])
    assert saved['history'][-1]['ai_used'] is False

@pytest.mark.asyncio
async def test_missing_code_in_nonempty_catalog_is_not_empty_catalog(seeded, gateway):
    thread = seeded.create_thread(USER)
    result = await Agent(seeded, gateway).turn(USER, thread['id'], req('AT-9999'))
    assert '일치하는 알림 코드를 찾지 못했습니다' in result['answer']
    assert '연결된 DB에 알림 코드가 없습니다' not in result['answer']
    assert result['ai_used'] is False

@pytest.mark.asyncio
async def test_search_error_is_not_disguised_as_no_results(seeded, gateway):
    gateway.search_error = DomainError('검색 준비 실패', 503)
    thread = seeded.create_thread(USER)
    with pytest.raises(DomainError, match='검색 준비 실패'):
        await Agent(seeded, gateway).turn(USER, thread['id'], req('인증 알림', action='search'))
    assert seeded.get_thread(USER, thread['id'])['version'] == 0

@pytest.mark.asyncio
async def test_db_authority_approval_needs_no_excel_confirmation(seeded, gateway, monkeypatch):
    from conftest import ADMIN
    from test_domain import approval
    monkeypatch.setenv('CODE_CATALOG_AUTHORITY', 'system')
    t = seeded.create_thread(USER)
    result = await Agent(seeded, gateway).turn(USER, t['id'], req('작성', action='draft', proposed_message='새 문구'))
    approved = seeded.approve(ADMIN, result['draft']['id'], approval().model_copy(update={'external_registered': False}))
    assert approved['code'] == 'AT-2000'
