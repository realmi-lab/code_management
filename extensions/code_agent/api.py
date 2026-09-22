from __future__ import annotations
from .catalog_schema import FIELDS, business_values, export_record
import asyncio,csv,io,json,logging,os,zipfile
from xml.etree.ElementTree import ParseError
from defusedxml.common import DefusedXmlException
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,Depends,File,Form,UploadFile,HTTPException,Request
from fastapi.responses import Response
from .models import Actor,Turn,ImportCommit,Approval,Revision,CatalogComparison,DocumentReview,CatalogSearchTest
from .store import DomainError,admin,SampleStore
from .agent import Agent
from .importer import parse_upload,ImportError
from .provider import public_settings
from .operations import RedisQuota, turn_trace
from . import ai_config
from .inspection import inspect_message

log=logging.getLogger(__name__)
MAX_UPLOAD=8*1024*1024

def create_router(store,gateway,identity,enqueue=lambda:None,quota=None,sample_gateway=None,enqueue_sample=None):
    quota=quota or RedisQuota()
    router=APIRouter(prefix='/api/code-catalog',tags=['code-catalog'])
    agent=Agent(store,gateway)
    sample_store=SampleStore(store)
    if sample_gateway is None:
        from .gateway import UrstoryGateway
        sample_gateway=UrstoryGateway(sample_store,getattr(gateway,'monitor',None))
    sample_agent=Agent(sample_store,sample_gateway)
    def scope(namespace):return sample_store if namespace=='demo' else store
    def searcher(namespace):return sample_gateway if namespace=='demo' else gateway
    pending=set()
    capacity=asyncio.Semaphore(4)
    async def actor(user=Depends(identity)):
        return Actor(id=user.id,role=user.role,name=getattr(user,'name',''))
    def queue():
        try: enqueue()
        except Exception: log.warning('Catalog indexing enqueue failed; periodic reconciler will retry.')
    @router.post('/search-test')
    async def search_test(body:CatalogSearchTest,a=Depends(actor)):
        await quota.check(a.id,'review')
        async with capacity:
            records,trace=await searcher(body.namespace).search(body.query)
        return {'namespace':body.namespace,'storage':'postgresql','items':records,'trace':trace,'total':len(records)}
    @router.get('/status')
    def status(namespace:Literal['production','demo']='production',a=Depends(actor)):
        from .embeddings import storage_identity
        from .gateway import index_identity
        s=scope(namespace).status()
        ready=s['version']==s['indexed_version'] and (s['version']==0 or s.get('indexed_model')==index_identity(storage_identity()))
        return dict(s,storage='postgresql',namespace=namespace,index_ready=ready,user=a.model_dump(),llm=public_settings(),embedding=ai_config.read()['embedding'],authority=os.getenv('CODE_CATALOG_AUTHORITY','system'),notice='정식 번호는 관리자가 승인한 값을 직접 입력합니다. AI는 번호를 발급하지 않습니다.')
    @router.get('/ai-settings')
    def ai_settings(a=Depends(actor)):
        admin(a);return ai_config.public()
    @router.put('/ai-settings')
    async def update_ai_settings(request:Request,a=Depends(actor)):
        admin(a)
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>12000:raise DomainError('설정 요청이 너무 큽니다.',413)
        try:body=json.loads(data)
        except ValueError:raise DomainError('설정 형식을 확인해주세요.',422)
        result=await asyncio.to_thread(ai_config.save,body,a.id)
        queue()
        return dict(result,notice='다음 요청부터 적용됩니다. 검색 방식을 바꾸면 검색 준비를 다시 실행해주세요.')
    @router.get('/codes')
    def list_codes(include_retired:bool=False,offset:int=0,limit:int=100,q:str='',status:Literal['all','active','retired']|None=None,namespace:Literal['production','demo']='production',a=Depends(actor)):
        if not 0<=offset or not 1<=limit<=200: raise DomainError('목록 범위가 올바르지 않습니다.',422)
        if len(q)>4000: raise DomainError('검색어는 4,000자 이하로 입력해주세요.',422)
        from sqlalchemy.exc import SQLAlchemyError
        try:
            s,rows=scope(namespace).snapshot(include_retired if status is None else status!='active')
        except SQLAlchemyError as exc:
            raise DomainError('DB 목록을 조회하지 못했습니다. DB 연결 상태를 확인한 뒤 다시 시도해주세요.',503) from exc
        if status in ('active','retired'): rows=[r for r in rows if r['status']==status]
        terms=q.casefold().split()
        if terms:
            def matches(r):
                fields=r.get('source',{}).get('catalog_fields',{})
                text=' '.join(str(r.get(k,'')) for k in ('code','message','menu','trigger','notes'))+' '+' '.join(str(v) for v in business_values(r).values())+' '+' '.join(str(v) for v in fields.values())
                text=text.casefold()
                return all(term in text for term in terms)
            rows=[r for r in rows if matches(r)]
        return {'items':rows[offset:offset+limit],'total':len(rows),'catalog_version':s['version']}
    @router.post('/compare')
    async def compare_catalog(body:CatalogComparison,a=Depends(actor)):
        await quota.check(a.id,'review')
        async with capacity:
            return await inspect_message(store,searcher(body.namespace),body)
    @router.post('/review')
    async def review_document(body:DocumentReview,a=Depends(actor)):
        await quota.check(a.id,'review')
        # One snapshot for the whole document instead of one per line.
        catalog=scope(body.namespace).snapshot(True)
        version=catalog[0]['version']
        items=[]
        async with capacity:
            for number,line in enumerate(body.text.splitlines(),1):
                if not line.strip():continue
                result=await inspect_message(store,searcher(body.namespace),CatalogComparison(message=line,namespace=body.namespace,mode=body.mode),catalog)
                items.append(dict(result,line=number,input=line))
        if body.namespace=='production' and store.status()['version']!=version:
            raise DomainError('검토 중 목록이 변경되었습니다. 다시 검토해주세요.')
        return {'items':items,'catalog_version':version,'namespace':body.namespace}
    @router.get('/codes/{code}')
    def get_code(code:str,namespace:Literal['production','demo']='production',a=Depends(actor)):
        # Single-row lookup in both scopes; the sample scope used to load all rows.
        rec=scope(namespace).get_code(code)
        if not rec: raise DomainError('등록된 코드번호가 없습니다.',404)
        return rec
    @router.patch('/codes/{code}')
    def revise(code:str,body:Revision,a=Depends(actor)):
        result=store.revise_code(a,code,body); queue(); return result
    @router.post('/imports/preview')
    async def preview(file:UploadFile=File(...),mapping:str=Form('{}'),a=Depends(actor)):
        admin(a)
        await quota.check(a.id,'import')
        data=await file.read(MAX_UPLOAD+1)
        if len(data)>MAX_UPLOAD: raise DomainError('파일은 8MB 이하여야 합니다.',413)
        try:
            mapped=json.loads(mapping)
            if not isinstance(mapped,dict) or any(not isinstance(spec,dict) for spec in mapped.values()): raise ValueError()
            parsed=await asyncio.to_thread(parse_upload,data,file.filename or 'upload.xlsx',mapped)
        except (ValueError,KeyError,TypeError,AttributeError,ParseError,DefusedXmlException,csv.Error,zipfile.BadZipFile) as exc: raise DomainError('파일 형식 또는 열 연결을 확인해주세요. '+(str(exc) if isinstance(exc,ImportError) else ''),422) from exc
        return await asyncio.to_thread(store.save_preview,a,parsed)
    @router.post('/imports/{ident}/commit')
    def commit(ident:str,body:ImportCommit,a=Depends(actor)):
        result=store.apply_preview(a,ident,body);queue();return result
    @router.post('/threads')
    def thread(namespace:Literal['production','demo']='production',a=Depends(actor)): return scope(namespace).create_thread(a)
    @router.get('/threads')
    def threads(namespace:Literal['production','demo']='production',a=Depends(actor)): return scope(namespace).list_threads(a)
    @router.get('/threads/{ident}')
    def get_thread(ident:str,namespace:Literal['production','demo']='production',a=Depends(actor)): return scope(namespace).get_thread(a,ident)
    @router.post('/threads/{ident}/turn')
    async def turn(ident:str,body:Turn,namespace:Literal['production','demo']='production',a=Depends(actor)):
        await quota.check(a.id,'turn')
        key=(a.id,ident)
        if key in pending: raise DomainError('이 대화의 이전 요청이 처리 중입니다.',409)
        pending.add(key)
        acquired=False
        try:
            await asyncio.wait_for(capacity.acquire(),timeout=2); acquired=True
            with turn_trace(getattr(gateway,'monitor',None),a.id,ident,body.request_id):
                return await asyncio.wait_for((sample_agent if namespace=='demo' else agent).turn(a,ident,body),timeout=240)
        except TimeoutError as exc: raise DomainError('처리 시간이 초과되었습니다. 대화 상태를 확인한 뒤 다시 시도해주세요.',504) from exc
        finally:
            pending.discard(key)
            if acquired: capacity.release()
    @router.get('/drafts')
    def get_drafts(a=Depends(actor)): return store.list_drafts(a)
    @router.post('/drafts/{ident}/review')
    async def review(ident:str,a=Depends(actor)):
        await quota.check(a.id,'review')
        draft=next((v for v in store.list_drafts(a) if v['id']==ident),None)
        if not draft: raise DomainError('초안을 찾을 수 없습니다.',404)
        version=store.status()['version']; candidates,trace=await gateway.search(draft['payload']['message'])
        return {'draft':store.review_draft(a,ident,candidates,version),'candidates':candidates,'trace':trace}
    @router.post('/drafts/{ident}/approve')
    def approve(ident:str,body:Approval,a=Depends(actor)):
        result=store.approve(a,ident,body);queue();return result
    @router.post('/index')
    async def index(namespace:Literal['production','demo']='production',a=Depends(actor)):
        admin(a)
        await quota.check(a.id,'index')
        try:
            if namespace=='demo':
                if enqueue_sample is None:raise RuntimeError('Sample worker not configured')
                enqueue_sample()
            else:enqueue()
        except Exception as exc: raise DomainError('인덱싱 작업을 등록하지 못했습니다. 워커 연결을 확인해주세요.',503) from exc
        return {'status':'queued','namespace':namespace,'catalog_version':scope(namespace).status()['version']}
    @router.get('/audit')
    def audit(a=Depends(actor)): return store.audit_log(a)
    @router.get('/export.json')
    def export_json(namespace:Literal['production','demo']='production',a=Depends(actor)):
        state,items=scope(namespace).snapshot(True)
        body={'schema_version':2,'namespace':namespace,'synthetic':namespace=='demo',
              'catalog_version':state['version'],'total':len(items),'items':[export_record(r) for r in items]}
        filename='sample_catalog_300.json' if namespace=='demo' else 'code-catalog.json'
        return Response(json.dumps(body,ensure_ascii=False,indent=2),media_type='application/json',
                        headers={'Content-Disposition':f'attachment; filename="{filename}"'})
    @router.get('/export')
    def export(namespace:Literal['production','demo']='production',a=Depends(actor)):
        _,items=scope(namespace).snapshot(True); out=io.StringIO(); writer=csv.writer(out);writer.writerow(['코드번호','등록문구','메뉴','노출조건','비고','상태','업무구분','타입','용도','타이틀','영문타이틀','영문컨텐츠'])
        for rec in items:
            vals=[str(rec[k]) for k in ('code','message','menu','trigger','notes','status')]
            fields=rec.get('source',{}).get('catalog_fields',{})
            vals.extend(str(fields.get(k,'')) for k in ('business','message_type','purpose','title','title_en','message_en'))
            writer.writerow(["'"+x if x.lstrip().startswith(('=','+','-','@')) else x for x in vals])
        return Response('\ufeff'+out.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="code-catalog.csv"'})
    return router
