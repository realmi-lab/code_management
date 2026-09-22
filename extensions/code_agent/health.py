"""Connectivity checks for the selected providers; not inference-quality claims."""
import os
import httpx
from .provider import commandcode_enabled, client_options, anthropic_enabled, anthropic_options
from .embeddings import local_enabled, keyword_only, IDENTITY
from . import ai_config


async def llm_connected():
    try:
        from app.config import get_settings
        if anthropic_enabled():
            async with httpx.AsyncClient(timeout=8) as client:
                response=await client.get('https://api.anthropic.com/v1/models',headers={
                    'x-api-key':anthropic_options()['api_key'],'anthropic-version':'2023-06-01'})
            return response.status_code==200
        options=client_options(get_settings().openai_api_key)
        if not options.get('api_key'):return False
        url=options.get('base_url','https://api.openai.com/v1')+'/models'
        async with httpx.AsyncClient(timeout=8) as client:
            response=await client.get(url,headers={'Authorization':'Bearer '+options['api_key']})
        return response.status_code==200
    except Exception:return False


async def embedding_connected():
    if keyword_only():return False
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            if local_enabled():
                response=await client.get(os.getenv('LOCAL_EMBEDDING_URL','http://local-embeddings:8080')+'/health')
                return response.status_code==200 and response.json().get('model')==IDENTITY and response.json().get('ready') is True
            from app.config import get_settings
            key=ai_config.key('OPENAI_API_KEY')
            if not key:return False
            response=await client.get('https://api.openai.com/v1/models',headers={'Authorization':'Bearer '+key})
            return response.status_code==200
    except Exception:return False


def descriptions():
    return ('Apple 온디바이스' if ai_config.read()['provider']=='apple' else 'Anthropic / Claude' if anthropic_enabled() else 'Command Code / DeepSeek' if commandcode_enabled() else 'OpenAI LLM',
            '사용 안 함 · 키워드 검색' if keyword_only() else '로컬 multilingual-e5-base (CPU)' if local_enabled() else 'OpenAI 임베딩')
