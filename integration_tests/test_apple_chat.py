"""Local-only conversation selection, guided output, and no cloud fallback."""
import json
import httpx
import pytest
from openai import AsyncOpenAI
from code_agent import ai_config, apple, provider
from code_agent.routing import RoutingLLM
from code_agent.models import Plan
from code_agent.store import DomainError
from test_ai_settings import config_path, body


@pytest.fixture
def local_apple(config_path, monkeypatch):
    monkeypatch.setenv('CODE_APPLE_BRIDGE_TOKEN', 'synthetic-local-token')
    monkeypatch.setattr(ai_config, 'judge_apple_status', lambda: {'apple_judge_state': 'ready', 'apple_judge_available': True})
    monkeypatch.delenv('CODE_LLM_JUDGE_MODEL', raising=False)
    monkeypatch.delenv('CODE_LLM_JUDGE_PROVIDER', raising=False)
    return config_path


def test_apple_selection_preserves_cloud_keys_and_uses_local_judge(local_apple):
    ai_config.save(body('commandcode'), 1)
    result = ai_config.save(body('apple', version=1, key=''), 1)
    assert result['provider'] == 'apple' and result['model'] == 'apple/on-device'
    assert ai_config.key('COMMANDCODE_API_KEY') == 'synthetic-private-key'
    assert provider.public_settings()['judge_provider'] == 'apple'
    assert provider.client_options(None)['base_url'] == ai_config.APPLE_BRIDGE_URL
    assert provider.reasoning_options() == {}
    assert 'synthetic' not in json.dumps(result)


def test_apple_unavailable_and_custom_model_do_not_save(local_apple, monkeypatch):
    with pytest.raises(DomainError) as error:
        ai_config.save(body('apple', key='') | {'model': 'cloud/model'}, 1)
    assert error.value.status == 422
    monkeypatch.setattr(ai_config, 'judge_apple_status', lambda: {'apple_judge_available': False})
    with pytest.raises(DomainError) as error:
        ai_config.save(body('apple', key=''), 1)
    assert error.value.status == 503 and not local_apple.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected', [(200, None), (502, 502), (503, 502), (0, 503)])
async def test_apple_chat_transport_never_calls_cloud(local_apple, monkeypatch, status, expected):
    ai_config.save(body('apple', key=''), 1)
    seen=[]
    def respond(request):
        seen.append(request)
        if status == 0: raise httpx.ConnectError('bridge unavailable', request=request)
        if status != 200: return httpx.Response(status, json={'error': {'message': 'synthetic'}})
        return httpx.Response(200, json={'id':'test','object':'chat.completion','created':0,'model':'apple/on-device',
            'choices':[{'index':0,'message':{'role':'assistant','content':'{"action":"search","query":"인증"}'},'finish_reason':'stop'}]})
    monkeypatch.setattr(apple, 'AsyncOpenAI', lambda **kw: AsyncOpenAI(**kw, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))))
    with apple.structured_response(Plan.model_json_schema()):
        if expected:
            with pytest.raises(DomainError) as error: await RoutingLLM().generate('합성 입력')
            assert error.value.status == expected
        else:
            assert json.loads(await RoutingLLM().generate('합성 입력'))['query']=='인증'
    assert len(seen)==1 and str(seen[0].url)=='http://host.docker.internal:8787/v1/chat/completions'
    sent=json.loads(seen[0].content)
    assert sent['messages']==[{'role':'user','content':'합성 입력'}]
    assert sent['model']=='apple/on-device' and sent['response_format']['json_schema']['name']=='Plan'
    assert sent['temperature']==0
    assert 'reasoning_effort' not in sent
    assert apple._response_schema.get() is None


def test_apple_adapter_preserves_all_candidates_and_repairs_without_duplicate_schema():
    from code_agent.models import Explanation
    schema=Explanation.model_json_schema()
    payload={'question':'30초 인증','catalog':[
        {'code':f'EX-{n:04d}','message':'30초 이내에 인증해주세요.','title':'30초 이내에 인증해주세요.',
         'id':f'private-row-{n}','notes':'첫 줄\n둘째 줄','contents_en':'Within 30 seconds.'} for n in range(8)],
        'rule_comparison':[], 'extra':{'null':None,'flag':False,'count':0}}
    before=json.dumps(payload,ensure_ascii=False)
    system='등록 원문을 보존하세요.\n출력은 아래 JSON Schema를 따르는 JSON 객체 하나만 반환하세요.\n'+json.dumps(schema,ensure_ascii=False)+'\n직전 오류를 수정하세요.'
    prompt,instructions,shape=apple.prepare_request(before,system,schema)
    assert instructions.endswith('직전 오류를 수정하세요.') and '출력은 아래 JSON Schema' not in instructions
    assert shape['propertyOrder']==['text','references']
    assert shape['properties']['references']['items']['enum']==[r['code'] for r in payload['catalog']]
    for row in payload['catalog']:
        for key,value in row.items():
            if key=='id':assert value not in prompt
            else:assert json.dumps(value,ensure_ascii=False) in prompt
    assert '문구, 제목:' in prompt and 'null: null' in prompt and 'flag: false' in prompt and 'count: 0' in prompt
    assert json.dumps(payload,ensure_ascii=False)==before
    assert 'enum' not in schema['properties']['references']['items']


def test_apple_planner_input_and_optional_fields_are_unchanged():
    schema=Plan.model_json_schema()
    prompt='{"user":"원래 질문","history":[],"candidates":[]}'
    adapted,system,shape=apple.prepare_request(prompt,'기존 분류 지시',schema)
    assert (adapted,system,shape)==(prompt,'기존 분류 지시',schema)


@pytest.mark.parametrize('reason',['exceededContextWindowSize','decodingFailure','unsupportedLanguageOrLocale','guardrailViolation','rateLimited','unknown'])
def test_apple_error_reason_is_safe_and_distinct(reason,caplog):
    from openai import APIStatusError
    body={'error':{'message':reason+'(private document text and secret-token)'}}
    response=httpx.Response(502,request=httpx.Request('POST','http://bridge/v1/chat/completions'),json=body)
    error=apple.model_error(APIStatusError('private',response=response,body=body))
    assert error.status==502
    assert 'private' not in error.message+caplog.text and 'secret-token' not in error.message+caplog.text
    assert 'reason='+reason in caplog.text
