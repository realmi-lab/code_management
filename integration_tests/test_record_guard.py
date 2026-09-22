import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from code_agent.record_guard import check_registered_fields
from code_agent.models import Explanation
from code_agent.safety import GroundingError
from test_safety import safety

ROWS=[{'code':'QA-1','message':'17초 이후에 다시 요청해주세요.','menu':'전화 인증','trigger':'재요청 대기'},
      {'code':'QA-2','message':'42초 이내에 완료해주세요.','menu':'기기 인증','trigger':'완료 제한'}]

@pytest.mark.parametrize('field,value',[('문구',ROWS[1]['message']),('메뉴','기기 인증'),('노출 조건','완료 제한'),('문구','17초 이내에 다시 요청해주세요.')])
def test_another_candidate_cannot_supply_a_registered_field(field,value):
    result=check_registered_fields('메시지코드: QA-1\n'+field+': '+value,['QA-1'],ROWS)
    assert result['checked_fields']==1 and result['violations']

def test_correct_multiple_code_blocks_and_wrapped_originals():
    text='\n'.join('메시지코드: '+r['code']+'\n문구: “'+r['message']+'”\n메뉴: '+r['menu'] for r in ROWS)
    assert check_registered_fields(text,['QA-1','QA-2'],ROWS)=={'checked_fields':4,'violations':[]}

def test_free_prose_and_multiline_fields_remain_semantic_judge_work():
    rows=[dict(ROWS[0],message='첫 줄\n다음 줄')]
    result=check_registered_fields('메시지코드: QA-1\n문구: 첫 줄\n다음 줄\n대기 후 재요청하는 조건입니다.',['QA-1'],rows)
    assert result=={'checked_fields':0,'violations':[]}


@pytest.mark.parametrize('heading',['QA-2','qa-2','**QA-2**','`QA-2`','### QA-2','- QA-2'])
def test_standalone_code_header_rebinds_to_new_row(heading):
    text='메시지코드: QA-1\n문구: '+ROWS[0]['message']+'\n'+heading+'\n문구: '+ROWS[1]['message']
    assert check_registered_fields(text,['QA-1','QA-2'],ROWS)=={'checked_fields':2,'violations':[]}


def test_standalone_header_cannot_borrow_previous_rows_wording_or_quantity():
    text='메시지코드: QA-1\n문구: '+ROWS[0]['message']+'\nQA-2\n문구: '+ROWS[0]['message']
    result=check_registered_fields(text,['QA-1','QA-2'],ROWS)
    assert result['checked_fields']==2
    assert result['violations']==[{'field':'message','reason':'different_registered_value'}]


@pytest.mark.parametrize('boundary',[
    '비교 대상은 QA-2입니다.',
    '다른 코드: QA-2는 완료 제한입니다.',
    '코드: QA-1과 QA-2',
    '그 밖의 차이를 설명합니다.',
])
def test_ambiguous_prose_clears_binding_and_defers_fields_to_semantic_judges(boundary):
    text='메시지코드: QA-1\n문구: '+ROWS[0]['message']+'\n'+boundary+'\n문구: '+ROWS[1]['message']
    assert check_registered_fields(text,['QA-1','QA-2'],ROWS)=={'checked_fields':1,'violations':[]}


def test_clear_header_after_ambiguous_prose_restores_binding():
    text='메시지코드: QA-1\n비교 대상은 QA-2입니다.\n코드: QA-2\n문구: '+ROWS[0]['message']
    assert check_registered_fields(text,['QA-1','QA-2'],ROWS)['violations']


@pytest.mark.parametrize('header',['메시지코드: `QA-1`','**메시지코드:** QA-1','**메시지코드**: QA-1'])
@pytest.mark.parametrize('wording',[ROWS[0]['message'],'**'+ROWS[0]['message']+'**','`'+ROWS[0]['message']+'`'])
def test_balanced_presentation_markup_does_not_change_field_content(header,wording):
    assert check_registered_fields(header+'\n문구: '+wording,['QA-1'],ROWS)=={'checked_fields':1,'violations':[]}


@pytest.mark.parametrize('wording',['**42초 이내에 완료해주세요.**','`17초 이내에 다시 요청해주세요.`'])
def test_markup_cannot_hide_changed_number_or_direction(wording):
    result=check_registered_fields('**메시지코드:** QA-1\n문구: '+wording,['QA-1'],ROWS)
    assert result['checked_fields']==1 and result['violations']

@pytest.mark.asyncio
async def test_record_mismatch_stops_before_two_paid_judges(safety):
    llm=SimpleNamespace(generate=AsyncMock())
    with pytest.raises(GroundingError):
        await safety.validate(Explanation(text='메시지코드: QA-1\n문구: '+ROWS[1]['message'],references=['QA-1']),{'catalog':ROWS},llm)
    llm.generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('judge_passes',[True,False])
async def test_unbound_field_still_runs_both_semantic_judges(safety,judge_passes):
    text='메시지코드: QA-1\n비교 대상은 QA-2입니다.\n문구: '+ROWS[1]['message']
    assert check_registered_fields(text,['QA-1','QA-2'],ROWS)=={'checked_fields':0,'violations':[]}
    llm=SimpleNamespace(generate=AsyncMock(side_effect=[
        'faithfulness_score: 1\nverdict: FAITHFUL',
        'grounded_ratio: 1\nverdict: PASS' if judge_passes else 'grounded_ratio: 0\nverdict: FAIL']))
    result=Explanation(text=text,references=['QA-1','QA-2'])
    if judge_passes:
        await safety.validate(result,{'catalog':ROWS},llm)
    else:
        with pytest.raises(GroundingError):await safety.validate(result,{'catalog':ROWS},llm)
    assert llm.generate.await_count==2
