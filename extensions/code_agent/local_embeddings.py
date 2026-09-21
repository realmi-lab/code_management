"""Private CPU model service, with pinned weights and no external inference calls."""
from contextlib import asynccontextmanager
import hmac
import os
from typing import Literal
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from .embeddings import MODEL, REVISION, IDENTITY

model=None


@asynccontextmanager
async def lifespan(app):
    global model
    if not os.getenv('LOCAL_EMBEDDING_TOKEN'):raise RuntimeError('Local embedding token required')
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(2)
    model=SentenceTransformer(MODEL,revision=REVISION,device='cpu',trust_remote_code=False)
    model.max_seq_length=512
    yield
    model=None


app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None)


class Batch(BaseModel):
    texts:list[str]=Field(min_length=1,max_length=32)
    kind:Literal['query','passage']


@app.get('/health')
def health():
    if model is None:raise HTTPException(503)
    return {'model':IDENTITY,'ready':True}


@app.post('/embed')
def embed(batch:Batch,authorization:str=Header('')):
    if not hmac.compare_digest(authorization,'Bearer '+os.environ['LOCAL_EMBEDDING_TOKEN']):raise HTTPException(401)
    if any(len(text)>16000 for text in batch.texts):raise HTTPException(413,'Text exceeds embedding limit')
    vectors=model.encode([batch.kind+': '+text for text in batch.texts],normalize_embeddings=True,batch_size=8).tolist()
    if any(len(vector)!=768 for vector in vectors):raise HTTPException(503,'Model dimension mismatch')
    # (x,0) dot (y,0) == x dot y; norms and cosine ranking are unchanged.
    return {'model':IDENTITY,'embeddings':[vector+[0.0]*768 for vector in vectors]}
