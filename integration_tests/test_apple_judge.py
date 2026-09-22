"""Apple on-device judge transport: env routing, schema-forced requests, strict rendering, fail-closed."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from openai import AsyncOpenAI
from code_agent import ai_config, apple_judge, provider
from code_agent.routing import JudgeLLM, RoutingLLM
from code_agent.safety import GroundingError, StrictJudge
from code_agent.store import DomainError
from test_ai_settings import config_path, body
from test_provider import patched_source
from test_provider_routing import native_modules

FAITH_PROMPT = '다음 문서와 답변을 비교하세요.\n\n다음 형식으로 정확히 응답하세요:\nfaithfulness_score: 원문 충실도 점수 (0.0 ~ 1.0)\ndistortions: 왜곡된 항목 목록\nverdict: FAITHFUL 또는 UNFAITHFUL'
GROUND_PROMPT = '다음 문서와 답변을 비교하세요.\n\n다음 형식으로 정확히 응답하세요:\ngrounded_ratio: 비율 (0.0 ~ 1.0)\nungrounded_claims: 목록\nverdict: PASS 또는 FAIL'
GOOD = {'distortions': [], 'faithfulness_score': 1.0, 'verdict': 'FAITHFUL'}


@pytest.fixture
def apple(monkeypatch, config_path):
    monkeypatch.setenv('CODE_LLM_JUDGE_PROVIDER', 'apple')
    monkeypatch.setenv('CODE_APPLE_BRIDGE_TOKEN', 'synthetic-bridge-token')
    for key in ('CODE_LLM_JUDGE_MODEL', 'CODE_LLM_JUDGE_BASE_URL', 'CODE_LLM_JUDGE_REASONING_EFFORT'):
        monkeypatch.delenv(key, raising=False)
    return config_path


def bridge(monkeypatch, reply, status=200):
    """Bind the SDK client used by AppleJudge to a mock bridge; return the captured requests."""
    seen = []

    def respond(request):
        seen.append({'headers': dict(request.headers), 'json': json.loads(request.content), 'url': str(request.url)})
        if status != 200:
            return httpx.Response(status, json={'error': {'message': 'synthetic', 'type': 'server_error', 'code': 'x'}})
        content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return httpx.Response(200, json={'id': 'chatcmpl-test', 'object': 'chat.completion', 'created': 0, 'model': 'apple/on-device',
                                         'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}]})
    monkeypatch.setattr(apple_judge, 'AsyncOpenAI',
                        lambda **kw: AsyncOpenAI(**kw, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))))
    return seen


def test_apple_judge_options_default_model_and_bridge_url(apple, monkeypatch):
    options = provider.judge_options()
    assert options == {'provider': 'apple', 'model': provider.APPLE_JUDGE_MODEL, 'base_url': provider.APPLE_BRIDGE_URL}
    assert provider.judge_configured() and provider.judge_provider() == 'apple'
    settings = provider.public_settings()
    assert settings['judge_provider'] == 'apple' and settings['judge_model'] == 'apple/on-device'
    assert settings['provider'] == 'openai' and settings['model'] == ai_config.MODELS['openai']
    monkeypatch.setenv('CODE_LLM_JUDGE_BASE_URL', 'http://127.0.0.1:9/v1')
    assert provider.judge_options()['base_url'] == 'http://127.0.0.1:9/v1'
    monkeypatch.setenv('CODE_LLM_JUDGE_BASE_URL', 'ftp://bridge')
    with pytest.raises(ValueError):
        provider.judge_options()
    monkeypatch.delenv('CODE_LLM_JUDGE_BASE_URL')
    monkeypatch.setenv('CODE_LLM_JUDGE_PROVIDER', 'siri')
    with pytest.raises(ValueError):
        provider.judge_options()
    monkeypatch.delenv('CODE_LLM_JUDGE_PROVIDER')
    # Without the provider the judge shares the generation provider, as before.
    assert provider.judge_options() == {} and provider.public_settings()['judge_provider'] == 'openai'


@pytest.mark.asyncio
async def test_apple_judge_sends_schema_and_renders_strict_lines(apple, monkeypatch):
    seen = bridge(monkeypatch, GOOD)
    result = await apple_judge.AppleJudge().generate(FAITH_PROMPT)
    assert result == 'faithfulness_score: 1.00\ndistortions: 없음\nverdict: FAITHFUL'
    request = seen[-1]
    assert request['url'].startswith(provider.APPLE_BRIDGE_URL) and request['headers']['authorization'] == 'Bearer synthetic-bridge-token'
    sent = request['json']
    assert sent['model'] == 'apple/on-device' and sent['temperature'] == 0 and 'reasoning_effort' not in sent
    assert sent['messages'] == [{'role': 'user', 'content': FAITH_PROMPT}]
    schema = sent['response_format']['json_schema']
    assert sent['response_format']['type'] == 'json_schema' and schema['name'] == 'faithfulness_judgement'
    assert schema['schema']['required'] == ['distortions', 'faithfulness_score', 'verdict']
    assert schema['schema']['properties']['verdict']['enum'] == ['FAITHFUL', 'UNFAITHFUL']
    judge = StrictJudge(SimpleNamespace(generate=AsyncMock(return_value=result)), 'faithfulness_score', {'FAITHFUL', 'UNFAITHFUL'})
    assert await judge.generate('synthetic') == result
    # A grounding prompt selects the other schema, and a failing verdict is rendered so StrictJudge blocks it.
    seen = bridge(monkeypatch, {'ungrounded_claims': ['인증번호는\n이메일로 전송됩니다.'], 'grounded_ratio': 0.5, 'verdict': 'FAIL'})
    rendered = await apple_judge.AppleJudge().generate(GROUND_PROMPT)
    assert rendered == 'grounded_ratio: 0.50\nungrounded_claims: 인증번호는 이메일로 전송됩니다.\nverdict: FAIL'
    assert seen[-1]['json']['response_format']['json_schema']['name'] == 'grounding_judgement'
    with pytest.raises(GroundingError):
        await StrictJudge(SimpleNamespace(generate=AsyncMock(return_value=rendered)), 'grounded_ratio', {'PASS', 'FAIL'}).generate('synthetic')


@pytest.mark.asyncio
@pytest.mark.parametrize('reply', ['not json', {'faithfulness_score': 1.5, 'distortions': [], 'verdict': 'FAITHFUL'},
                                   {'faithfulness_score': 0.9, 'distortions': [], 'verdict': 'MAYBE'},
                                   {'distortions': [], 'verdict': 'FAITHFUL'}, {'faithfulness_score': 0.9, 'distortions': 'x', 'verdict': 'FAITHFUL'}, ''])
async def test_apple_judge_malformed_payload_fails_closed(apple, monkeypatch, reply):
    bridge(monkeypatch, reply)
    with pytest.raises(DomainError) as error:
        await apple_judge.AppleJudge().generate(FAITH_PROMPT)
    assert error.value.status == 502


@pytest.mark.asyncio
async def test_apple_judge_bridge_errors_fail_closed_without_fallback(apple, monkeypatch):
    bridge(monkeypatch, GOOD, status=500)
    with pytest.raises(DomainError) as error:
        await apple_judge.AppleJudge().generate(FAITH_PROMPT)
    assert error.value.status == 502
    monkeypatch.setenv('CODE_LLM_JUDGE_BASE_URL', 'http://127.0.0.1:9/v1')
    monkeypatch.setattr(apple_judge, 'AsyncOpenAI', lambda **kw: AsyncOpenAI(**{**kw, 'max_retries': 0}))
    with pytest.raises(DomainError) as error:
        await apple_judge.AppleJudge().generate(FAITH_PROMPT)
    assert error.value.status == 503 and '브리지' in error.value.message


@pytest.mark.asyncio
async def test_non_judge_prompt_returns_free_text_without_schema(apple, monkeypatch):
    seen = bridge(monkeypatch, 'free text')
    assert await apple_judge.AppleJudge().generate('요약해줘', system_prompt='간단히') == 'free text'
    assert 'response_format' not in seen[-1]['json']
    assert seen[-1]['json']['messages'][0] == {'role': 'system', 'content': '간단히'}


@pytest.mark.asyncio
async def test_judge_llm_routes_to_apple_and_generation_stays_on_provider(apple, patched_source, monkeypatch):
    original, _ = native_modules(monkeypatch, patched_source)
    payloads = []

    def response(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'synthetic',
                                         'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '생성 결과'}, 'finish_reason': 'stop'}],
                                         'usage': {'prompt_tokens': 7, 'completion_tokens': 5, 'total_tokens': 12}})
    monkeypatch.setattr(original, 'AsyncOpenAI', lambda **kw: AsyncOpenAI(**kw, http_client=httpx.AsyncClient(transport=httpx.MockTransport(response))))
    seen = bridge(monkeypatch, GOOD)
    ai_config.save(body('commandcode', version=0, key='synthetic-commandcode'), 1)
    judge = JudgeLLM()
    assert judge.model == 'apple/on-device'
    assert await judge.generate(FAITH_PROMPT) == 'faithfulness_score: 1.00\ndistortions: 없음\nverdict: FAITHFUL'
    assert len(seen) == 1 and payloads == [] and judge.last_usage is None
    assert await RoutingLLM().generate('생성 질문') == '생성 결과'
    assert payloads[-1]['model'] == ai_config.MODELS['commandcode'] and payloads[-1]['reasoning_effort'] == 'high'
    assert len(seen) == 1
    settings = provider.public_settings()
    assert settings['provider'] == 'commandcode' and settings['judge_provider'] == 'apple' and settings['judge_model'] == 'apple/on-device'


ROWS = [{'code': 'EX-0104', 'message': '30초 이내에 인증을 완료해주세요.', 'menu': '기기 인증', 'trigger': '인증 시작 후 완료 제한시간 안내',
         'notes': '합성 예시', 'status': 'active', 'revision': 1, 'source': {'kind': 'demo'}},
        {'code': 'EX-0101', 'message': '인증번호를 발송했습니다.', 'menu': '휴대폰 인증', 'trigger': '인증번호 전송 성공'}]
EVIDENCE = {'question': '인증을 30초 안에 끝내야 한다는 안내', 'catalog': ROWS, 'rule_comparison': []}
GOOD_TEXT = '메시지코드: EX-0104\n문구: 30초 이내에 인증을 완료해주세요.\n메뉴: 기기 인증\n노출 조건: 인증 시작 후 완료 제한시간 안내'


def real_prompt(field, answer, evidence=EVIDENCE):
    """Rebuild the pinned upstream judge templates around a JSON answer and JSON evidence."""
    documents = json.dumps(evidence, ensure_ascii=False)
    if isinstance(answer, str):
        answer = {'text': answer, 'references': ['EX-0104']}
    tail = ('특히 다음 항목을 집중 확인하세요:\n1. 숫자\n\n다음 형식으로 정확히 응답하세요:\nfaithfulness_score: 점수\ndistortions: 목록\nverdict: FAITHFUL 또는 UNFAITHFUL'
            if field == 'faithfulness_score' else '다음 형식으로 정확히 응답하세요:\ngrounded_ratio: 비율\nungrounded_claims: 목록\nverdict: PASS 또는 FAIL')
    return f'다음 검색된 문서와 생성된 답변을 비교하세요.\n\n검색된 문서:\n{documents}\n\n생성된 답변:\n{json.dumps(answer, ensure_ascii=False)}\n\n{tail}'


@pytest.mark.asyncio
async def test_decomposed_judge_confirms_verbatim_lines_without_calling_the_model(apple, monkeypatch):
    seen = bridge(monkeypatch, {'judgements': []})
    judge = apple_judge.AppleJudge()
    result = await judge.generate(real_prompt('faithfulness_score', GOOD_TEXT))
    assert result == 'faithfulness_score: 1.00\ndistortions: 없음\nverdict: FAITHFUL'
    assert seen == [] and judge.last_detail == {'claims': 5, 'supported': 5, 'model_checked': 0, 'model_calls': 0}
    assert await StrictJudge(SimpleNamespace(generate=AsyncMock(return_value=result)), 'faithfulness_score', {'FAITHFUL', 'UNFAITHFUL'}).generate('x') == result
    grounded = await apple_judge.AppleJudge().generate(real_prompt('grounded_ratio', GOOD_TEXT))
    assert grounded == 'grounded_ratio: 1.00\nungrounded_claims: 없음\nverdict: PASS' and seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize('text,expected', [
    (GOOD_TEXT.replace('메뉴: 기기 인증', '메뉴: 휴대폰 인증'), '원문: 기기 인증 → 답변: 휴대폰 인증'),
    (GOOD_TEXT.replace('30초 이내에 인증을 완료해주세요.', '30초 안에 인증을 끝내 주세요.'), '원문: 30초 이내에 인증을 완료해주세요. → 답변: 30초 안에 인증을 끝내 주세요.'),
    (GOOD_TEXT.replace('EX-0104', 'EX-0999'), '문서에 없는 코드: EX-0999'),
])
async def test_decomposed_judge_blocks_original_mismatches_deterministically(apple, monkeypatch, text, expected):
    seen = bridge(monkeypatch, {'judgements': []})
    result = await apple_judge.AppleJudge().generate(real_prompt('faithfulness_score', text))
    assert result.endswith('verdict: UNFAITHFUL') and expected in result and seen == []
    with pytest.raises(GroundingError):
        await StrictJudge(SimpleNamespace(generate=AsyncMock(return_value=result)), 'faithfulness_score', {'FAITHFUL', 'UNFAITHFUL'}).generate('x')
    grounded = await apple_judge.AppleJudge().generate(real_prompt('grounded_ratio', text))
    assert grounded.endswith('verdict: FAIL') and seen == []


@pytest.mark.asyncio
async def test_decomposed_judge_asks_model_only_for_free_text_and_fails_closed(apple, monkeypatch):
    text = GOOD_TEXT + '\n인증번호는 이메일로 전송됩니다.'
    seen = bridge(monkeypatch, {'judgements': [{'index': 1, 'supported': False}]})
    judge = apple_judge.AppleJudge()
    result = await judge.generate(real_prompt('grounded_ratio', text))
    assert result == 'grounded_ratio: 0.83\nungrounded_claims: 인증번호는 이메일로 전송됩니다.\nverdict: FAIL'
    assert len(seen) == 1 and judge.last_detail == {'claims': 6, 'supported': 5, 'model_checked': 1, 'model_calls': 1}
    sent = seen[-1]['json']
    assert sent['response_format']['json_schema']['name'] == 'claim_support'
    shape=sent['response_format']['json_schema']['schema']['properties']['judgements']
    assert shape['minItems'] == shape['maxItems'] == 1
    asked = sent['messages'][-1]['content']
    assert '1. 인증번호는 이메일로 전송됩니다.' in asked and '2. ' not in asked
    # The model sees Korean-labelled evidence, not raw JSON keys.
    assert '문구: 30초 이내에 인증을 완료해주세요.' in asked and '메시지코드: EX-0104' in asked and '"message"' not in asked
    bridge(monkeypatch, {'judgements': [{'index': 1, 'supported': True}]})
    assert await apple_judge.AppleJudge().generate(real_prompt('grounded_ratio', text)) == 'grounded_ratio: 1.00\nungrounded_claims: 없음\nverdict: PASS'
    # A sentence the model did not answer counts as unsupported.
    bridge(monkeypatch, {'judgements': []})
    assert (await apple_judge.AppleJudge().generate(real_prompt('faithfulness_score', text))).endswith('verdict: UNFAITHFUL')
    bridge(monkeypatch, 'not json')
    with pytest.raises(DomainError) as error:
        await apple_judge.AppleJudge().generate(real_prompt('faithfulness_score', text))
    assert error.value.status == 502


@pytest.mark.asyncio
async def test_decomposed_judge_handles_draft_payloads_against_the_request(apple, monkeypatch):
    seen = bridge(monkeypatch, {'judgements': [{'index': 1, 'supported': True}]})
    answer = {'message': '비밀번호는 8자 이상 입력해주세요.', 'menu': '회원가입', 'trigger': '', 'explanation': '비밀번호 정책 확인 필요'}
    evidence = {'request': "회원가입 메뉴에 '비밀번호는 8자 이상 입력해주세요.' 문구 초안 작성", 'history': [], 'previous_draft': None, 'candidates': ROWS}
    judge = apple_judge.AppleJudge()
    result = await judge.generate(real_prompt('grounded_ratio', answer, evidence))
    assert result == 'grounded_ratio: 1.00\nungrounded_claims: 없음\nverdict: PASS'
    assert judge.last_detail == {'claims': 3, 'supported': 3, 'model_checked': 1, 'model_calls': 1}
    assert '1. 설명: 비밀번호 정책 확인 필요' in seen[-1]['json']['messages'][-1]['content']


@pytest.mark.asyncio
@pytest.mark.parametrize('judgements', [
    [{'index': 1, 'supported': True}, {'index': 1, 'supported': False}],
    [{'index': True, 'supported': True}],
    [{'index': 2, 'supported': True}],
    [{'index': 1, 'supported': 'true'}],
])
async def test_decomposed_judge_rejects_ambiguous_claim_results(apple, monkeypatch, judgements):
    bridge(monkeypatch, {'judgements': judgements})
    with pytest.raises(DomainError) as error:
        await apple_judge.AppleJudge().generate(real_prompt('grounded_ratio', GOOD_TEXT + '\n이메일 인증 화면에서도 표시됩니다.'))
    assert error.value.status == 502


@pytest.mark.asyncio
async def test_judge_exposes_deterministic_counts(apple, monkeypatch):
    seen = bridge(monkeypatch, {'judgements': []})
    judge = JudgeLLM()
    await judge.generate(real_prompt('grounded_ratio', GOOD_TEXT))
    assert judge.last_detail == {'claims': 5, 'supported': 5, 'model_checked': 0, 'model_calls': 0}
    assert seen == []


@pytest.mark.asyncio
async def test_question_cannot_literally_validate_unsupported_answer(apple,monkeypatch):
    seen=bridge(monkeypatch,{'judgements':[{'index':1,'supported':False}]})
    evidence={**EVIDENCE,'question':'이 알림은 이메일 인증 화면에서도 표시됩니다.'}
    result=await apple_judge.AppleJudge().generate(real_prompt('grounded_ratio','이 알림은 이메일 인증 화면에서도 표시됩니다.',evidence))
    assert 'FAIL' in result and seen
    prompt=seen[0]['json']['messages'][0]['content']
    assert prompt.count('이 알림은 이메일 인증 화면에서도 표시됩니다.')==1
