"""Explicit text-generation provider selection; embeddings stay independent."""
import os
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
    if provider not in ('openai','commandcode','anthropic','deepseek'):
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


def reasoning_options():
    if not commandcode_enabled():
        return {}
    effort = os.getenv('CODE_LLM_REASONING_EFFORT', 'high')
    if effort not in ('low', 'medium', 'high'):
        raise ValueError('Unsupported CODE_LLM_REASONING_EFFORT')
    return {'reasoning_effort': effort}


def client_options(api_key):
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
    if selected_provider() in ('commandcode','anthropic','deepseek') or ai_config.read()['version']:
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
            'model': model_name(None), **reasoning_options()}


def evaluation_llm():
    if anthropic_enabled():
        from .claude_judge import ClaudeJudge
        return ClaudeJudge()
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(**evaluation_options())
