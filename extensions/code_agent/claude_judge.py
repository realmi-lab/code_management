from .claude import request_options, response_text
from .provider import anthropic_options, model_name
# RAGAS uses the existing LangChain dependency; no OpenAI judge is constructed.
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ClaudeJudge(BaseChatModel):
    @property
    def _llm_type(self):return 'catalog-anthropic'

    @property
    def _identifying_params(self):return {'model':model_name(None)}

    def _options(self,messages,stop=None):
        system=[];turns=[]
        for message in messages:
            content=message.content
            if isinstance(content,list):
                if any(not isinstance(block,dict) or block.get('type')!='text' for block in content):
                    raise ValueError('Claude evaluation accepts text messages only')
                content='\n'.join(block['text'] for block in content)
            if not isinstance(content,str):raise ValueError('Claude evaluation requires text content')
            if message.type=='system':system.append(content)
            elif message.type in ('human','ai'):
                turns.append({'role':'user' if message.type=='human' else 'assistant','content':content})
            else:raise ValueError('Claude evaluation received an unsupported message role')
        if not turns:raise ValueError('Claude evaluation requires a conversation message')
        options=request_options('', '\n'.join(system))
        options['messages']=turns
        if stop:options['stop_sequences']=stop
        return options

    def _result(self,response):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=response_text(response)))],
                          llm_output={'model':model_name(None),'token_usage':response.usage.model_dump()})

    def _generate(self,messages,stop=None,run_manager=None,**kwargs):
        from anthropic import Anthropic
        with Anthropic(**anthropic_options()) as client:
            return self._result(client.messages.create(**self._options(messages,stop)))

    async def _agenerate(self,messages,stop=None,run_manager=None,**kwargs):
        from anthropic import AsyncAnthropic
        async with AsyncAnthropic(**anthropic_options()) as client:
            return self._result(await client.messages.create(**self._options(messages,stop)))
