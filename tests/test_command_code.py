import asyncio
import json
import sys
import time
import pytest
from catalog.ai import AI, AIError
from catalog.command_code import parse_output, CommandCodeError
from catalog.config import Settings

MODEL = 'deepseek/deepseek-v4.1-flash'

def settings(tmp_path, **kwargs):
    return Settings(data_dir=tmp_path/'data', ai_enabled=True,
                    ai_provider='command-code', ai_allow_external=True,
                    ai_chat_model=MODEL, **kwargs)

def cli(tmp_path, body):
    path=tmp_path/'fake-cli'
    path.write_text('#!'+sys.executable+'\n'+body)
    path.chmod(0o700)
    return str(path)

def frames(effort='low'):
    return '\n'.join(json.dumps(x) for x in [
        {'type':'event','event':{'type':'model_request_end','model':MODEL,'effort':effort}},
        {'type':'result','subtype':'success','finalText':json.dumps({'message':'30초 이후에 인증해 주세요.','rationale':'띄어쓰기 개선'})},
    ])

def test_real_subprocess_contract_and_draft_validation(tmp_path):
    body="""import sys, json
args=sys.argv[1:]
assert args[args.index('--model')+1]=='deepseek/deepseek-v4.1-flash'
assert args[args.index('--effort')+1]=='low'
assert args[args.index('--max-turns')+1]=='1'
assert '--no-session' in args and '--no-skills' in args and '--mod' in args
assert '30초' in sys.stdin.read()
"""
    binary=cli(tmp_path,body+'print('+repr(frames())+')\n')
    ai=AI(settings(tmp_path,command_code_bin=binary))
    message,_=asyncio.run(ai.draft('30초 이후에 인증해주세요.','','',[]))
    assert message=='30초 이후에 인증해 주세요.'
    assert ai.last_call['observed_effort']=='low'
    assert not ai.embedding_enabled

def test_wrong_effective_effort_rejected():
    with pytest.raises(CommandCodeError):
        parse_output(frames('high'),MODEL,'low')

def test_missing_profile_is_not_invented():
    result=json.loads(frames().splitlines()[-1])
    data=parse_output(json.dumps(result),MODEL,'low')
    assert data['command_code']['observed_effort'] is None

def test_cli_error_does_not_expose_output(tmp_path):
    binary=cli(tmp_path,"import sys\nprint('SENSITIVE_TOKEN_AND_DOCUMENT')\nsys.exit(3)\n")
    ai=AI(settings(tmp_path,command_code_bin=binary))
    with pytest.raises(AIError) as e:
        asyncio.run(ai.draft('안내','','',[]))
    assert '로그인' in str(e.value)
    assert 'SENSITIVE' not in str(e.value)

def test_timeout_terminates_process(tmp_path):
    binary=cli(tmp_path,"import time\ntime.sleep(20)\n")
    ai=AI(settings(tmp_path,command_code_bin=binary,ai_timeout=1))
    start=time.monotonic()
    with pytest.raises(AIError, match='대기 시간'):
        asyncio.run(ai.draft('안내','','',[]))
    assert time.monotonic()-start<5

def test_external_consent_and_embedding_contract(tmp_path):
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path,ai_enabled=True,ai_provider='command-code')
    with pytest.raises(ValueError):
        settings(tmp_path,ai_embedding_model='unsupported')
    with pytest.raises(ValueError):
        settings(tmp_path,ai_reasoning_effort='invalid')

def test_command_code_disabled_cannot_launch(tmp_path,monkeypatch):
    s=settings(tmp_path);s.ai_enabled=False
    async def reject(*a,**kw): raise AssertionError('Must not spawn')
    monkeypatch.setattr(asyncio,'create_subprocess_exec',reject)
    assert asyncio.run(AI(s).draft('원문','','',[]))[0]=='원문'

def test_truncated_exit_rejected_even_with_result(tmp_path):
    binary=cli(tmp_path,'import sys\nprint('+repr(frames())+')\nsys.exit(8)\n')
    with pytest.raises(AIError, match='완료되지'):
        asyncio.run(AI(settings(tmp_path,command_code_bin=binary)).draft('안내','','',[]))
