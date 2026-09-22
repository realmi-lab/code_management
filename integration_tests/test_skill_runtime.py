"""Real gateway/safety wiring with synthetic evidence and scripted model IO.

These tests prove transport, local guards and telemetry contracts, not model
understanding of compact evidence or live-provider answer quality.
"""
import copy
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.dont_write_bytecode = True  # The pinned upstream tree stays immutable.

from code_agent.evidence import decode_evidence
from code_agent.gateway import UrstoryGateway
from code_agent.models import Explanation
from code_agent.operations import TrackedLLM, turn_trace
from code_agent.safety import CatalogSafety, GroundingError
from code_agent.skillbook import instructions


def evidence():
    rows = [
        {'code': f'TEST-{i:04}', 'message': '인증을 30초 이후에 완료해주세요.',
         'menu': '본인인증', 'trigger': '메뉴 확인 후 대기', 'revision': 1,
         'status': 'active', 'id': i, 'updated_at': 'synthetic-only',
         'source': {'catalog_fields': {'title': '', 'notes': 'runner@example.com / 010-1234-5678',
                                      'empty': None, 'enabled': False, 'values': [0, '']}},
         'catalog_fields': {'title_en': '', 'contents_en': ''}}
        for i in range(25)
    ]
    rows[1]['message'] = '인증을 60초 이후에 완료해주세요.'
    return {'question': 'PRIVATE-QUESTION: 인증 조건을 찾아줘 runner@example.com',
            'catalog': rows, 'rule_comparison': []}


def explanation(message='인증을 30초 이후에 완료해주세요.'):
    return Explanation(text='메시지코드: TEST-0000\n문구: ' + message + '\n메뉴: 본인인증\n노출 조건: 메뉴 확인 후 대기',
                       references=['TEST-0000'])


class ScriptedModels:
    """One deterministic transport captures actual production-generated prompts."""
    model = 'synthetic-model'

    def __init__(self, generated=None):
        self.generated = list(generated or [explanation().model_dump_json()])
        self.calls = []
        self.last_usage = None
        self.client = SimpleNamespace(close=AsyncMock())

    async def generate(self, prompt, system_prompt=None):
        from code_agent.apple import _response_schema
        if prompt.startswith('다음 검색된 문서와 생성된 답변을 비교하세요.'):
            stage = 'faithfulness' if 'faithfulness_score:' in prompt else 'grounding'
            result = ('faithfulness_score: 1.0\ndistortions: []\nverdict: FAITHFUL' if stage == 'faithfulness'
                      else 'grounded_ratio: 1.0\nungrounded_claims: []\nverdict: PASS')
        else:
            stage = 'generation'
            assert self.generated, 'Unexpected model call (including unexpected input-check calls)'
            result = self.generated.pop(0)
        self.calls.append({'stage': stage, 'prompt': prompt, 'system': system_prompt,
                           'schema': copy.deepcopy(_response_schema.get())})
        # Deliberately synthetic returned counts; no token estimate or real call.
        self.last_usage = {'prompt_tokens': 111, 'completion_tokens': 22, 'total_tokens': 133,
                           'completion_tokens_details': {'reasoning_tokens': 11}}
        return result


@pytest.fixture
def runtime(monkeypatch):
    root = Path(__file__).resolve().parents[1] / 'upstream/backend'
    if not root.exists():
        pytest.skip('Pinned upstream required')
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setattr('code_agent.provider.selected_provider', lambda: 'commandcode')
    monkeypatch.setattr('code_agent.provider.judge_provider', lambda: None)
    monkeypatch.setattr('code_agent.provider.judge_configured', lambda: False)
    return CatalogSafety()


def gateway(safety, models):
    instance = UrstoryGateway(None)
    instance._safety_instance = safety
    instance._llm = AsyncMock(return_value=models)
    return instance


def document_text(call):
    return call['prompt'].split('검색된 문서:\n', 1)[1].split('\n\n생성된 답변:', 1)[0]


def metrics(caplog):
    return json.loads(next(record.message.split('catalog_turn_metrics ', 1)[1] for record in caplog.records
                           if record.message.startswith('catalog_turn_metrics ')))


