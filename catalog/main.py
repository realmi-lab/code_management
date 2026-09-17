from __future__ import annotations
import csv
import hashlib
import io
import json
import os
import secrets
import sqlite3
import time
from collections import defaultdict,deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from datetime import datetime,timezone
from fastapi import FastAPI,HTTPException,UploadFile,File,Form,Request,Query
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool
from .config import Settings,ROOT
from .db import DB,uid,now,dumps,decode_draft
from .models import DraftUpdate,ExternalLink,SearchRequest,CompareRequest,DraftRequest,ApprovalRequest,StatusRequest,ReviewRequest,ImportCommit,Namespace,canonical_code
from .importer import parse_upload,annotate_preview,ImportError,safe_filename
from .search import Search
from .ai import AI,AIError
from .demo import seed_demo
from .workflow import Workflow
from .admin_ai import load_runtime_config,public_state,apply_config


class AdminAuthRequest(BaseModel):
    password: str = Field(min_length=1,max_length=128)

class AdminAIConfigRequest(AdminAuthRequest):
    enabled: bool = True
    provider: Literal['openai-compatible','command-code','claude-code'] = 'claude-code'
    model: str = Field(default='',max_length=160)
    api_key: str | None = Field(default=None,max_length=1024)
    base_url: str = Field(default='',max_length=500)
    reasoning_effort: Literal['low','high','max'] = 'low'


def _require_admin(settings,password:str):
    expected=settings.admin_password
    if not expected or not secrets.compare_digest(password.encode('utf-8'),expected.encode('utf-8')):
        raise HTTPException(403,'관리자 비밀번호를 확인해주세요.')


def csv_text(headers,rows):
    def safe(v):
        t='' if v is None else str(v)
        # CSV is explicitly a safe review/export format, not a byte-exact round trip for formula-like text.
        if t.lstrip().startswith(('=','+','-','@')) or t.startswith(('\t','\r')): t="'"+t
        return t
    out=io.StringIO(newline=''); writer=csv.writer(out,lineterminator='\r\n')
    writer.writerow(headers)
    writer.writerows([[safe(v) for v in row] for row in rows])
    return '\ufeff'+out.getvalue()


