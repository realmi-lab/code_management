"""Actual Chromium + actual HTTP catalogue API; external auth/AI are test doubles.
Never used by production Dockerfiles. Synthetic data stored in a temporary DB.
"""
from pathlib import Path
import os,sys,tempfile,threading,time,socket,json,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'extensions'),str(ROOT/'integration_tests')]
from fastapi.responses import HTMLResponse,Response
from fastapi.staticfiles import StaticFiles
from code_agent.store import Store
from test_api import app_for
from conftest import seed,use_list
from playwright.sync_api import sync_playwright,expect
import uvicorn

HOST='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>body{margin:0;background:#f2f5f1;font:14px sans-serif}.banner{padding:8px 18px;color:#58645b;font-size:12px}iframe{width:100%;height:calc(100vh - 33px);border:0;background:white}</style></head><body><div class="banner">합성 데이터로 검증하는 통합 작업실 · 원본 로그인/AI 응답은 테스트 대역</div><iframe id="workspace" title="알림 코드 작업실" src="/api/code-catalog/ui/index.html" allow="clipboard-write"></iframe><script src="/test-host.js"></script></body></html>'''
SCRIPT='''const f=document.getElementById('workspace');function send(){f.contentWindow.postMessage({type:'catalog-auth',token:'test-admin'},location.origin);}window.addEventListener('message',e=>{if(e.origin===location.origin&&e.source===f.contentWindow&&e.data?.type==='catalog-ready')send();});f.addEventListener('load',send);'''

