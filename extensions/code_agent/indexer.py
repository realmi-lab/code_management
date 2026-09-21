"""Versioned publication to real PGVector + Nori, with one UUID per hit in BOTH stores."""
from __future__ import annotations
import asyncio,json,logging,math,uuid
import httpx
from sqlalchemy import text,select,update,delete
from .store import Store,SampleStore,state,chunks
from .gateway import INDEX, index_identity, catalog_index
from .safety import CatalogSafety
from .embeddings import keyword_only
from .config_scope import pinned_configuration, assert_current
log=logging.getLogger(__name__)

MAPPING={
 'settings':{'analysis':{'analyzer':{'ko_catalog':{'type':'custom','tokenizer':'nori_tokenizer','filter':['lowercase']}}}},
 'mappings':{'properties':{'chunk_id':{'type':'keyword'},'document_id':{'type':'keyword'},'content':{'type':'text','analyzer':'ko_catalog'},
                         'metadata':{'type':'object','enabled':False}}}
}

def text_for(rec):
    from .catalog_schema import FIELDS,business_values
    values=business_values(rec)
    return '\n'.join([label+': '+str(values[key]) for key,label in FIELDS]+['메뉴: '+rec['menu'],'노출 조건: '+rec['trigger']])

def validate_vectors(vectors,count):
    if len(vectors)!=count or any(len(v)!=1536 or not all(isinstance(x,(float,int)) and math.isfinite(x) for x in v) for v in vectors):
        raise ValueError('Embedding batch shape mismatch; index was not published.')

@pinned_configuration
async def rebuild(namespace="production"):
    if namespace not in ("production","demo"):raise ValueError("Invalid catalogue scope")
    from app.config import get_settings
    from app.services.embedding.openai import OpenAIEmbedding
    from app.services.settings import SettingsService
    from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
    env=get_settings(); store=Store(env.database_url)
    if namespace=="demo":store=SampleStore(store)
    state_table=store.state_table
    index_name=catalog_index(namespace)
    lock_id=715194234 if namespace=="demo" else 715194233
    engine=create_async_engine(env.database_url)
    async with async_sessionmaker(engine,expire_on_commit=False)() as session:
        settings=await SettingsService(db=session).get_settings()
    await engine.dispose()
    embedder=OpenAIEmbedding(api_key=env.openai_api_key,model=settings.embedding_model,dimensions=1536)
    snapshot=str(uuid.uuid4());published=False
    try:
        with store.engine.connect() as lock:
            locked=lock.execute(text('SELECT pg_try_advisory_lock(:lock_id)'),{'lock_id':lock_id}).scalar();lock.commit()
            if not locked: return {'status':'already_running'}
            try:
                s,rows=store.snapshot()
                if s['indexed_version']==s['version'] and s.get('indexed_model')==index_identity(settings.embedding_model): return {'status':'up_to_date'}
                async with httpx.AsyncClient(base_url=env.elasticsearch_url,timeout=60) as es:
                    exists=await es.head('/'+index_name)
                    if exists.status_code==404:
                        created=await es.put('/'+index_name,json=MAPPING);created.raise_for_status()
                    else: exists.raise_for_status()
                    for start in range(0,len(rows),32):
                        group=rows[start:start+32]; safety=CatalogSafety(); contents=[safety.redact(text_for(v)) for v in group]
                        if keyword_only():vectors=[None]*len(group)
                        else:
                            vectors=await embedder.embed_documents(contents);validate_vectors(vectors,len(group))
                        bulk=[]
                        with store.engine.begin() as c:
                            for offset,(rec,content,vector) in enumerate(zip(group,contents,vectors)):
                                ident=str(uuid.uuid4()); meta={'code':rec['code'],'revision':rec['revision'],'catalog_version':s['version']}
                                c.execute(text('INSERT INTO cm_search_chunks (id,document_id,content,chunk_index,metadata,embedding) VALUES (:id,:snapshot,:content,:idx,CAST(:meta AS json),CAST(:embedding AS vector))'),
                                    {'id':ident,'snapshot':snapshot,'content':content,'idx':start+offset,'meta':json.dumps(meta,ensure_ascii=False),'embedding':str(vector) if vector is not None else None})
                                bulk.extend([json.dumps({'index':{'_index':index_name,'_id':ident}}),json.dumps({'chunk_id':ident,'document_id':snapshot,'content':content,'metadata':meta},ensure_ascii=False)])
                        response=await es.post('/_bulk',content='\n'.join(bulk)+'\n',headers={'Content-Type':'application/x-ndjson'})
                        response.raise_for_status()
                        if response.json().get('errors'): raise RuntimeError('Elasticsearch rejected a batch; active index unchanged.')
                    refreshed=await es.post('/'+index_name+'/_refresh');refreshed.raise_for_status()
                    assert_current()
                    with store.engine.begin() as c:
                        changed=c.execute(update(state_table).where(state_table.c.id==1,state_table.c.version==s['version']).values(
                            indexed_version=s['version'],snapshot=snapshot,index_error='',indexed_model=index_identity(settings.embedding_model)))
                        published=changed.rowcount==1
                    if not published: return {'status':'superseded'}
                    # Only approved current snapshot is searched. Old snapshot removal is best effort.
                    if s['snapshot']:
                        try:
                            removed=await es.post('/'+index_name+'/_delete_by_query',json={'query':{'term':{'document_id':s['snapshot']}}});removed.raise_for_status()
                            with store.engine.begin() as c: c.execute(delete(chunks).where(chunks.c.document_id==s['snapshot']))
                        except Exception: log.warning('Old catalog index cleanup will require retry.')
                return {'status':'indexed','count':len(rows),'version':s['version']}
            finally:
                lock.execute(text('SELECT pg_advisory_unlock(:lock_id)'),{'lock_id':lock_id});lock.commit()
    except Exception as exc:
        # Do not persist model response, URLs with credentials, or document text.
        with store.engine.begin() as c: c.execute(update(state_table).where(state_table.c.id==1).values(index_error=type(exc).__name__))
        raise RuntimeError('Catalogue indexing failed: '+type(exc).__name__) from None
    finally:
        if not published:
            with store.engine.begin() as c: c.execute(delete(chunks).where(chunks.c.document_id==snapshot))
            # Orphan ES snapshot has no pointer and cannot be queried by the catalogue.
        await embedder.client.close();store.engine.dispose()
