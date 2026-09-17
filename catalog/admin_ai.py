"""Runtime AI configuration persisted outside Git-tracked files."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse


PROVIDERS = {'openai-compatible', 'command-code', 'claude-code'}
EFFORTS = {'low', 'high', 'max'}


def config_path(settings) -> Path:
    return Path(settings.data_dir) / '.ai-runtime.json'


def public_state(settings) -> dict:
    return {
        'enabled': bool(settings.ai_enabled),
        'provider': settings.ai_provider,
        'model': settings.ai_chat_model,
        'base_url': settings.ai_base_url if settings.ai_provider == 'openai-compatible' else '',
        'reasoning_effort': settings.ai_reasoning_effort,
        'key_configured': bool(settings.ai_key),
        'claude_code_available': bool(shutil.which(settings.claude_code_bin)),
        'claude_code_bin': settings.claude_code_bin,
    }


def _validated(data: dict, settings, *, preserve_key: bool) -> dict:
    provider = str(data.get('provider') or settings.ai_provider).strip()
    if provider not in PROVIDERS:
        raise ValueError('지원하지 않는 AI provider입니다.')
    model = str(data.get('model') or settings.ai_chat_model).strip()
    if len(model) > 160:
        raise ValueError('모델 이름이 너무 깁니다.')
    enabled = bool(data.get('enabled', True))
    effort = str(data.get('reasoning_effort') or settings.ai_reasoning_effort or 'low').strip()
    if effort not in EFFORTS:
        raise ValueError('추론 강도는 low, high, max 중 하나여야 합니다.')

    incoming_key = data.get('api_key', None)
    if incoming_key is None and preserve_key:
        api_key = settings.ai_key
    else:
        api_key = str(incoming_key or '').strip()
    if len(api_key) > 1024:
        raise ValueError('API key가 너무 깁니다.')

    base_url = str(data.get('base_url') or settings.ai_base_url or '').strip()
    if len(base_url) > 500:
        raise ValueError('API URL이 너무 깁니다.')

    if enabled and not model:
        raise ValueError('사용할 모델을 입력해주세요.')
    if provider == 'claude-code':
        if enabled and not api_key:
            raise ValueError('Claude API key를 입력해주세요.')
        base_url = settings.ai_base_url
    elif provider == 'openai-compatible':
        u = urlparse(base_url)
        if enabled and (u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment):
            raise ValueError('OpenAI-compatible API URL을 확인해주세요.')
        local = u.hostname in ('localhost', '127.0.0.1', '::1', 'host.docker.internal')
        if enabled and not local and u.scheme != 'https':
            raise ValueError('외부 AI API는 HTTPS만 허용합니다.')

    return {
        'enabled': enabled,
        'provider': provider,
        'model': model,
        'api_key': api_key,
        'base_url': base_url,
        'reasoning_effort': effort,
    }


def apply_config(settings, data: dict, *, persist: bool = True, preserve_key: bool = True) -> dict:
    config = _validated(data, settings, preserve_key=preserve_key)
    settings.ai_enabled = config['enabled']
    settings.ai_provider = config['provider']
    settings.ai_chat_model = config['model']
    settings.ai_key = config['api_key']
    settings.ai_reasoning_effort = config['reasoning_effort']
    settings.ai_embedding_model = ''
    settings.ai_allow_external = config['provider'] in ('command-code', 'claude-code')
    if config['provider'] == 'openai-compatible':
        settings.ai_base_url = config['base_url']
        host = urlparse(settings.ai_base_url).hostname
        settings.ai_allow_external = host not in ('localhost', '127.0.0.1', '::1', 'host.docker.internal')

    if persist:
        path = config_path(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    return public_state(settings)


def load_runtime_config(settings) -> bool:
    path = config_path(settings)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return False
        apply_config(settings, data, persist=False, preserve_key=False)
        return True
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
