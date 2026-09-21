#!/usr/bin/env python3
"""Use the local Command Code API key without printing or passing it in argv."""
import json
from pathlib import Path
from manage import ROOT, SetupError, configure, encode_env, private_write


def main():
    auth = Path.home() / '.commandcode/auth.json'
    if not auth.is_file():
        raise SetupError('commandcode login으로 먼저 로그인하세요.')
    key = json.loads(auth.read_text()).get('apiKey', '').strip()
    if not key:
        raise SetupError('Command Code API 키가 없습니다.')
    values = configure(ROOT, interactive=False)
    values.update(CODE_LLM_PROVIDER='commandcode', COMMANDCODE_API_KEY=key,
                  CODE_LLM_MODEL='deepseek/deepseek-v4.1-flash', CODE_LLM_REASONING_EFFORT='high')
    private_write(ROOT / '.env', encode_env(values))
    print('Command Code / deepseek/deepseek-v4.1-flash / high 설정 완료 (.env 권한 0600)')
    if not values.get('OPENAI_API_KEY'):
        print('임베딩용 OPENAI_API_KEY는 미설정입니다. 전체 RAG 기동에는 별도 설정이 필요합니다.')


if __name__ == '__main__':
    try:
        main()
    except (SetupError, OSError, ValueError) as exc:
        print('Command Code 설정 실패:', type(exc).__name__)
        raise SystemExit(1)
