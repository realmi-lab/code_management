from __future__ import annotations
import re
from fastapi import HTTPException
from .db import uid,now,dumps,decode_draft
from .models import canonical_code
from .compare import compare_message

class Workflow:
    def __init__(self,db,settings): self.db=db; self.settings=settings

    def get_draft(self,namespace,ident,con=None):
        if con is None:
            with self.db.connect() as c: return self.get_draft(namespace,ident,c)
        row=con.execute('SELECT * FROM drafts WHERE namespace=? AND id=?',(namespace,ident)).fetchone()
        if not row: raise HTTPException(404,'초안을 찾을 수 없습니다.')
        return decode_draft(row)

    def create_draft(self,req,message):
        target_revision=None; target_code=req.target_code
        with self.db.connect(write=True) as con:
            if req.kind=='revision':
                if not target_code: raise HTTPException(422,'문구 변경 초안은 대상 코드번호가 필요합니다.')
                try: target_code=canonical_code(target_code)
                except ValueError as exc: raise HTTPException(422,str(exc)) from exc
                target=self.db.get_code(req.namespace,target_code,con)
                if not target: raise HTTPException(404,'변경할 코드가 없습니다.')
                target_revision=target['revision']
            elif target_code:
                raise HTTPException(422,'신규 초안에는 변경 대상 코드를 지정할 수 없습니다.')
            ident=uid(); stamp=now()
            con.execute('''INSERT INTO drafts(id,namespace,message,menu,trigger_text,notes,kind,target_code,target_revision,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(ident,req.namespace,message,req.menu,req.trigger,req.notes,req.kind,target_code,target_revision,stamp,stamp))
            self.db.audit(con,req.namespace,'draft.created',ident,None,{'message':message,'kind':req.kind},'초안 작성 — 정식 코드 미발급')
            return self.get_draft(req.namespace,ident,con)

    def handoff(self,ns,ident,expected_revision):
        with self.db.connect(write=True) as con:
            draft=self.get_draft(ns,ident,con)
            if draft['state']=='registered': raise HTTPException(409,'이미 등록된 초안입니다.')
            if draft['revision']!=expected_revision: raise HTTPException(409,'초안이 변경되었습니다. 새로고침 후 확인해주세요.')
            if draft['state']=='pending_external': return draft
            con.execute("UPDATE drafts SET state='pending_external',revision=revision+1,updated_at=? WHERE id=?",(now(),ident))
            after=self.get_draft(ns,ident,con)
            self.db.audit(con,ns,'draft.handoff',ident,draft,after,'엑셀 담당자에게 등록 요청 — 등록 완료가 아님')
            return after

    def approve(self,ident,req):
        # Demo uses its own numbering authority, without changing live authority.
        if req.namespace=='live' and self.settings.authority!='system':
            raise HTTPException(409,'공식 목록이 엑셀입니다. 초안을 내보내고 담당자가 번호를 확정한 엑셀을 가져와주세요. 앱에서 정식 번호를 임의 발급하지 않습니다.')
        with self.db.connect(write=True) as con:
            draft=self.get_draft(req.namespace,ident,con)
            if draft['state']=='registered':
                # Do not create another code after a lost response / repeated click.
                if req.code and req.code.upper()!=draft['registered_code']:
                    raise HTTPException(409,'이미 다른 번호로 등록된 초안입니다.')
                return {'draft':draft,'code':self.db.get_code(req.namespace,draft['registered_code'],con),'idempotent':True}
            if draft['revision']!=req.expected_revision: raise HTTPException(409,'초안 버전이 달라졌습니다. 다시 확인해주세요.')
            if self.db.version(req.namespace,con)!=req.expected_catalog_version:
                raise HTTPException(409,'검토 이후 코드 목록이 변경되었습니다. 최신 목록으로 중복을 재검토해주세요.')
            all_codes=self.db.all_codes(req.namespace,True,con)
            similar=[]
            for row in all_codes:
                if row['code']==draft.get('target_code'): continue
                comparison=compare_message(draft['message'],row,menu=draft['menu'],trigger=draft['trigger'])
                if comparison['wording_equal'] or comparison['similarity']>=0.67:
                    similar.append({'code':row['code'],'message':row['message'],'match':comparison})
            if similar and not req.duplicate_ack:
                raise HTTPException(409,{'message':'유사·동일 문구가 있습니다. 차이를 검토하고 확인 항목을 선택해주세요.','candidates':similar[:12]})
            if not req.reason.strip(): raise HTTPException(422,'등록 이유를 입력해주세요.')
            if draft['kind']=='revision':
                code=draft['target_code']; before=self.db.get_code(req.namespace,code,con)
                if not before or before['revision']!=draft['target_revision']:
                    raise HTTPException(409,'원본 문구가 변경되었습니다. 최신 원본으로 변경 초안을 다시 작성해주세요.')
                if req.code and req.code.upper()!=code: raise HTTPException(422,'문구 변경에서는 코드번호를 바꿀 수 없습니다.')
                con.execute('''UPDATE codes SET message=?,menu=?,trigger_text=?,notes=?,revision=revision+1,updated_at=?,source_json=?
                    WHERE namespace=? AND code=?''',(draft['message'],draft['menu'],draft['trigger'],draft['notes'],now(),
                    dumps({'kind':'approved_revision','draft_id':ident,'previous_source':before['source']}),req.namespace,code))
                con.execute('DELETE FROM embeddings WHERE code_id=?',(before['id'],))
                self.db.audit(con,req.namespace,'code.revised',code,before,draft,req.reason)
            else:
                code=self.allocate(con,req)
                if self.db.get_code(req.namespace,code,con): raise HTTPException(409,'이미 사용 중인 코드번호입니다. 폐기 번호도 재사용하지 않습니다.')
                row={'code':code,'message':draft['message'],'menu':draft['menu'],'trigger':draft['trigger'],'notes':draft['notes'],'status':'active'}
                self.db.insert_code(con,req.namespace,row,{'kind':'approved','draft_id':ident})
                self.db.audit(con,req.namespace,'code.approved',code,None,row,req.reason)
            con.execute("UPDATE drafts SET state='registered',registered_code=?,revision=revision+1,updated_at=? WHERE id=?",(code,now(),ident))
            self.db.bump(con,req.namespace)
            return {'draft':self.get_draft(req.namespace,ident,con),'code':self.db.get_code(req.namespace,code,con),'idempotent':False}

    def allocate(self,con,req):
        if req.code:
            try: return canonical_code(req.code)
            except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        if not req.prefix:
            raise HTTPException(422,'번호 발급 규칙이 없으면 관리자가 확정한 코드번호를 직접 입력해주세요.')
        rules=self.settings.code_rules
        if req.namespace=='demo': rules={'EX':{'start':1000,'width':4}}
        rule=rules.get(req.prefix)
        if not rule: raise HTTPException(422,'해당 접두어의 번호 발급 규칙이 설정되지 않았습니다.')
        row=con.execute('SELECT next_number FROM sequences WHERE namespace=? AND prefix=?',(req.namespace,req.prefix)).fetchone()
        n=max(int(row[0]) if row else rule['start'],rule['start'])
        while True:
            code=f'{req.prefix}-{n:0{rule["width"]}d}'
            if len(str(n))>12: raise HTTPException(409,'번호 범위를 초과했습니다.')
            if not self.db.get_code(req.namespace,code,con): break
            n+=1
        con.execute('INSERT OR REPLACE INTO sequences(namespace,prefix,next_number) VALUES(?,?,?)',(req.namespace,req.prefix,n+1))
        return code

    def update_draft(self,ident,req):
        with self.db.connect(write=True) as con:
            before=self.get_draft(req.namespace,ident,con)
            if before['state']=='registered':
                raise HTTPException(409,'등록된 초안은 수정할 수 없습니다. 등록 코드에서 변경 초안을 작성해주세요.')
            if before['revision']!=req.expected_revision:
                raise HTTPException(409,'초안이 변경되었습니다. 최신 내용을 다시 확인해주세요.')
            con.execute("""UPDATE drafts SET message=?,menu=?,trigger_text=?,notes=?,
                state='draft',revision=revision+1,updated_at=? WHERE id=?""",
                (req.message,req.menu,req.trigger,req.notes,now(),ident))
            after=self.get_draft(req.namespace,ident,con)
            self.db.audit(con,req.namespace,'draft.updated',ident,before,after,req.reason)
            return after

    def is_imported(self,row,ns,con):
        import_id=row['source'].get('import_id')
        if not import_id: return False
        return con.execute('SELECT 1 FROM imports WHERE id=? AND namespace=? AND consumed=1',
                           (import_id,ns)).fetchone() is not None

    @staticmethod
    def external_differences(draft,row):
        labels={'message':'문구','menu':'메뉴','trigger':'노출 조건'}
        return [label for key,label in labels.items() if draft[key]!=row[key]]

    def external_matches(self,ns,ident):
        with self.db.connect() as con:
            # Pair the displayed candidates with the version of the same snapshot.
            con.execute('BEGIN')
            draft=self.get_draft(ns,ident,con)
            imported_ids={row[0] for row in con.execute(
                'SELECT id FROM imports WHERE namespace=? AND consumed=1',(ns,))}
            items=[]
            for row in self.db.all_codes(ns,False,con):
                if row['source'].get('import_id') not in imported_ids: continue
                marker='[draft:'+ident+']' in row['notes']
                if not (marker or row['message']==draft['message'] or row['code']==draft['target_code']):
                    continue
                if draft['kind']=='revision' and row['code']!=draft['target_code']: continue
                items.append({**row,'differences':self.external_differences(draft,row),'draft_marker':marker})
            version=self.db.version(ns,con)
            con.execute('COMMIT')
        items.sort(key=lambda r:(bool(r['differences']),not r['draft_marker'],r['code']))
        return {'draft':draft,'items':items[:20],'total':len(items),
                'catalog_version':version,'marker':'[draft:'+ident+']'}

    def link_external(self,ident,req):
        with self.db.connect(write=True) as con:
            before=self.get_draft(req.namespace,ident,con)
            if before['state']=='registered':
                if before['registered_code']==req.code:
                    return {'draft':before,'idempotent':True}
                raise HTTPException(409,'이미 다른 코드와 연결된 초안입니다.')
            if before['state']!='pending_external':
                raise HTTPException(409,'먼저 엑셀 등록 요청을 표시해주세요.')
            if before['revision']!=req.expected_revision or self.db.version(req.namespace,con)!=req.expected_catalog_version:
                raise HTTPException(409,'초안 또는 코드 목록이 변경되었습니다. 다시 확인해주세요.')
            row=self.db.get_code(req.namespace,req.code,con)
            if not row or row['status']!='active' or not self.is_imported(row,req.namespace,con):
                raise HTTPException(409,'확정 엑셀에서 가져온 사용 중인 코드만 연결할 수 있습니다.')
            if before['kind']=='revision' and row['code']!=before['target_code']:
                raise HTTPException(409,'문구 변경 초안은 기존 대상 코드와만 연결할 수 있습니다.')
            differences=self.external_differences(before,row)
            if differences and not req.differences_ack:
                raise HTTPException(409,'초안과 등록된 '+', '.join(differences)+'이 다릅니다. 차이를 확인해주세요.')
            con.execute("""UPDATE drafts SET state='registered',registered_code=?,
                revision=revision+1,updated_at=? WHERE id=?""",(row['code'],now(),ident))
            after=self.get_draft(req.namespace,ident,con)
            self.db.audit(con,req.namespace,'draft.external_linked',ident,before,
                          {'draft':after,'code_revision':row['revision'],'differences':differences},req.reason)
            return {'draft':after,'idempotent':False}

    def reconcile_import(self,con,ns,codes):
        """Link only one unambiguous, imported marker with exact wording/context."""
        touched=set(codes)
        if not touched: return []
        pending={r['id']:decode_draft(r) for r in con.execute(
            "SELECT * FROM drafts WHERE namespace=? AND state='pending_external'",(ns,))}
        if not pending: return []
        imported_ids={row[0] for row in con.execute(
            'SELECT id FROM imports WHERE namespace=? AND consumed=1',(ns,))}
        matches={}
        # Count marker references across the current catalog BEFORE applying exact
        # text/target filters. A conflicting reference in a previous import must
        # require manual review, just as two references in this import do.
        for row in self.db.all_codes(ns,False,con):
            markers=set(re.findall(r'\[draft:([^\]\r\n]+)\]',row['notes']))
            for ident in markers & pending.keys():
                matches.setdefault(ident,[]).append((row,markers))
        linked=[]
        for ident,choices in matches.items():
            if len(choices)!=1: continue
            row,markers=choices[0]
            before=pending[ident];code=row['code']
            if code not in touched or markers!={ident}: continue
            if row['source'].get('import_id') not in imported_ids: continue
            if self.external_differences(before,row): continue
            if before['kind']=='revision' and before['target_code']!=code: continue
            con.execute("""UPDATE drafts SET state='registered',registered_code=?,
                revision=revision+1,updated_at=? WHERE id=?""",(code,now(),ident))
            after=self.get_draft(ns,ident,con)
            self.db.audit(con,ns,'draft.external_linked',ident,before,after,
                          '확정 가져오기: 초안 ID와 문구·메뉴·조건이 정확히 일치')
            linked.append({'draft_id':ident,'code':code})
        return linked
