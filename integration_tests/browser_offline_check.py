"""Chromium renders production workspace files; actual API via TestClient bridge.
Does NOT disable browser policy. Does NOT verify HTTP/CSP, original Next/JWT, or LLM.
Synthetic authentication, model, and clipboard exist only in this test script.
"""
from pathlib import Path
import os,sys, tempfile, json, traceback, base64, re
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'extensions'),str(ROOT/'integration_tests')]
from code_agent.store import Store
from test_api import app_for
from conftest import seed,use_list
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
BRIDGE=r'''
// about:blank has an opaque origin. The real parent's postMessage is replaced
// ONLY in this offline harness; same-origin browser security is not tested here.
window.postMessage=()=>{};
window.__copied='';Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async s=>{window.__copied=s;}}});
window.fetch=async(url,options={})=>{
 const p={path:String(url),method:options.method||'GET',headers:options.headers||{},body:options.body||null};
 if(options.body instanceof FormData){p.body=null;p.form=[];for(const [key,v] of options.body.entries()){
  if(v instanceof File){const bytes=new Uint8Array(await v.arrayBuffer());let s='';for(const b of bytes)s+=String.fromCharCode(b);p.form.push({key,filename:v.name,type:v.type,body:btoa(s)});}else p.form.push({key,value:v});
 }}
 const r=await window.__api(p);return new Response(Uint8Array.from(atob(r.body),x=>x.charCodeAt(0)),{status:r.status,headers:r.headers});
};
'''
def main():
 # The approval step checks the Excel confirmation box, which only renders in excel authority.
 os.environ['CODE_CATALOG_AUTHORITY']='excel'
 out=Path(os.getenv('VERIFICATION_DIR',str(ROOT/'docs/verification')));out.mkdir(parents=True,exist_ok=True)
 checks=[];errors=[]
 report={'passed':False,'browser':'Chromium','transport':'offline assets + real FastAPI TestClient bridge','auth':'synthetic dependency + synthetic postMessage; NOT original JWT/Next','model':'ScriptedGateway','clipboard':'test double','checks':checks,'javascript_errors':errors}
 def checked(name):checks.append({'name':name,'passed':True})
 try:
  with tempfile.TemporaryDirectory() as tmp:
   store=Store('sqlite:///'+tmp+'/browser.db');store.initialize();seed(store)
   with TestClient(app_for(store)) as client,sync_playwright() as p:
    def bridge(source,v):
     kwargs={'headers':v['headers']}
     if 'form' in v:
      kwargs['data']={};kwargs['files']={}
      for x in v['form']:
       if 'filename' in x:kwargs['files'][x['key']]=(x['filename'],base64.b64decode(x['body']),x['type'])
       else:kwargs['data'][x['key']]=x['value']
     else:kwargs['content']=v.get('body')
     r=client.request(v['method'],v['path'],**kwargs)
     if r.status_code>=400:print('TEST_API_ERROR',v['path'],r.status_code,r.text[:500])
     return {'status':r.status_code,'headers':dict(r.headers),'body':base64.b64encode(r.content).decode()}
    b=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or ('/usr/bin/chromium' if os.path.exists('/usr/bin/chromium') else None),headless=True,args=['--no-sandbox'])
    ctx=b.new_context(viewport={'width':1320,'height':960});ctx.expose_binding('__api',bridge)
    page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    html=(ROOT/'extensions/code_agent/static/index.html').read_text()
    html=re.sub(r'<link[^>]*>','',html);html=re.sub(r'<script[^>]*>.*?</script>','',html,flags=re.S)
    page.set_content(html);page.add_style_tag(path=str(ROOT/'extensions/code_agent/static/styles.css'))
    page.add_script_tag(content=BRIDGE);page.add_script_tag(path=str(ROOT/'extensions/code_agent/static/app.js'))
    page.evaluate("window.dispatchEvent(new MessageEvent('message',{data:{type:'catalog-auth',token:'test-admin'},origin:location.origin,source:window}));")
    ui=page;expect(ui.locator('#app')).to_be_visible();checked('workspace_render_and_test_identity')
    use_list(ui,'production')
    ui.locator('#question').fill('AT-1923 문구 알려줘');ui.locator('#send').click()
    expect(ui.locator('.message').first).to_have_text('메뉴확인 30초 이후에 인증해주세요.');checked('exact_original_message')
    ui.get_by_role('button',name='기획서에 복사').first.click()
    page.wait_for_function("window.__copied.includes('메뉴확인 30초 이후에 인증해주세요.')");checked('copy_payload_original_preserved')
    ui.locator('#question').fill('인증 대기 알림 찾아줘');ui.locator('#send').click()
    expect(ui.locator('.result-group')).to_have_count(2);expect(ui.locator('#send')).to_have_text('보내기 ↑');checked('conversational_search')
    expect(ui.locator('#proposed, #ask-form details')).to_have_count(0)  # options menu removed
    ui.locator('#action').select_option('compare')
    ui.locator('#question').fill('두 번째 후보와 "30초 이내에 인증해주세요." 비교해줘');ui.locator('#send').click()
    expect(ui.locator('.difference').last).to_contain_text('조건');checked('ordinal_selection_and_condition_comparison')
    ui.locator('#action').select_option('draft');ui.locator('#question').fill('"메뉴를 확인하고 다시 진행해주세요." 이 문구로 새 초안 작성해줘');ui.locator('#send').click()
    expect(ui.locator('.draft-card .message')).to_have_text('메뉴를 확인하고 다시 진행해주세요.');checked('draft_not_registered_automatically')
    ui.locator('#messages').evaluate("e=>e.scrollTo({top:e.scrollHeight,behavior:'instant'})")
    # Capture the resting frame: entry motion is still running right after the turn.
    page.wait_for_timeout(600)
    page.screenshot(path=str(out/'integrated-desktop.png'),full_page=True)
    ui.locator('[data-view=drafts]').click();expect(ui.locator('#draft-list .card')).to_have_count(1)
    ui.get_by_role('button',name='등록 검토',exact=True).click();ui.locator('#approve-code').fill('AT-2000');ui.locator('#approve-reason').fill('합성 브라우저 테스트 승인');ui.locator('#duplicate-ack').check();ui.locator('#external-ack').check();ui.locator('#approve-submit').click()
    expect(ui.locator('#draft-list')).to_contain_text('등록됨 AT-2000');checked('explicit_admin_registration')
    ui.locator('[data-view=catalog]').click();use_list(ui,'production');expect(ui.locator('#catalog-list')).to_contain_text('AT-2000');checked('registered_item_in_catalogue')
    expect(ui.locator('[data-view=imports], #imports, input[type=file]')).to_have_count(0);checked('file_import_controls_removed')
    seed(store,'코드번호,등록문구\nAT-2001,<img src=x onerror=window.__injected=1>테스트 추가 알림\n')
    ui.locator('[data-view=catalog]').click();expect(ui.locator('#catalog-list')).to_contain_text('<img src=x onerror=window.__injected=1>')
    assert ui.locator('#catalog-list img').count()==0 and page.evaluate('window.__injected === undefined');checked('stored_html_rendered_as_text_not_code')
    ui.locator('[data-view=audit]').click();expect(ui.locator('#audit-list')).to_contain_text('approve');checked('approval_audit_visible')
    ui.locator('[data-view=chat]').click();ui.locator('#threads button').first.click();expect(ui.locator('#messages')).to_contain_text('메뉴를 확인하고 다시 진행해주세요.')
    expect(ui.locator('.draft-card')).to_contain_text('등록됨 AT-2000');checked('conversation_restore_reflects_registration')
    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200)
    assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth'),'horizontal mobile overflow'
    ui.locator('#messages').evaluate("e=>e.scrollTo({top:e.scrollHeight,behavior:'instant'})")
    page.wait_for_timeout(400)
    page.screenshot(path=str(out/'integrated-mobile.png'),full_page=True);checked('mobile_390px_without_horizontal_overflow')
    assert not errors,errors;checked('no_javascript_errors');report['passed']=True
    b.close()
   store.engine.dispose()
 except Exception as e:
  report.update(error=str(e),traceback=traceback.format_exc())
  try:report['page_text']=page.locator('body').inner_text();page.screenshot(path=str(out/'browser-offline-failure.png'),full_page=True)
  except Exception:pass
  raise
 finally:
  (out/'browser-offline-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
