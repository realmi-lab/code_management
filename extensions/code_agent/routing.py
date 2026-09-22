"""Per-call clients let all upstream paths honor administrator selection immediately."""
from . import ai_config

class Closing:
    async def close(self):pass

class RoutingLLM:
    def __init__(self,api_key=None,model=None,temperature=0.3):
        self.client=Closing();self.temperature=temperature;self.fallback=model;self.last_usage=None
    @property
    def model(self):
        from .provider import model_name
        return model_name(self.fallback)
    async def generate(self,prompt,system_prompt=None):
        from .provider import anthropic_enabled
        self.last_usage=None
        if anthropic_enabled():
            from .claude import make_llm
            llm=make_llm(self.model)
        else:
            from app.services.generation.openai import OpenAILLM
            class Native(OpenAILLM):pass
            llm=Native(api_key=ai_config.key('OPENAI_API_KEY'),model=self.model,temperature=self.temperature)
            # The patched constructor re-resolves the administrator model; keep a pinned judge model.
            llm.model=self.model
        try:
            result=await llm.generate(prompt,system_prompt=system_prompt)
            self.last_usage=getattr(llm,'last_usage',None)
            return result
        finally:await llm.client.close()

class JudgeLLM(RoutingLLM):
    """Faithfulness/grounding judge: same provider and key; CODE_LLM_JUDGE_* may pin its model/effort."""
    def __init__(self,temperature=0):super().__init__(temperature=temperature)
    @property
    def model(self):
        from .provider import judge_model_name
        return judge_model_name() or super().model
    async def generate(self,prompt,system_prompt=None):
        from .provider import judge_stage
        with judge_stage():
            return await super().generate(prompt,system_prompt=system_prompt)

class RoutingEmbedding:
    def __init__(self,api_key=None,model=None,dimensions=None):
        self.client=Closing();self.dimensions=dimensions;self.fallback=model
    @property
    def model(self):
        from .embeddings import local_enabled,keyword_only,IDENTITY
        return IDENTITY if local_enabled() else 'none:keyword-v1' if keyword_only() else 'text-embedding-3-small'
    async def _call(self,method,value):
        from .embeddings import local_enabled,keyword_only,LocalEmbedding,IDENTITY
        if keyword_only():raise ValueError('Embeddings are disabled in keyword search mode')
        if local_enabled():embedder=LocalEmbedding(model=IDENTITY,dimensions=self.dimensions)
        else:
            from app.services.embedding.openai import OpenAIEmbedding
            class Native(OpenAIEmbedding):pass
            embedder=Native(api_key=ai_config.key('OPENAI_API_KEY'),model=self.model,dimensions=self.dimensions or 1536)
        try:return await getattr(embedder,method)(value)
        finally:await embedder.client.close()
    async def embed_documents(self,texts):return await self._call('embed_documents',texts)
    async def embed_query(self,text):return await self._call('embed_query',text)
