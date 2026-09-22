"""Native Anthropic transport and a LangChain adapter for the original RAGAS."""
from .provider import anthropic_options, model_name


def request_options(prompt,system_prompt=None):
    options={'model':model_name(None),'max_tokens':16384,
             'messages':[{'role':'user','content':prompt}]}
    if system_prompt:options['system']=system_prompt
    # Preserve the SDK's native thinking blocks; return only final text to the app.
    return options


def response_text(response):
    if response.stop_reason=='max_tokens':raise ValueError('Claude output was truncated')
    if response.stop_reason not in ('end_turn','stop_sequence'):
        raise ValueError('Claude did not complete a final text response')
    text=''.join(block.text for block in response.content if block.type=='text')
    if not text.strip():raise ValueError('Claude returned no final text')
    return text


def make_llm(model=None):
    from app.services.generation.claude import ClaudeLLM
    return ClaudeLLM(api_key=anthropic_options()['api_key'],model=model or model_name(None),max_tokens=16384)
