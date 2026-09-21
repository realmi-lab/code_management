"""Native loopback HTTP API smoke. External authentication/AI are explicit test doubles."""
from pathlib import Path
import sys,json,tempfile,socket,threading,time,uuid,os
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'extensions'),str(ROOT/'integration_tests')]
import httpx,uvicorn
from fastapi.staticfiles import StaticFiles
from conftest import seed
from test_api import app_for
from code_agent.store import Store

def main():
 out=Path(os.getenv('VERIFICATION_DIR',str(ROOT/'docs/verification')));out.mkdir(parents=True,exist_ok=True)
 checks=[];server=None;thread=None;store=None;report={'passed':False,'transport':'real localhost HTTP via httpx','auth_and_model':'test doubles; NOT upstream services','checks':checks}
 try:
  with tempfile.TemporaryDirectory() as tmp:
   store=Store('sqlite:///'+tmp+'/http.db');store.initialize();seed(store);app=app_for(store)
   app.mount('/api/code-catalog/ui',StaticFiles(directory=ROOT/'extensions/code_agent/static',html=True))
   with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'));thread=threading.Thread(target=server.run,daemon=True);thread.start()
   for _ in range(100):
    if server.started:break
    time.sleep(.03)
   with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=20,trust_env=False) as c:
    assert c.get('/api/code-catalog/status').status_code==401;checks.append('unauthenticated_401')
    h={'Authorization':'Bearer test-admin'}
    assert c.get('/api/code-catalog/status',headers=h).json()['user']['id']==1;checks.append('authenticated_status')
    r=c.get('/api/code-catalog/ui/index.html');assert r.status_code==200 and '알림 코드' in r.text;checks.append('static_workspace_HTTP')
    t=c.post('/api/code-catalog/threads',headers=h).json();request={'request_id':str(uuid.uuid4()),'expected_version':0,'text':'AT-1923'}
    r=c.post('/api/code-catalog/threads/'+t['id']+'/turn',headers=h,json=request);r.raise_for_status()
    assert r.json()['candidates'][0]['message']=='메뉴확인 30초 이후에 인증해주세요.';checks.append('exact_lookup_HTTP')
    assert c.post('/api/code-catalog/threads/'+t['id']+'/turn',headers=h,json=request).json()==r.json();checks.append('retry_idempotency_HTTP')
    assert c.get('/api/code-catalog/threads/'+t['id'],headers={'Authorization':'Bearer test-other'}).status_code==404;checks.append('thread_owner_isolation_HTTP')
    payload={'request_id':str(uuid.uuid4()),'expected_version':1,'text':'이 문구로 초안 작성해줘','action':'draft','proposed_message':'테스트 확인 안내입니다.'}
    r=c.post('/api/code-catalog/threads/'+t['id']+'/turn',headers=h,json=payload);r.raise_for_status();d=r.json()['draft'];assert d['status']=='draft';checks.append('draft_creation_HTTP')
    r=c.post('/api/code-catalog/drafts/'+d['id']+'/approve',headers=h,json={'expected_catalog_version':d['catalog_version'],'expected_draft_revision':d['revision'],'code':'AT-2222','reason':'합성 HTTP 테스트 승인','duplicate_ack':True,'external_registered':True});r.raise_for_status();assert r.json()['code']=='AT-2222';checks.append('explicit_approval_HTTP')
    assert c.get('/api/code-catalog/codes/AT-2222',headers=h).json()['message']=='테스트 확인 안내입니다.';checks.append('registered_original_HTTP')
    assert any(x['action']=='approve' and x['actor']==1 for x in c.get('/api/code-catalog/audit',headers=h).json());checks.append('audit_HTTP')
   server.should_exit=True;thread.join(3);store.engine.dispose();report['passed']=True
 except Exception as e:report['error']=type(e).__name__+': '+str(e);raise
 finally:
  if server:server.should_exit=True
  if thread:thread.join(3)
  (out/'native-http-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