def main():
 # The approval step checks the Excel confirmation box, which only renders in excel authority.
 os.environ['CODE_CATALOG_AUTHORITY']='excel'
 out=Path(os.getenv('VERIFICATION_DIR',str(ROOT/'docs/verification')));out.mkdir(parents=True,exist_ok=True)
 results=[];server=None;thread=None
 report={'browser':'Chromium','transport':'real-loopback-HTTP','authentication':'test dependency; NOT upstream JWT','retrieval_and_LLM':'ScriptedGateway test double','checks':results,'passed':False}
 try:
  with tempfile.TemporaryDirectory() as tmp:
   store=Store('sqlite:///'+tmp+'/browser.db');store.initialize();seed(store);app=app_for(store)
   app.mount('/api/code-catalog/ui',StaticFiles(directory=ROOT/'extensions/code_agent/static',html=True),name='ui')
   @app.get('/test-host')
   def host():return HTMLResponse(HOST)
   @app.get('/test-host.js')
   def script():return Response(SCRIPT,media_type='text/javascript')
   with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
   thread=threading.Thread(target=server.run,daemon=True);thread.start()
   for _ in range(100):
    if server.started:break
    time.sleep(.05)
   errors=[]
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or ('/usr/bin/chromium' if os.path.exists('/usr/bin/chromium') else None),headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1320,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{port}/test-host',wait_until='networkidle')
    ui=page.frame_locator('#workspace')
    expect(ui.locator('#app')).to_be_visible();results.append({'name':'same_origin_auth_handoff','passed':True})
    use_list(ui,'production')
    ui.locator('#question').fill('AT-1923 문구 알려줘');ui.locator('#send').click()
    expect(ui.locator('.message').first).to_have_text('메뉴확인 30초 이후에 인증해주세요.')
    results.append({'name':'exact_original_message','passed':True})
    ui.locator('#question').fill('인증 대기 알림 찾아줘');ui.locator('#send').click()
    expect(ui.locator('#send')).to_have_text('보내기 ↑');expect(ui.locator('.result-group')).to_have_count(2)
    results.append({'name':'conversational_search','passed':True})
    expect(ui.locator('#proposed, #ask-form details')).to_have_count(0)  # options menu removed
    ui.locator('#action').select_option('compare')
    ui.locator('#question').fill('두 번째 후보와 "30초 이내에 인증해주세요." 비교해줘');ui.locator('#send').click()
    expect(ui.locator('.difference').last).to_contain_text('조건')
    results.append({'name':'followup_ordinal_and_condition_comparison','passed':True})
    ui.locator('#action').select_option('draft');ui.locator('#question').fill('"메뉴를 확인하고 다시 진행해주세요." 이 문구로 새 초안 작성해줘');ui.locator('#send').click()
    expect(ui.locator('.draft-card .message')).to_have_text('메뉴를 확인하고 다시 진행해주세요.')
    results.append({'name':'new_draft_not_automatically_registered','passed':True})
    # Capture the resting frame: entry motion is still running right after the turn.
    page.wait_for_timeout(600)
    page.screenshot(path=str(out/'integrated-desktop.png'),full_page=True)
    ui.locator('[data-view=drafts]').click();expect(ui.locator('#draft-list .card')).to_have_count(1)
    ui.get_by_role('button',name='등록 검토',exact=True).click();ui.locator('#approve-code').fill('AT-2000');ui.locator('#approve-reason').fill('합성 브라우저 테스트 승인');ui.locator('#duplicate-ack').check();ui.locator('#external-ack').check();ui.locator('#approve-submit').click()
    expect(ui.locator('#draft-list')).to_contain_text('등록됨 AT-2000');results.append({'name':'explicit_admin_registration','passed':True})
    ui.locator('[data-view=catalog]').click();use_list(ui,'production');expect(ui.locator('#catalog-list')).to_contain_text('AT-2000');results.append({'name':'registered_catalogue_updated','passed':True})
    expect(ui.get_by_role('tab',name='전체 코드',exact=True)).to_be_visible()
    expect(ui.locator('#catalog-list table')).to_be_visible()
    ui.locator('#catalog-query').fill('AT-2000');ui.locator('#catalog-form').get_by_role('button',name='검색',exact=True).click()
    expect(ui.locator('#catalog-list tbody tr')).to_have_count(1)
    ui.locator('#catalog-list .catalog-code').click();expect(ui.locator('#catalog-detail')).to_be_visible()
    expect(ui.locator('#catalog-detail')).to_contain_text('메뉴를 확인하고 다시 진행해주세요.')
    ui.locator('#catalog-detail').get_by_role('button',name='닫기',exact=True).click()
    ui.locator('#catalog-query').fill('');ui.locator('#catalog-form').get_by_role('button',name='검색',exact=True).click()
    use_list(ui,'demo')
    expect(ui.locator('#catalog-count')).to_contain_text('300개')
    expect(ui.locator('#catalog-list tbody tr')).to_have_count(30)
    ui.locator('#catalog-status').select_option('retired');ui.locator('#catalog-form').get_by_role('button',name='검색',exact=True).click()
    expect(ui.locator('#catalog-list tbody tr')).to_have_count(21)
    expect(ui.locator('#catalog-list')).to_contain_text('EX-0901')
    expect(ui.locator('#catalog-list tbody .btn').first).to_be_disabled()
    ui.get_by_role('tab',name='문구 비교',exact=True).click()
    ui.locator('#compare-message').fill('30초 이내에 인증해주세요.')
    ui.locator('#compare-form').get_by_role('button',name='문구 비교',exact=True).click()
    expect(ui.locator('#compare-results')).to_contain_text('조건 방향이 다릅니다.')
    ui.get_by_role('tab',name='기획서 검토',exact=True).click()
    ui.locator('#review-text').fill('EX-0201\nEX-0901\nEX-9999\nAT-1923: 30초 이내에 인증해주세요.')
    ui.locator('#review-form').get_by_role('button',name='검토',exact=True).click()
    expect(ui.locator('#review-results .review-item')).to_have_count(4)
    expect(ui.locator('#review-results')).to_contain_text('미등록 코드: EX-9999')
    expect(ui.locator('#review-results')).to_contain_text('조건 방향이 다릅니다.')
    page.screenshot(path=str(out/'restored-review.png'),full_page=True)
    use_list(ui,'production')
    results.append({'name':'restored_catalog_compare_review_and_isolated_github_samples','passed':True})
    expect(ui.locator('[data-view=imports], #imports, input[type=file], #catalog-import')).to_have_count(0)
    results.append({'name':'file_import_controls_removed','passed':True})
    ui.locator('[data-view=audit]').click();expect(ui.locator('#audit-list')).to_contain_text('approve');results.append({'name':'approval_audit_user_and_reason','passed':True})
    expect(ui.locator('#audit-list table')).to_be_visible()
    ui.locator('#audit-list details').first.locator('summary').click()
    expect(ui.locator('#audit-list details').first.locator('pre')).to_be_visible()
    results.append({'name':'audit_table_actor_and_before_after_detail','passed':True})
    ui.locator('[data-view=chat]').click();ui.locator('#threads button').first.click();expect(ui.locator('#messages')).to_contain_text('메뉴를 확인하고 다시 진행해주세요.')
    results.append({'name':'conversation_persisted_and_restored','passed':True})
    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(400)
    frame=page.frames[1];overflow=frame.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    assert not overflow,'mobile viewport overflows horizontally'
    page.screenshot(path=str(out/'integrated-mobile.png'),full_page=True);results.append({'name':'mobile_390px_no_horizontal_overflow','passed':True})
    assert not errors,errors
    results.append({'name':'no_browser_javascript_errors','passed':True});report['passed']=True;report['javascript_errors']=errors
    browser.close()
   store.engine.dispose()
 except Exception as exc:
  report['error']=type(exc).__name__+': '+str(exc);report['traceback']=traceback.format_exc();raise
 finally:
  if server:server.should_exit=True
  if thread:thread.join(timeout=3)
  (out/'browser-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
  print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
