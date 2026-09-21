"""Transactional catalogue in the SAME PostgreSQL database as UrstoryRAG.

SQLite is used only by isolated tests. All writes are parameterized; catalog and
conversation versions are compare-and-swap guards against concurrent writes.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib, json, uuid, os
from sqlalchemy import (MetaData, Table, Column, String, Integer, Text, JSON, Boolean,
                        create_engine, select, update, insert, UniqueConstraint, text, inspect, Computed)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from .models import Actor, Approval, ImportCommit, canonical_code

from .catalog_schema import EXTRA_COLUMNS, business_values, normalized_record

metadata=MetaData()
state=Table('cm_state',metadata,Column('id',Integer,primary_key=True),Column('version',Integer,nullable=False),
    Column('indexed_version',Integer,nullable=False,default=-1),Column('snapshot',String(36)),Column('indexed_model',String(200),default=''),Column('index_error',Text,default=''))
codes=Table('cm_codes',metadata,Column('id',String(36),primary_key=True),Column('code',String(40),unique=True,nullable=False),
    Column('message',Text,nullable=False),Column('menu',Text,default=''),Column('trigger',Text,default=''),Column('notes',Text,default=''),
    Column('status',String(20),nullable=False),Column('revision',Integer,nullable=False),Column('source',JSON,nullable=False),Column('updated_at',String(40)))
for field in EXTRA_COLUMNS: codes.append_column(Column(field,Text,nullable=False,server_default=''))
codes.append_column(Column('message_code',String(40),Computed('code',persisted=True)))
imports=Table('cm_imports',metadata,Column('id',String(36),primary_key=True),Column('owner',Integer,nullable=False),
    Column('version',Integer,nullable=False),Column('payload',JSON,nullable=False),Column('applied',Boolean,default=False),Column('result',JSON),Column('created_at',String(40)))
threads=Table('cm_threads',metadata,Column('id',String(36),primary_key=True),Column('owner',Integer,nullable=False,index=True),
    Column('title',String(100)),Column('version',Integer,nullable=False),Column('history',JSON,nullable=False),
    Column('candidates',JSON,nullable=False),Column('draft',JSON),Column('updated_at',String(40)))
turns=Table('cm_turns',metadata,Column('id',String(36),primary_key=True),Column('thread_id',String(36),nullable=False),
    Column('request_id',String(36),nullable=False),Column('fingerprint',String(64),nullable=False),Column('result',JSON,nullable=False),
    UniqueConstraint('thread_id','request_id'))
drafts=Table('cm_drafts',metadata,Column('id',String(36),primary_key=True),Column('owner',Integer,nullable=False),
    Column('thread_id',String(36),nullable=False),Column('payload',JSON,nullable=False),Column('status',String(24),nullable=False),
    Column('revision',Integer,nullable=False),Column('catalog_version',Integer,nullable=False),Column('registered_code',String(40)),Column('created_at',String(40)))
audits=Table('cm_audit',metadata,Column('id',String(36),primary_key=True),Column('actor',Integer,nullable=False),Column('action',String(40)),
    Column('entity',String(100)),Column('before',JSON),Column('after',JSON),Column('reason',Text),Column('created_at',String(40)))
chunks=Table('cm_search_chunks',metadata,Column('id',String(36),primary_key=True),Column('document_id',String(36),index=True,nullable=False),
    Column('content',Text,nullable=False),Column('chunk_index',Integer),Column('metadata',JSON,nullable=False))

thread_scopes=Table('cm_thread_scopes',metadata,Column('thread_id',String(36),primary_key=True),Column('namespace',String(20),nullable=False))
sample_codes=codes.to_metadata(metadata,name='cm_sample_codes')
sample_bootstrap=Table('cm_sample_bootstrap',metadata,Column('id',Integer,primary_key=True),Column('source_hash',String(64),nullable=False),Column('count',Integer,nullable=False),Column('created_at',String(40),nullable=False))
sample_state=state.to_metadata(metadata,name='cm_sample_state')
sample_state.append_column(Column('source_hash',String(64)))

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return str(uuid.uuid4())
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def row(value): return dict(value) if value is not None else None

class DomainError(Exception):
    def __init__(self, message, status=409): self.message=message; self.status=status; super().__init__(message)

def admin(actor):
    if actor.role!='admin': raise DomainError('관리자 권한이 필요합니다.',403)

class Store:
    namespace="production"
    state_table=state
    def __init__(self,url):
        if url.startswith('postgresql+asyncpg:'): url=url.replace('postgresql+asyncpg:','postgresql+psycopg:',1)
        kw={'pool_pre_ping':True}
        if url.startswith('sqlite'):
            kw['connect_args']={'check_same_thread':False,'timeout':15}
            if ':memory:' in url: kw['poolclass']=StaticPool
        self.engine=create_engine(url,**kw)

    def initialize(self):
        metadata.create_all(self.engine)
        with self.engine.begin() as c:
            # ON CONFLICT works in supported PostgreSQL and SQLite versions.
            c.execute(text('INSERT INTO cm_state (id,version,indexed_version,index_error) VALUES (1,0,-1,\'\') ON CONFLICT (id) DO NOTHING'))
            if self.engine.dialect.name=='postgresql':
                c.execute(text('ALTER TABLE cm_search_chunks ADD COLUMN IF NOT EXISTS embedding vector(1536)'))
        # Additive, repeatable migration: old authoritative text and history remain intact.
        existing={col['name'] for col in inspect(self.engine).get_columns('cm_codes')}
        with self.engine.begin() as c:
            for field in EXTRA_COLUMNS:
                if field not in existing:c.execute(text(f"ALTER TABLE cm_codes ADD COLUMN {field} TEXT NOT NULL DEFAULT ''"))
            if 'message_code' not in existing:
                c.execute(text('ALTER TABLE cm_codes ADD COLUMN message_code VARCHAR(40) GENERATED ALWAYS AS (code) '+('STORED' if self.engine.dialect.name=='postgresql' else 'VIRTUAL')))
            migrated_rows=c.execute(select(codes)).mappings().all()
            for rec in migrated_rows:
                values=business_values(dict(rec))
                c.execute(update(codes).where(codes.c.id==rec['id']).values(**{k:values[k] for k in EXTRA_COLUMNS}))
            if migrated_rows and not set(EXTRA_COLUMNS)<=existing:
                c.execute(update(state).where(state.c.id==1).values(version=state.c.version+1,index_error=''))
        SampleStore(self).initialize_catalog()

    @contextmanager
    def transaction(self):
        with self.engine.begin() as c:
            try: yield c
            except IntegrityError as exc: raise DomainError('번호 또는 요청이 중복되었습니다. 최신 목록을 확인해주세요.') from exc

    def _audit(self,c,actor,action,entity,before,after,reason=''):
        c.execute(insert(audits).values(id=uid(),actor=actor.id,action=action,entity=entity,before=before,after=after,reason=reason,created_at=now()))

    def _state(self,c): return row(c.execute(select(state).where(state.c.id==1)).mappings().one())
    def status(self):
        with self.engine.connect() as c: return self._state(c)
    def _bump(self,c,expected):
        changed=c.execute(update(state).where(state.c.id==1,state.c.version==expected).values(version=expected+1,index_error=''))
        if changed.rowcount!=1: raise DomainError('목록이 변경되었습니다. 최신 후보를 검토하고 다시 실행해주세요.')
        return expected+1
    def snapshot(self,retired=False):
        # Lock the single catalog state row during this short snapshot; all writers use it.
        with self.engine.begin() as c:
            s=row(c.execute(select(state).where(state.c.id==1).with_for_update()).mappings().one())
            q=select(codes).order_by(codes.c.code)
            if not retired: q=q.where(codes.c.status=='active')
            return s, [normalized_record(dict(v)) for v in c.execute(q).mappings()]
    def get_code(self,code):
        try: code=canonical_code(code)
        except ValueError as exc: raise DomainError(str(exc),422) from exc
        with self.engine.connect() as c:
            value=row(c.execute(select(codes).where(codes.c.code==code)).mappings().first())
            return normalized_record(value) if value else None
    def save_preview(self,actor,parsed):
        admin(actor)
        s,existing=self.snapshot(True); by_code={v['code']:v for v in existing}
        counts={'new':0,'unchanged':0,'conflict':0}
        by_message={}
        for item in existing: by_message.setdefault(item['message'],[]).append(item['code'])
        for rec in parsed['records']:
            old=by_code.get(rec['code'])
            if old:
                # Preserve omitted optional columns; explicit empty cells still require approval.
                fields=dict(old.get('source',{}).get('catalog_fields',{}))
                fields.update(rec['source'].get('catalog_fields',{}))
                rec['source']['catalog_fields']=fields
            rec['action']='new' if not old else ('unchanged' if all(rec.get(k,'')==old.get(k,'') for k in ('message','menu','trigger','notes','status')) and rec['source'].get('catalog_fields',{})==old.get('source',{}).get('catalog_fields',{}) else 'conflict')
            if old: rec['existing']=old
            rec['same_message_codes']=[code for code in by_message.get(rec['message'],[]) if code!=rec['code']]
            counts[rec['action']]+=1
        parsed['counts']=counts
        with self.transaction() as c:
            ident=uid(); c.execute(insert(imports).values(id=ident,owner=actor.id,version=s['version'],payload=parsed,applied=False,created_at=now()))
        return dict(parsed,id=ident,catalog_version=s['version'])
    def apply_preview(self,actor,ident,body:ImportCommit):
        admin(actor)
        with self.transaction() as c:
            imp=row(c.execute(select(imports).where(imports.c.id==ident,imports.c.owner==actor.id).with_for_update()).mappings().first())
            if not imp: raise DomainError('가져오기 내역을 찾을 수 없습니다.',404)
            if imp['applied']: return imp['result']
            data=imp['payload']
            if data['errors']: raise DomainError('파일 오류를 수정한 뒤 다시 가져와주세요.',422)
            if body.expected_catalog_version!=imp['version']: raise DomainError('미리보기 버전이 다릅니다.')
            conflicts={v['code'] for v in data['records'] if v['action']=='conflict'}
            chosen=set(body.updates)
            if not chosen<=conflicts: raise DomainError('변경 대상으로 확인되지 않은 코드가 있습니다.',422)
            if chosen and not body.reason.strip(): raise DomainError('기존 문구 변경 사유가 필요합니다.',422)
            if conflicts-chosen and not body.skip_conflicts: raise DomainError('충돌 항목을 선택하거나 제외해 주세요.')
            changed_rows=[v for v in data['records'] if v['action']=='new' or (v['action']=='conflict' and v['code'] in chosen)]
            if changed_rows:
                next_v=self._bump(c,imp['version'])
            else:
                guard=c.execute(update(state).where(state.c.id==1,state.c.version==imp['version']).values(version=imp['version']))
                if guard.rowcount!=1: raise DomainError('목록이 변경되었습니다. 다시 확인해주세요.')
                next_v=imp['version']
            count=0
            for rec in data['records']:
                action=rec['action']
                if action=='unchanged' or (action=='conflict' and rec['code'] not in chosen): continue
                vals={k:rec[k] for k in ('code','message','menu','trigger','notes','status','source')}
                vals.update({k:v for k,v in business_values(rec).items() if k in EXTRA_COLUMNS})
                old=rec.get('existing'); vals['revision']=old['revision']+1 if old else 1; vals['updated_at']=now()
                if old: vals['added_date']=old.get('added_date','')
                else: vals['added_date']=now()[:10]
                if old: c.execute(update(codes).where(codes.c.id==old['id']).values(**vals)); entity=old['id']
                else: entity=uid(); c.execute(insert(codes).values(id=entity,**vals))
                self._audit(c,actor,'import_update' if old else 'import_create',rec['code'],old,vals,body.reason); count+=1
            result={'changed':count,'catalog_version':next_v,'index_status':'pending'}
            c.execute(update(imports).where(imports.c.id==ident).values(applied=True,result=result))
            return result
    def create_thread(self,actor,title='새 대화'):
        t={'id':uid(),'owner':actor.id,'title':title[:100],'version':0,'history':[],'candidates':[],'draft':None,'updated_at':now()}
        with self.transaction() as c:
            c.execute(insert(threads).values(**t))
            c.execute(insert(thread_scopes).values(thread_id=t['id'],namespace=self.namespace))
        t['namespace']=self.namespace
        return t
    def scope_condition(self):
        from sqlalchemy import func
        return func.coalesce(thread_scopes.c.namespace,'production')==self.namespace
    def list_threads(self,actor):
        with self.engine.connect() as c:
            return [dict(x,namespace=self.namespace) for x in c.execute(select(threads.c.id,threads.c.title,threads.c.version,threads.c.updated_at).select_from(threads.outerjoin(thread_scopes,threads.c.id==thread_scopes.c.thread_id)).where(threads.c.owner==actor.id,self.scope_condition()).order_by(threads.c.updated_at.desc()).limit(100)).mappings()]
    def get_thread(self,actor,ident):
        with self.engine.connect() as c:
            t=row(c.execute(select(threads).select_from(threads.outerjoin(thread_scopes,threads.c.id==thread_scopes.c.thread_id)).where(threads.c.id==ident,threads.c.owner==actor.id,self.scope_condition())).mappings().first())
            if not t: raise DomainError('대화를 찾을 수 없습니다.',404)
            t['namespace']=self.namespace
            if t.get('draft'):
                current_draft=row(c.execute(select(drafts).where(drafts.c.id==t['draft']['id'],drafts.c.owner==actor.id)).mappings().first())
                t['draft']=current_draft
            return t
    def replay(self,actor,thread_id,request_id,fingerprint):
        self.get_thread(actor,thread_id)
        with self.engine.connect() as c:
            t=row(c.execute(select(turns).where(turns.c.thread_id==thread_id,turns.c.request_id==request_id)).mappings().first())
            if not t: return None
            if t['fingerprint']!=fingerprint: raise DomainError('같은 요청 번호에 다른 내용이 들어왔습니다.')
            return t['result']
    def finish_turn(self,actor,t,request_id,fingerprint,user_text,result,draft=None):
        with self.transaction() as c:
            state_table=self.state_table
            current=row(c.execute(select(state_table).where(state_table.c.id==1).with_for_update()).mappings().one())
            if current['version']!=result['catalog_version']: raise DomainError('답변 도중 목록이 변경되었습니다. 다시 질문해주세요.')
            history=(t['history']+[{'role':'user','content':user_text},{'role':'assistant','content':result['answer'],'selected_code':result.get('selected_code'),'ai_used':result.get('ai_used',True)}])[-24:]
            created=None
            if draft:
                if self.namespace!='production':raise DomainError('샘플 대화에서는 정식 등록용 초안을 저장하지 않습니다.',422)
                created=dict(id=uid(),owner=actor.id,thread_id=t['id'],payload=draft,status='draft',revision=1,catalog_version=current['version'],registered_code=None,created_at=now())
                c.execute(insert(drafts).values(**created)); result['draft']=created
                self._audit(c,actor,'draft_create',created['id'],None,draft)
            changed=c.execute(update(threads).where(threads.c.id==t['id'],threads.c.owner==actor.id,threads.c.version==t['version']).values(
                title=user_text[:70] if t['version']==0 else t['title'],version=t['version']+1,history=history,
                candidates=t['candidates'] if result['action'] in ('compare','explain') and t['candidates'] else [{'code':v['code'],'revision':v['revision']} for v in result['candidates']],
                draft=created if created else t.get('draft'),updated_at=now()))
            if changed.rowcount!=1: raise DomainError('다른 요청이 먼저 처리되었습니다. 대화를 새로 불러와주세요.')
            result['namespace']=self.namespace
            result['thread_id']=t['id']; result['version']=t['version']+1
            c.execute(insert(turns).values(id=uid(),thread_id=t['id'],request_id=request_id,fingerprint=fingerprint,result=result))
            return result
    def list_drafts(self,actor):
        with self.engine.connect() as c:
            q=select(drafts).order_by(drafts.c.created_at.desc()).limit(100)
            if actor.role!='admin': q=q.where(drafts.c.owner==actor.id)
            return [dict(v) for v in c.execute(q).mappings()]
    def approve(self,actor,ident,body:Approval):
        admin(actor)
        if os.getenv('CODE_CATALOG_AUTHORITY','system')=='excel' and not body.external_registered:
            raise DomainError('기존 엑셀 관리 절차에서 확정한 코드번호인지 확인해주세요.',422)
        with self.transaction() as c:
            d=row(c.execute(select(drafts).where(drafts.c.id==ident).with_for_update()).mappings().first())
            if not d: raise DomainError('초안을 찾을 수 없습니다.',404)
            if d['status']=='registered':
                if d['registered_code']==body.code: return {'code':body.code,'already_registered':True}
                raise DomainError('이미 다른 코드로 등록된 초안입니다.')
            if d['revision']!=body.expected_draft_revision: raise DomainError('초안이 변경되었습니다.')
            if d['catalog_version']!=body.expected_catalog_version: raise DomainError('초안을 최신 목록으로 다시 검토해주세요.')
            version=self._bump(c,body.expected_catalog_version)
            if c.execute(select(codes.c.id).where(codes.c.code==body.code)).first(): raise DomainError('이미 사용되었거나 폐기된 코드번호입니다.')
            same=c.execute(select(codes.c.code).where(codes.c.message==d['payload']['message'],codes.c.status=='active')).first()
            if (same or d['payload'].get('candidates')) and not body.duplicate_ack:
                raise DomainError('유사·중복 후보를 검토했다는 확인이 필요합니다.')
            p=d['payload']; new=dict(id=uid(),code=body.code,message=p['message'],menu=p.get('menu',''),trigger=p.get('trigger',''),notes=p.get('explanation',''),
                status='active',revision=1,source={'kind':'approved_draft','draft_id':ident,'actor_id':actor.id},updated_at=now())
            new.update({k:v for k,v in business_values(new).items() if k in EXTRA_COLUMNS});new['added_date']=now()[:10]
            c.execute(insert(codes).values(**new))
            c.execute(update(drafts).where(drafts.c.id==ident).values(status='registered',registered_code=body.code,revision=d['revision']+1))
            self._audit(c,actor,'approve',body.code,None,new,body.reason)
            return {'code':body.code,'catalog_version':version,'index_status':'pending'}
    def review_draft(self,actor,ident,candidates,version):
        with self.transaction() as c:
            q=select(drafts).where(drafts.c.id==ident).with_for_update()
            if actor.role!='admin': q=q.where(drafts.c.owner==actor.id)
            d=row(c.execute(q).mappings().first())
            if not d: raise DomainError('초안을 찾을 수 없습니다.',404)
            if d['status']!='draft': raise DomainError('이미 처리된 초안입니다.')
            if self._state(c)['version']!=version: raise DomainError('목록이 변경되었습니다.')
            p=dict(d['payload'],candidates=[{'code':x['code'],'revision':x['revision']} for x in candidates])
            c.execute(update(drafts).where(drafts.c.id==ident).values(payload=p,catalog_version=version,revision=d['revision']+1))
            return dict(d,payload=p,catalog_version=version,revision=d['revision']+1)
    def revise_code(self,actor,code,body):
        admin(actor)
        with self.transaction() as c:
            version=self._bump(c,body.expected_catalog_version)
            old=row(c.execute(select(codes).where(codes.c.code==canonical_code(code)).with_for_update()).mappings().first())
            if not old: raise DomainError('코드를 찾을 수 없습니다.',404)
            if old['revision']!=body.expected_revision: raise DomainError('코드가 변경되었습니다.')
            vals={k:getattr(body,k) for k in ('message','menu','trigger','status')}; vals.update(revision=old['revision']+1,updated_at=now())
            vals['title']=body.message
            for key in EXTRA_COLUMNS+('notes',):
                value=getattr(body,key,None)
                if value is not None:vals[key]=value
            if vals.get('title'):vals['message']=vals['title']
            if vals['message']!=old['message'] and body.spelling_check is None:vals['spelling_check']='미검사'
            c.execute(update(codes).where(codes.c.id==old['id']).values(**vals)); self._audit(c,actor,'revise',old['code'],old,dict(old,**vals),body.reason)
            return {'code':old['code'],'catalog_version':version,'index_status':'pending'}
    def audit_log(self,actor):
        admin(actor)
        with self.engine.connect() as c: return [dict(v) for v in c.execute(select(audits).order_by(audits.c.created_at.desc()).limit(200)).mappings()]


class SampleStore(Store):
    """Immutable JSON catalogue; separate index publication and conversation scope."""
    namespace='demo'
    state_table=sample_state
    def __init__(self,base):self.engine=base.engine
    def source(self):
        with self.engine.connect() as c:
            records=[normalized_record(dict(r)) for r in c.execute(select(sample_codes).order_by(sample_codes.c.code)).mappings()]
        return records,digest(records)
    def initialize_catalog(self):
        # One-time verified import. Later startup never reads or overwrites JSON.
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO cm_sample_state (id,version,indexed_version,index_error,source_hash) VALUES (1,1,-1,'','') ON CONFLICT (id) DO NOTHING"))
            current=c.execute(select(sample_state).where(sample_state.c.id==1).with_for_update()).mappings().one()
            if c.execute(select(sample_bootstrap).where(sample_bootstrap.c.id==1)).first():return
            if c.execute(select(sample_codes.c.id).limit(1)).first():
                raise DomainError('기존 샘플 DB가 있어 초기 자료를 자동으로 덮어쓰지 않습니다.',409)
            from .inspection import sample_records
            records=sample_records();source_hash=digest(records)
            for rec in records:
                values={k:rec.get(k,'') for k in ('code','message','menu','trigger','notes','status','revision','source')+EXTRA_COLUMNS}
                c.execute(insert(sample_codes).values(id=uid(),updated_at=now(),**values))
            c.execute(insert(sample_bootstrap).values(id=1,source_hash=source_hash,count=len(records),created_at=now()))
            c.execute(update(sample_state).where(sample_state.c.id==1).values(version=current['version']+(1 if current['source_hash'] else 0),index_error='',source_hash=source_hash))
    def status(self):
        with self.engine.connect() as c:return row(c.execute(select(sample_state).where(sample_state.c.id==1)).mappings().one())
    def snapshot(self,retired=False):
        with self.engine.begin() as c:
            state_row=dict(c.execute(select(sample_state).where(sample_state.c.id==1).with_for_update()).mappings().one())
            query=select(sample_codes).order_by(sample_codes.c.code)
            if not retired:query=query.where(sample_codes.c.status=='active')
            return state_row,[normalized_record(dict(r)) for r in c.execute(query).mappings()]
    def get_code(self,code):
        try:code=canonical_code(code)
        except ValueError as exc:raise DomainError(str(exc),422) from exc
        with self.engine.connect() as c:
            rec=c.execute(select(sample_codes).where(sample_codes.c.code==code)).mappings().first()
            return normalized_record(dict(rec)) if rec else None
