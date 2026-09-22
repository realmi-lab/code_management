"""Explicit text-generation provider selection; embeddings stay independent."""
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from . import ai_config

COMMANDCODE_URL = 'https://api.commandcode.ai/provider/v1'
COMMANDCODE_MODEL = 'deepseek/deepseek-v4.1-flash'
ANTHROPIC_MODEL = 'claude-sonnet-5'
_raw_model_settings = ContextVar('code_agent_raw_model_settings', default=False)


@contextmanager
def raw_model_settings():
    """Construct stored preferences without deployment-only effective overrides."""
    token = _raw_model_settings.set(True)
    try:
        yield
    finally:
        _raw_model_settings.reset(token)


def selected_provider():
    provider=ai_config.read()['provider']
    if provider not in ('openai','commandcode','anthropic','deepseek','apple'):
        raise ValueError('Unsupported CODE_LLM_PROVIDER')
    return provider


def anthropic_enabled():return selected_provider()=='anthropic'


def anthropic_options():
    key=ai_config.key('ANTHROPIC_API_KEY').strip()
    if not key:raise ValueError('ANTHROPIC_API_KEY is required for Claude')
    return {'api_key':key,'base_url':'https://api.anthropic.com','max_retries':2,'timeout':70}


def commandcode_enabled():
    return selected_provider() == 'commandcode'


def model_name(fallback):
    c=ai_config.read()
    if c['version'] or selected_provider()!='openai':return c['model']
    return fallback if fallback is not None else c['model']


_judge_stage = ContextVar('code_agent_judge_stage', default=False)
JUDGE_MODEL_PATTERN = r'[A-Za-z0-9_./:-]{1,160}'
JUDGE_PROVIDERS = ('apple',)
APPLE_JUDGE_MODEL = 'apple/on-device'
APPLE_BRIDGE_URL = ai_config.APPLE_BRIDGE_URL
JUDGE_URL_PATTERN = r'https?://[A-Za-z0-9_.-]+(?::\d{1,5})?(?:/[A-Za-z0-9_./-]*)?'


@contextmanager
def judge_stage():
    """Mark faithfulness/grounding judge calls so CODE_LLM_JUDGE_* applies to them only."""
    token = _judge_stage.set(True)
    try:
        yield
    finally:
        _judge_stage.reset(token)


def judge_options():
    """Env-only judge overrides; empty means the judge shares the generation model and effort.

    CODE_LLM_JUDGE_PROVIDER=apple routes only the two judge stages to the Mac-side Apple on-device
    bridge (see extensions/apple_bridge). Generation, HyDE, rewrites and RAGAS never change.
    """
    options = {}
    provider = os.getenv('CODE_LLM_JUDGE_PROVIDER', '').strip()
    model = os.getenv('CODE_LLM_JUDGE_MODEL', '').strip()
    if selected_provider()=='apple':
        if model and model!=APPLE_JUDGE_MODEL:raise ValueError('Apple only supports apple/on-device')
        provider='apple'
    if provider:
        if provider not in JUDGE_PROVIDERS:
            raise ValueError('Unsupported CODE_LLM_JUDGE_PROVIDER')
        options['provider'] = provider
    if model:
        if not re.fullmatch(JUDGE_MODEL_PATTERN, model):
            raise ValueError('Unsupported CODE_LLM_JUDGE_MODEL')
        options['model'] = model
    elif provider == 'apple':
        options['model'] = APPLE_JUDGE_MODEL
    effort = os.getenv('CODE_LLM_JUDGE_REASONING_EFFORT', '').strip()
    if effort:
        if effort not in ('low', 'medium', 'high', 'none'):
            raise ValueError('Unsupported CODE_LLM_JUDGE_REASONING_EFFORT')
        options['reasoning_effort'] = effort
    if provider == 'apple':
        base_url = os.getenv('CODE_LLM_JUDGE_BASE_URL', '').strip() or APPLE_BRIDGE_URL
        if not re.fullmatch(JUDGE_URL_PATTERN, base_url):
            raise ValueError('Unsupported CODE_LLM_JUDGE_BASE_URL')
        options['base_url'] = base_url
    return options


def judge_provider():
    return judge_options().get('provider')


def judge_model_name():
    return judge_options().get('model')


def judge_configured():
    return bool(judge_options())


def reasoning_options():
    if not commandcode_enabled():
        return {}
    effort = os.getenv('CODE_LLM_REASONING_EFFORT', 'high')
    if effort not in ('low', 'medium', 'high'):
        raise ValueError('Unsupported CODE_LLM_REASONING_EFFORT')
    if _judge_stage.get():
        judge = judge_options().get('reasoning_effort')
        if judge == 'none':
            return {}
        effort = judge or effort
    return {'reasoning_effort': effort}


def client_options(api_key):
    if selected_provider()=='apple':
        token=os.getenv('CODE_APPLE_BRIDGE_TOKEN','').strip()
        if not token:raise ValueError('CODE_APPLE_BRIDGE_TOKEN is required')
        return {'api_key':token,'base_url':os.getenv('CODE_APPLE_BRIDGE_URL','').strip() or APPLE_BRIDGE_URL,'timeout':70,'max_retries':0}
    if anthropic_enabled():raise ValueError('Claude must use the native Anthropic Messages API')
    if selected_provider()=='deepseek':
        key=ai_config.key('DEEPSEEK_API_KEY').strip()
        if not key:raise ValueError('DEEPSEEK_API_KEY is required')
        return {'api_key':key,'base_url':'https://api.deepseek.com'}
    if not commandcode_enabled():
        return {'api_key':ai_config.key('OPENAI_API_KEY') or api_key}
    key = ai_config.key('COMMANDCODE_API_KEY').strip()
    if not key:
        raise ValueError('COMMANDCODE_API_KEY is required for Command Code')
    return {'api_key': key, 'base_url': COMMANDCODE_URL}


def evaluation_options():
    if anthropic_enabled():return {'model':model_name(None)}
    if selected_provider()=='openai' and not ai_config.read()['version']:
        return {'model': 'gpt-4o', 'temperature': 0}
    return {**client_options(None), 'model': model_name(None), **reasoning_options()}


def apply_model_settings(settings):
    """Apply runtime selection to a fresh settings copy, never stored preferences."""
    if _raw_model_settings.get():
        return
    if selected_provider() in ('commandcode','anthropic','deepseek','apple') or ai_config.read()['version']:
        settings.llm_provider = selected_provider()
        for field in ('llm_model', 'hyde_model', 'multi_query_model', 'contextual_chunking_model'):
            setattr(settings, field, model_name(None))
        settings.guardrails.hallucination_detection.judge_model = model_name(None)
    from .embeddings import local_enabled, keyword_only, IDENTITY
    if local_enabled():
        settings.embedding_provider='local'
        settings.embedding_model=IDENTITY
    elif keyword_only():
        settings.embedding_provider='none';settings.embedding_model='none:keyword-v1'
        settings.search_mode='keyword';settings.hyde_enabled=False;settings.multi_query_enabled=False
        if settings.chunking_strategy=='semantic':settings.chunking_strategy='auto'
    elif ai_config.read()['version']:
        settings.embedding_provider='openai';settings.embedding_model='text-embedding-3-small'


def public_settings():
    return {'provider': selected_provider(),
            'model': model_name(None), **reasoning_options(),
            'judge_model': judge_model_name() or model_name(None),
            'judge_provider': judge_provider() or selected_provider()}


def evaluation_llm():
    if anthropic_enabled():
        from .claude_judge import ClaudeJudge
        return ClaudeJudge()
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(**evaluation_options())
