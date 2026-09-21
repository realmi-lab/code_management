"""Opt-in local E5 embeddings. Zero padding preserves cosine distance exactly."""
import os
import httpx
from . import ai_config

MODEL='intfloat/multilingual-e5-base'
REVISION='d128750597153bb5987e10b1c3493a34e5a4502a'
IDENTITY=f'local:{MODEL}@{REVISION}:pad1536:v1'


def local_enabled():return ai_config.read()['embedding']=='local'
def keyword_only():return ai_config.read()['embedding']=='none'
def storage_identity():return IDENTITY if local_enabled() else 'none:keyword-v1' if keyword_only() else 'text-embedding-3-small'


class Client(httpx.AsyncClient):
    async def close(self):await self.aclose()


class DisabledEmbedding:
    """No client or credentials are constructed when semantic search is disabled."""
    model='none:keyword-v1'
    @property
    def client(self):return self
    async def close(self):pass
    async def embed_documents(self,texts):
        raise ValueError('Embeddings are disabled in keyword search mode')
    async def embed_query(self,text):
        raise ValueError('Embeddings are disabled in keyword search mode')


class LocalEmbedding:
    def __init__(self,api_key=None,model=None,dimensions=1536):
        if dimensions not in (None,1536):raise ValueError('Local adapter requires 1536 storage dimensions')
        if model not in (None,IDENTITY):raise ValueError('Local model identity mismatch; reindex required')
        self.model=IDENTITY
        self.client=Client(base_url=os.getenv('LOCAL_EMBEDDING_URL','http://local-embeddings:8080'),
                           headers={'Authorization':'Bearer '+os.environ['LOCAL_EMBEDDING_TOKEN']},timeout=180)
    async def _embed(self,texts,kind):
        results=[]
        for start in range(0,len(texts),32):
            response=await self.client.post('/embed',json={'texts':texts[start:start+32],'kind':kind})
            response.raise_for_status();data=response.json()
            if data.get('model')!=IDENTITY:raise ValueError('Embedding service identity mismatch')
            batch=data['embeddings']
            from .indexer import validate_vectors
            validate_vectors(batch,len(texts[start:start+32]));results.extend(batch)
        return results
    async def embed_documents(self,texts):return await self._embed(texts,'passage')
    async def embed_query(self,text):return (await self._embed([text],'query'))[0]


def evaluation_embeddings():
    if keyword_only():raise ValueError('Embedding-based RAGAS metrics are disabled in keyword-only mode')
    from langchain_core.embeddings import Embeddings
    from langchain_openai import OpenAIEmbeddings
    if not local_enabled():return OpenAIEmbeddings(model='text-embedding-3-small',api_key=ai_config.key('OPENAI_API_KEY'))
    class Local(Embeddings):
        def _run(self,texts,kind):
            with httpx.Client(base_url=os.getenv('LOCAL_EMBEDDING_URL','http://local-embeddings:8080'),
                              headers={'Authorization':'Bearer '+os.environ['LOCAL_EMBEDDING_TOKEN']},timeout=180) as client:
                result=[]
                for start in range(0,len(texts),32):
                    response=client.post('/embed',json={'texts':texts[start:start+32],'kind':kind});response.raise_for_status()
                    data=response.json()
                    if data['model']!=IDENTITY:raise ValueError('Embedding identity mismatch')
                    from .indexer import validate_vectors
                    validate_vectors(data['embeddings'],len(texts[start:start+32]))
                    result.extend(data['embeddings'])
                return result
        def embed_documents(self,texts):return self._run(texts,'passage')
        def embed_query(self,text):return self._run([text],'query')[0]
    return Local()