@pytest.mark.asyncio
@pytest.mark.parametrize('skill_id', ['search_explanation', 'compare'])
async def test_sanitized_complete_evidence_reaches_generation_both_judges_and_skill_metrics(runtime, monkeypatch, caplog, skill_id):
    from app.services.guardrails.injection import PromptInjectionDetector
    original_detect = PromptInjectionDetector.detect
    checked_inputs = []

    async def observe_input(self, text):
        checked_inputs.append(json.loads(text))
        return await original_detect(self, text)

    monkeypatch.setattr(PromptInjectionDetector, 'detect', observe_input)
    original_validate = runtime.validate
    validation_inputs = []

    async def observe_validation(result, data, llm):
        validation_inputs.append(copy.deepcopy(data))
        return await original_validate(result, data, llm)

    monkeypatch.setattr(runtime, 'validate', observe_validation)
    raw = evidence()
    if skill_id == 'compare':
        from code_agent.compare import compare_message
        raw['rule_comparison'] = [dict(code=raw['catalog'][0]['code'],
                                      **compare_message('인증을 30초 이내에 완료해주세요.', raw['catalog'][0]))]
    untouched = copy.deepcopy(raw)
    sanitized = runtime.redact(raw)
    models = ScriptedModels()
    with caplog.at_level(logging.INFO), turn_trace(None, 1, 'synthetic-thread', 'synthetic-request'):
        result = await gateway(runtime, models).json(Explanation, instructions(skill_id), raw)

    assert result == explanation()
    assert raw == untouched
    assert checked_inputs == validation_inputs == [sanitized]
    generated = next(call for call in models.calls if call['stage'] == 'generation')
    assert json.loads(generated['prompt'])['encoding'] == 'columns-rows'
    assert decode_evidence(generated['prompt']) == sanitized
    assert 'runner@example.com' not in generated['prompt'] and '010-1234-5678' not in generated['prompt']
    assert len(decode_evidence(generated['prompt'])['catalog']) == 25
    judges = [call for call in models.calls if call['stage'] != 'generation']
    assert {call['stage'] for call in judges} == {'faithfulness', 'grounding'}
    assert document_text(judges[0]) == document_text(judges[1])
    grounded = {'catalog': sanitized['catalog'], 'rule_comparison': sanitized['rule_comparison']}
    assert all(decode_evidence(document_text(call)) == grounded for call in judges)
    assert all('PRIVATE-QUESTION' not in document_text(call) for call in judges)
    event = metrics(caplog)
    assert event['thread_id'] == 'synthetic-thread' and event['request_id'] == 'synthetic-request'
    assert [call['skill'] for call in event['calls'] if call['stage'] == 'Explanation'] == [skill_id + '@1.0.1']
    assert [call['skill'] for call in event['calls'] if call['stage'].startswith('Explanation/')] == ['verification@1.0.0'] * 2
    assert all(call['usage']['total_tokens'] == 133 for call in event['calls'])
    assert 'PRIVATE-QUESTION' not in caplog.text and 'runner@example.com' not in caplog.text
    models.client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cross_code_registered_value_is_blocked_before_judges_then_corrected_answer_uses_both(runtime, monkeypatch):
    from code_agent import record_guard
    original = record_guard.check_registered_fields
    events = []

    def observe_guard(*args):
        result = original(*args)
        events.append('guard-blocked' if result['violations'] else 'guard-passed')
        return result

    monkeypatch.setattr(record_guard, 'check_registered_fields', observe_guard)
    models = ScriptedModels()
    generate = models.generate

    async def observe_judge(prompt, system_prompt=None):
        events.append('judge')
        return await generate(prompt, system_prompt)

    monkeypatch.setattr(models, 'generate', observe_judge)
    safe = runtime.redact(evidence())
    # 60 seconds exists in another candidate: a union-of-numbers check is insufficient.
    with pytest.raises(GroundingError):
        await runtime.validate(explanation(safe['catalog'][1]['message']), safe, TrackedLLM(models, 'Explanation'))
    assert events == ['guard-blocked'] and not models.calls
    await runtime.validate(explanation(), safe, TrackedLLM(models, 'Explanation'))
    assert events == ['guard-blocked', 'guard-passed', 'judge', 'judge']
    assert {call['stage'] for call in models.calls} == {'faithfulness', 'grounding'}


@pytest.mark.asyncio
@pytest.mark.parametrize('generation_provider', ['apple', 'commandcode'])
async def test_apple_stages_keep_legacy_wire_shapes(runtime, monkeypatch, generation_provider):
    monkeypatch.setattr('code_agent.provider.selected_provider', lambda: generation_provider)
    monkeypatch.setattr('code_agent.provider.judge_provider', lambda: 'apple')
    raw = evidence()
    safe = runtime.redact(raw)
    models = ScriptedModels()
    await gateway(runtime, models).json(Explanation, instructions('search_explanation'), raw)
    generated = next(call for call in models.calls if call['stage'] == 'generation')
    if generation_provider == 'apple':
        assert generated['prompt'] == json.dumps(safe, ensure_ascii=False)
    else:
        assert decode_evidence(generated['prompt']) == safe
    assert generated['schema'] == Explanation.model_json_schema()
    expected = json.dumps({'catalog': safe['catalog'], 'rule_comparison': []}, ensure_ascii=False)
    judges = [call for call in models.calls if call['stage'] != 'generation']
    assert len(judges) == 2
    assert all(document_text(call) == expected for call in judges)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['format', 'registered_value'])
async def test_repair_reuses_identical_encoded_evidence_and_preserves_skill_identity(runtime, caplog, failure):
    first = '{"text":' if failure == 'format' else explanation('인증을 60초 이후에 완료해주세요.').model_dump_json()
    models = ScriptedModels([first, explanation().model_dump_json()])
    raw = evidence()
    with caplog.at_level(logging.INFO), turn_trace(None, 1, 'repair-thread', 'repair-request'):
        result = await gateway(runtime, models).json(Explanation, instructions('search_explanation'), raw)
    assert result == explanation()
    generated = [call for call in models.calls if call['stage'] == 'generation']
    assert len(generated) == 2 and generated[0]['prompt'] == generated[1]['prompt']
    assert decode_evidence(generated[0]['prompt']) == runtime.redact(raw)
    assert generated[0]['system'] in generated[1]['system'] and '직전' in generated[1]['system']
    assert len([call for call in models.calls if call['stage'] != 'generation']) == 2
    calls = metrics(caplog)['calls']
    generated_metrics = [call for call in calls if call['skill'] == 'search_explanation@1.0.1']
    assert len(generated_metrics) == 2
    assert generated_metrics[1]['stage'].endswith('/format-repair' if failure == 'format' else '/grounding-repair')
    assert len([call for call in calls if call['skill'] == 'verification@1.0.0']) == 2