def create_app(settings=None):
    settings=settings or Settings(); load_runtime_config(settings); db=DB(settings.data_dir/'catalog.sqlite3')
    seed_demo(db); ai=AI(settings); search=Search(db,ai); workflow=Workflow(db,settings)
    app=FastAPI(title='Code Library · 기획자용 알림 코드 관리',version='0.1.0',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.settings=settings; app.state.db=db; app.state.search=search; app.state.ai=ai; app.state.workflow=workflow
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=settings.allowed_hosts)
    buckets=defaultdict(deque)

    @app.middleware('http')
    async def guard(request,call_next):
        path=request.url.path
        # Protect every data endpoint; only liveness and static shell are public.
        if path.startswith('/api/') and path!='/api/health':
            token=request.headers.get('authorization','').removeprefix('Bearer ')
            if settings.access_token and not secrets.compare_digest(token.encode('utf-8'),settings.access_token.encode('utf-8')):
                return JSONResponse({'detail':'접속 키가 필요합니다.'},status_code=401)
            if request.method not in ('GET','HEAD','OPTIONS'):
                origin=request.headers.get('origin')
                if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
                    return JSONResponse({'detail':'다른 사이트에서 보낸 변경 요청을 차단했습니다.'},status_code=403)
                if request.headers.get('sec-fetch-site')=='cross-site':
                    return JSONResponse({'detail':'교차 사이트 요청을 차단했습니다.'},status_code=403)
                length=request.headers.get('content-length','0')
                if not length.isdigit() or int(length)>settings.max_upload+1024*1024:
                    return JSONResponse({'detail':'요청 크기 제한을 초과했습니다.'},status_code=413)
            if request.method not in ('GET','HEAD','OPTIONS'):
                bounded=bytearray()
                async for chunk in request.stream():
                    bounded.extend(chunk)
                    if len(bounded)>settings.max_upload+1024*1024:
                        return JSONResponse({'detail':'요청 크기 제한을 초과했습니다.'},status_code=413)
                request._body=bytes(bounded)  # Starlette's cached request passes these same bytes downstream.
            key=request.client.host if request.client else 'local'
            bucket=buckets[key]; cutoff=time.monotonic()-60
            while bucket and bucket[0]<cutoff: bucket.popleft()
            if len(bucket)>=180: return JSONResponse({'detail':'요청이 많습니다. 잠시 후 다시 시도해주세요.'},status_code=429,headers={'Retry-After':'60'})
            bucket.append(time.monotonic())
        response=await call_next(request)
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY',
            'Referrer-Policy':'no-referrer','Cache-Control':'no-store',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
        return response

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity(request,exc):
        return JSONResponse({'detail':'중복 번호 또는 데이터 제약으로 저장하지 못했습니다. 최신 목록을 확인해주세요.'},status_code=409)

    @app.exception_handler(AIError)
    async def ai_error(request,exc): return JSONResponse({'detail':str(exc)},status_code=503)

    @app.get('/api/health')
    def health(): return {'ok':True,'service':'code_management'}

    @app.post('/api/admin/ai/state')
    def admin_ai_state(req:AdminAuthRequest):
        _require_admin(settings,req.password)
        return public_state(settings)

    @app.post('/api/admin/ai/config')
    def admin_ai_config(req:AdminAIConfigRequest):
        _require_admin(settings,req.password)
        try:
            state=apply_config(settings,req.model_dump(),persist=True,preserve_key=True)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        ai.last_call=None;ai._query_cache.clear()
        return state

    @app.get('/api/meta')
    def meta(namespace:Namespace='live'):
        with db.connect() as con:
            con.execute('BEGIN')
            counts=db.catalog_stats(namespace,con)
            version=db.version(namespace,con)
            indexed=con.execute('SELECT COUNT(*) FROM embeddings e JOIN codes c ON c.id=e.code_id WHERE c.namespace=? AND e.model=?',(namespace,ai.embedding_identity)).fetchone()[0] if ai.embedding_enabled else 0
        return {'namespace':namespace,'counts':counts,
          'catalog_label':settings.catalog_label if namespace=='live' else '',
          'catalog_notice':settings.catalog_notice if namespace=='live' else '',
          'version':version,'authority':'system' if namespace=='demo' else settings.authority,
          'code_rules':{'EX':{'start':1000,'width':4}} if namespace=='demo' else settings.code_rules,
          'ai':{'enabled':settings.ai_enabled,'chat_enabled':ai.chat_enabled,'embedding_enabled':ai.embedding_enabled,'indexed':indexed,'external_allowed':settings.ai_allow_external,
                'provider':settings.ai_provider,'chat_model':settings.ai_chat_model,
                'reasoning_effort':settings.ai_reasoning_effort if settings.ai_provider in ('command-code','claude-code') else None,
                'last_call':ai.last_call},
          'authenticated':bool(settings.access_token),'upstream':{'repository':'urstory/urstory-rag','commit':'75661c676aec650e52f75dd068b687a4cb6a63b7','reused':'RRFCombiner'},
          'limits':{'max_upload_mb':8,'max_import_rows':settings.max_rows},
          'scope_notice':'데모는 합성 예시입니다. 실제 목록과 분리됩니다.' if namespace=='demo' else '엑셀에 없는 메뉴·노출 조건·사용처는 추측하지 않습니다.'}

    @app.post('/api/search')
    @app.post('/api/assistant')
    async def find(req:SearchRequest):
        return await search.find(req.query,req.namespace,req.limit,req.include_retired,req.menu,req.trigger,use_ai=req.use_ai)

    @app.post('/api/compare')
    async def compare(req:CompareRequest):
        # Search by actual candidate wording, not an unrelated query field.
        return await search.find(req.message,req.namespace,req.limit,req.include_retired,req.menu,req.trigger,req.message)

    @app.get('/api/codes')
    def listing(namespace:Namespace='live',q:str=Query(default='',max_length=300),status:Literal['all','active','retired']='all',offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=500)):
        return db.page_codes(namespace,q,status,offset,limit)

    @app.get('/api/codes/{code}')
    def get_code(code:str,namespace:Namespace='live'):
        try: code=canonical_code(code)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        row=db.get_code(namespace,code)
        if not row: raise HTTPException(404,'등록된 코드가 없습니다.')
        return row

    @app.get('/api/codes/{code}/copy')
    def copy_code(code:str,namespace:Namespace='live'):
        row=get_code(code,namespace)
        if row['status']=='retired': raise HTTPException(409,'폐기 코드는 기획서 재사용에서 제외됩니다.')
        lines=[f"알림 코드: {row['code']}"]
        for key,label in (('business','업무구분'),('message_type','타입'),('purpose','용도'),('title','타이틀')):
            if row.get(key): lines.append(label+': '+row[key])
        lines.append('표시 문구: '+row['message'])
        for key,label in (('title_en','영문타이틀'),('message_en','영문컨텐츠')):
            if row.get(key): lines.append(label+': '+row[key])
        lines.extend(['등록 메뉴: '+(row['menu'] or '미확인'),'등록 노출 조건: '+(row['trigger'] or '미확인'),
                      '이번 기획 노출 조건: [기획자가 작성]','처리 구분: 기존 코드 재사용 후보'])
        if row['source'].get('review_required'): lines.append('확인 필요: '+' / '.join(row['source'].get('review_notes') or ['사진 인식 자료이므로 원본 확인이 필요합니다.']))
        if namespace=='demo': lines.append('주의: 실제 회사 코드가 아닌 데모입니다.')
        return {'text':'\n'.join(lines)}

    @app.patch('/api/codes/{code}/status')
    def change_status(code:str,req:StatusRequest):
        if req.namespace=='live' and settings.authority!='system': raise HTTPException(409,'공식 엑셀에서 상태를 변경해야 합니다. 이 앱은 엑셀 항목을 자동 덮어쓰지 않습니다.')
        with db.connect(write=True) as con:
            row=db.get_code(req.namespace,code.upper(),con)
            if not row: raise HTTPException(404,'코드를 찾을 수 없습니다.')
            if row['revision']!=req.expected_revision: raise HTTPException(409,'항목이 변경되었습니다. 새로고침해주세요.')
            if not req.reason.strip(): raise HTTPException(422,'변경 이유를 입력해주세요.')
            con.execute('UPDATE codes SET status=?,revision=revision+1,updated_at=? WHERE id=?',(req.status,now(),row['id']))
            after=db.get_code(req.namespace,row['code'],con); db.bump(con,req.namespace)
            db.audit(con,req.namespace,'code.status',row['code'],row,after,req.reason)
            return after

    @app.post('/api/imports/preview')
    async def preview(file:UploadFile=File(...),namespace:Namespace=Form('live'),mapping:str=Form('{}')):
        blob=await file.read(settings.max_upload+1)
        await file.close()
        if len(blob)>settings.max_upload: raise HTTPException(413,'파일은 8MB 이하로 나눠주세요.')
        return await run_in_threadpool(prepare_import,blob,file.filename or 'upload.xlsx',namespace,mapping)

    def prepare_import(blob,filename,namespace,mapping):
        # Parse XLSX and write its immutable source off the async request loop.
        try:
            custom=json.loads(mapping)
            if not isinstance(custom,dict): raise ImportError('열 연결은 JSON 객체여야 합니다.')
            parsed=parse_upload(blob,filename,custom)
        except (ValueError,ImportError,KeyError,TypeError,csv.Error) as exc:
            raise HTTPException(422,str(exc)[:400]) from exc
        except Exception as exc:
            raise HTTPException(422,'엑셀 파일을 안전하게 해석하지 못했습니다. 일반 .xlsx 표로 다시 저장해주세요.') from exc
        parsed=annotate_preview(parsed,db,namespace); ident=uid()
        parsed['import_id']=ident; parsed['namespace']=namespace
        if len(parsed['records'])>settings.max_rows: raise HTTPException(413,'가져오기 항목 수가 너무 많습니다.')
        uploads=settings.data_dir/'uploads'
        path=uploads/(ident+Path(parsed['filename']).suffix.lower())
        created=False
        try:
            uploads.mkdir(exist_ok=True,mode=0o700)
            descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            created=True
            with os.fdopen(descriptor,'wb') as source:
                source.write(blob);source.flush();os.fsync(source.fileno())
            # A preview cannot be committed unless its original file is durable.
            with db.connect(write=True) as con:
                con.execute('INSERT INTO imports(id,namespace,filename,checksum,payload,catalog_version,created_at) VALUES(?,?,?,?,?,?,?)',
                  (ident,namespace,safe_filename(filename),hashlib.sha256(blob).hexdigest(),dumps(parsed),parsed['catalog_version'],now()))
        except (OSError,sqlite3.Error) as exc:
            if created:
                try: path.unlink(missing_ok=True)
                except OSError: pass
            raise HTTPException(503,'원본 파일과 미리보기를 저장하지 못했습니다. 저장 공간을 확인한 뒤 다시 시도해주세요.') from exc
        return parsed

    @app.post('/api/imports/{ident}/commit')
    def commit_import(ident:str,req:ImportCommit):
        with db.connect(write=True) as con:
            record=con.execute('SELECT * FROM imports WHERE id=?',(ident,)).fetchone()
            if not record: raise HTTPException(404,'미리보기를 찾을 수 없습니다.')
            if record['consumed']: raise HTTPException(409,'이미 처리된 가져오기입니다.')
            if (datetime.now(timezone.utc)-datetime.fromisoformat(record['created_at'])).total_seconds()>86400:
                raise HTTPException(409,'미리보기가 만료되었습니다. 파일을 다시 확인해주세요.')
            ns=record['namespace']; data=json.loads(record['payload'])
            if req.expected_catalog_version!=record['catalog_version'] or db.version(ns,con)!=record['catalog_version']:
                raise HTTPException(409,'미리보기 이후 목록이 변경되었습니다. 다시 미리보기를 실행해주세요.')
            if data['errors']: raise HTTPException(422,'파일 오류를 수정한 뒤 다시 가져와주세요.')
            approved=set(req.approved_updates)
            conflicts={r['code'] for r in data['records'] if r['action']=='conflict'}
            if not approved.issubset(conflicts):
                raise HTTPException(422,'원문 갱신을 승인한 번호가 미리보기의 충돌 항목과 다릅니다.')
            if approved and not req.update_reason.strip():
                raise HTTPException(422,'선택한 원문 갱신의 확인 이유를 입력해주세요.')
            if conflicts-approved and not req.skip_conflicts:
                raise HTTPException(409,'같은 번호에 다른 내용이 있습니다. 반영할 항목을 선택하거나 충돌 항목 제외를 확인해주세요.')
            if db.count_codes(ns,True,con)+data['counts']['new']>settings.max_rows:
                raise HTTPException(413,'이 첫 버전은 목록당 최대 10,000개 코드를 지원합니다.')
            count=0;updated=0
            for row in data['records']:
                source={**row['source'],'import_id':ident,'imported_at':now()}
                if row['action']=='new':
                    db.insert_code(con,ns,row,source); count+=1
                elif row['action']=='conflict' and row['code'] in approved:
                    before=db.get_code(ns,row['code'],con)
                    con.execute('''UPDATE codes SET message=?,menu=?,trigger_text=?,notes=?,status=?,source_json=?,
                        revision=revision+1,updated_at=? WHERE id=?''',
                        (row['message'],row['menu'],row['trigger'],row['notes'],row['status'],dumps(source),now(),before['id']))
                    con.execute('DELETE FROM embeddings WHERE code_id=?',(before['id'],))
                    db.audit(con,ns,'code.source_updated',row['code'],before,row,req.update_reason)
                    updated+=1
            if count or updated: db.bump(con,ns)
            con.execute('UPDATE imports SET consumed=1 WHERE id=?',(ident,))
            linked=workflow.reconcile_import(con,ns,[r['code'] for r in data['records'] if r['action'] in ('new','unchanged') or r['code'] in approved])
            db.audit(con,ns,'import.committed',ident,None,{'added':count,'updated':updated,'skipped_conflicts':len(conflicts-approved)},'명시적으로 선택한 갱신과 새 항목만 반영. 삭제 없음')
            return {'added':count,'updated':updated,'unchanged':data['counts']['unchanged'],'skipped_conflicts':len(conflicts-approved),'catalog_version':db.version(ns,con),'linked_drafts':linked}

    @app.post('/api/drafts')
    async def create_draft(req:DraftRequest):
        candidates=await search.find(req.message,req.namespace,8,True,req.menu,req.trigger,req.message)
        message=req.message; notice='AI 미사용: 입력 문구 그대로 초안을 저장합니다.'
        if req.use_ai:
            try: message,notice=await ai.draft(req.message,req.menu,req.trigger,candidates['results'])
            except AIError as exc: notice=str(exc)+' 입력 원문으로 초안을 저장했습니다.'
            if message!=req.message: candidates=await search.find(message,req.namespace,8,True,req.menu,req.trigger,message)
        draft=workflow.create_draft(req,message)
        return {'draft':draft,'candidates':candidates,'notice':notice,'registration_status':'아직 정식 코드가 발급되지 않았습니다.'}

    @app.get('/api/drafts')
    def drafts(namespace:Namespace='live'):
        with db.connect() as con:
            return {'items':[decode_draft(r) for r in con.execute('SELECT * FROM drafts WHERE namespace=? ORDER BY created_at DESC',(namespace,))]}

    @app.patch('/api/drafts/{ident}')
    def edit_draft(ident:str,req:DraftUpdate): return workflow.update_draft(ident,req)

    @app.get('/api/drafts/{ident}/external-matches')
    def external_matches(ident:str,namespace:Namespace='live'):
        return workflow.external_matches(namespace,ident)

    @app.post('/api/drafts/{ident}/link-external')
    def external_link(ident:str,req:ExternalLink): return workflow.link_external(ident,req)

    @app.get('/api/drafts/{ident}/review')
    async def draft_review(ident:str,namespace:Namespace='live'):
        draft=workflow.get_draft(namespace,ident)
        return {'draft':draft,'comparison':await search.find(draft['message'],namespace,12,True,draft['menu'],draft['trigger'],draft['message'])}

    @app.post('/api/drafts/{ident}/handoff')
    def handoff(ident:str,namespace:Namespace='live',expected_revision:int=Query(ge=1)):
        return workflow.handoff(namespace,ident,expected_revision)

    @app.post('/api/drafts/{ident}/approve')
    def approve(ident:str,req:ApprovalRequest): return workflow.approve(ident,req)

    @app.post('/api/review')
    async def review(req:ReviewRequest):
        lines=[line.strip() for line in req.text.splitlines() if line.strip()]
        if len(lines)>30: raise HTTPException(422,'기획서 검토는 한 번에 30개 문구까지 나눠주세요.')
        if not lines: raise HTTPException(422,'한 줄에 하나씩 문구를 입력해주세요.')
        items=[]
        # Sequential to bound requests to an optional inference server.
        for i,line in enumerate(lines,1):
            result=await search.find(line,req.namespace,3,req.include_retired,comparison_text=line)
            items.append({'line':i,'input':line,**result})
        return {'items':items,'notice':'줄별 문구 후보 검토입니다. 자유형 기획서 전체의 정책을 자동 해석하거나 재사용을 확정하지 않습니다.'}

    @app.post('/api/ai/reindex')
    async def reindex(namespace:Namespace='live'): return await search.reindex(namespace)

    @app.get('/api/audit')
    def audit(namespace:Namespace='live',limit:int=Query(60,ge=1,le=200)):
        with db.connect() as con:
            return {'items':[dict(r) for r in con.execute('SELECT * FROM audit WHERE namespace=? ORDER BY id DESC LIMIT ?',(namespace,limit))]}

    @app.get('/api/export/codes.csv')
    def export_codes(namespace:Namespace='live'):
        rows=db.all_codes(namespace)
        data=csv_text(['코드번호','등록문구','사용메뉴','노출조건','비고','상태','업무구분','타입','용도','타이틀','영문타이틀','영문컨텐츠'],
          [[r['code'],r['message'],r['menu'],r['trigger'],r['notes'],'사용 중' if r['status']=='active' else '폐기',
            *[r.get(key,'') for key in ('business','message_type','purpose','title','title_en','message_en')]] for r in rows])
        return Response(data,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="codes_'+namespace+'.csv"'})

    @app.get('/api/export/drafts.csv')
    def export_drafts(namespace:Namespace='live'):
        items=drafts(namespace)['items']
        data=csv_text(['초안ID','상태','종류','대상코드','제안문구','메뉴','노출조건','비고','등록코드','등록연결표시'],
           [[r['id'],r['state'],r['kind'],r['target_code'],r['message'],r['menu'],r['trigger'],r['notes'],r['registered_code'],'[draft:'+r['id']+']'] for r in items])
        return Response(data,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="drafts_'+namespace+'.csv"'})

    @app.get('/api/template.xlsx')
    def template():
        path=ROOT/'examples'/'code_catalog_template.xlsx'
        if not path.exists(): raise HTTPException(404,'템플릿 파일이 없습니다.')
        return FileResponse(path,filename='code_catalog_template.xlsx',media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
    @app.get('/')
    def index(): return FileResponse(ROOT/'static'/'index.html')
    return app

app=create_app()
