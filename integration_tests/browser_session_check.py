"""Actual Chromium + actual HTTP: the workspace survives the shell remounting its iframe.

Covers what the planner sees after visiting another screen and coming back: the open tab,
list, conversation and last comparison are restored, and a turn that was still running is
shown as running until the server finishes it (nothing is re-sent). Also covers the "?"
help popovers and the thread-title tooltip. External auth/AI are test doubles, as in
browser_check.py; this is NOT upstream JWT, Next or a live model.
"""
from pathlib import Path
import json,os,socket,sys,tempfile,threading,time,traceback,uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'extensions'),str(ROOT/'integration_tests')]
from fastapi.responses import HTMLResponse,Response
from fastapi.staticfiles import StaticFiles
from code_agent.store import Store
from test_api import app_for
from conftest import seed,use_list
from browser_check import HOST,SCRIPT
from playwright.sync_api import sync_playwright,expect
import httpx,uvicorn

LONG_TITLE='인증번호를 입력하기 전에 메뉴를 확인하고 30초가 지나야 한다는 안내 알림이 있는지 찾아줘'


def main():
 os.environ['CODE_CATALOG_AUTHORITY']='excel'
 out=Path(os.getenv('VERIFICATION_DIR',str(ROOT/'docs/verification')));out.mkdir(parents=True,exist_ok=True)
 checks=[];errors=[];server=None;thread=None
 report={'browser':'Chromium','transport':'real-loopback-HTTP','authentication':'test dependency; NOT upstream JWT','retrieval_and_LLM':'ScriptedGateway test double','checks':checks,'passed':False,'javascript_errors':errors}
 def checked(name):checks.append({'name':name,'passed':True})
 try:
  with tempfile.TemporaryDirectory() as tmp:
   store=Store('sqlite:///'+tmp+'/session.db');store.initialize();seed(store);app=app_for(store)
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
   base=f'http://127.0.0.1:{port}';api=httpx.Client(base_url=base+'/api/code-catalog',headers={'Authorization':'Bearer test-admin'},timeout=30)
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or ('/usr/bin/chromium' if os.path.exists('/usr/bin/chromium') else None),headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1320,'height':900});page.on('pageerror',lambda e:errors.append(str(e)))
    def open_host():
     page.goto(base+'/test-host',wait_until='networkidle')
     ui=page.frame_locator('#workspace');expect(ui.locator('#app')).to_be_visible();return ui
    frame=lambda:page.frames[1]
    ui=open_host()

    # --- a conversation in the real list, then the remount restores list + thread
    use_list(ui,'production')
    ui.locator('#question').fill('AT-1923 문구 알려줘');ui.locator('#send').click()
    expect(ui.locator('.message').first).to_have_text('메뉴확인 30초 이후에 인증해주세요.')
    thread_id=frame().evaluate('thread.id');version=frame().evaluate('thread.version')
    ui=open_host()
    expect(ui.locator('#catalog-namespace')).to_have_value('production')
    expect(ui.locator('.message').first).to_have_text('메뉴확인 30초 이후에 인증해주세요.')
    expect(ui.locator(f'#threads button[data-id="{thread_id}"]')).to_have_attribute('aria-current','true')
    checked('remount_restores_list_and_open_conversation')

    # --- a turn still running when the planner left: shown as running, then the answer lands
    frame().evaluate("""([id,v])=>sessionStorage.setItem('code-workspace:v1:'+user.id+':turn',JSON.stringify({namespace:'production',threadId:id,version:v,text:'인증 대기 알림 찾아줘',startedAt:Date.now()}))""",[thread_id,version])
    ui=open_host()
    expect(ui.locator('.bubble.is-pending')).to_contain_text('처리하고 있습니다')
    expect(ui.locator('#send')).to_have_attribute('aria-busy','true')
    expect(ui.locator('.bubble.user').last).to_have_text('인증 대기 알림 찾아줘')
    ui.locator('#threads button').first.click()  # switching threads mid-answer is refused, not half-done
    expect(ui.locator('#notice')).to_contain_text('답변을 받는 중')
    r=api.post(f'/threads/{thread_id}/turn',params={'namespace':'production'},json={'request_id':str(uuid.uuid4()),'expected_version':version,'text':'인증 대기 알림 찾아줘','action':'auto'})
    assert r.status_code==200,r.text
    expect(ui.locator('.bubble.is-pending')).to_have_count(0,timeout=15000)
    expect(ui.locator('#send')).not_to_have_attribute('aria-busy','true')
    expect(ui.locator('#messages')).to_contain_text('인증 대기 알림 찾아줘')
    assert frame().evaluate("sessionStorage.getItem('code-workspace:v1:'+user.id+':turn')") is None
    # Exactly one turn landed: the page waited for ours instead of re-sending its own.
    assert api.get(f'/threads/{thread_id}',params={'namespace':'production'}).json()['version']==version+1
    checked('in_flight_turn_resumed_without_resend')

    # --- a stale in-flight record (older than the server timeout) is dropped, not shown
    frame().evaluate("""([id,v])=>sessionStorage.setItem('code-workspace:v1:'+user.id+':turn',JSON.stringify({namespace:'production',threadId:id,version:v,text:'오래된 요청',startedAt:Date.now()-600000}))""",[thread_id,version])
    ui=open_host()
    expect(ui.locator('#messages')).not_to_contain_text('오래된 요청')
    expect(ui.locator('.bubble.is-pending')).to_have_count(0)
    checked('expired_in_flight_turn_discarded')

    # --- tab + last comparison survive the remount
    ui.get_by_role('tab',name='문구 비교',exact=True).click()
    ui.locator('#compare-message').fill('30초 이내에 인증해주세요.')
    ui.locator('#compare-form').get_by_role('button',name='문구 비교',exact=True).click()
    expect(ui.locator('#compare-results')).to_contain_text('조건 방향이 다릅니다.')
    ui=open_host()
    expect(ui.get_by_role('tab',name='문구 비교',exact=True)).to_have_attribute('aria-selected','true')
    expect(ui.locator('#compare-message')).to_have_value('30초 이내에 인증해주세요.')
    expect(ui.locator('#compare-results')).to_contain_text('조건 방향이 다릅니다.')
    checked('remount_restores_tab_and_comparison')

    # --- "?" help: headings keep their own name; hover peeks, click pins, Escape closes
    expect(ui.get_by_role('heading',name='문구 비교',exact=True)).to_have_count(1)
    help_=ui.locator('#compare .help');pop=help_.locator('.help-pop')
    ui.locator('#compare .title-row h2').hover();expect(pop).to_be_visible()
    ui.locator('#compare-message').hover();expect(pop).to_be_hidden()
    help_.locator('summary').click();expect(pop).to_be_visible()
    ui.locator('#compare-results').hover();expect(pop).to_be_visible()  # pinned: moving away keeps it
    page.keyboard.press('Escape');expect(pop).to_be_hidden()
    checked('help_popover_hover_click_escape')

    # --- long thread titles show in full on hover
    created=api.post('/threads',params={'namespace':'production'}).json()
    r=api.post(f"/threads/{created['id']}/turn",params={'namespace':'production'},json={'request_id':str(uuid.uuid4()),'expected_version':0,'text':LONG_TITLE,'action':'search'})
    assert r.status_code==200,r.text
    ui.get_by_role('tab',name='대화로 찾기',exact=True).click()
    ui=open_host()
    target=ui.locator(f'#threads button[data-id="{created["id"]}"]');target.hover()
    expect(ui.locator('.tip')).to_be_visible();expect(ui.locator('.tip')).to_have_text(LONG_TITLE[:70])
    ui.locator('#question').hover();expect(ui.locator('.tip')).to_be_hidden()
    checked('thread_title_tooltip_on_hover')

    # --- apple.com-style motion: gliding tab indicator, reveal, headline, tilt; all optional
    ui.get_by_role('tab',name='전체 코드',exact=True).click();page.wait_for_timeout(700)
    gap=frame().evaluate("(()=>{const b=document.querySelector('.tabs-indicator'),t=document.querySelector('#tab-catalog');return Math.abs(new DOMMatrix(getComputedStyle(b).transform).m41-t.offsetLeft)+Math.abs(b.offsetWidth-t.offsetWidth)})()")
    assert gap<=1,('indicator not under the selected tab',gap)
    page.wait_for_timeout(1500)
    hidden=frame().evaluate("[...document.querySelectorAll('#main .reveal')].filter(e=>e.getClientRects().length&&getComputedStyle(e).opacity==='0').length")
    assert hidden==0,('revealed tiles left invisible',hidden)
    ui.get_by_role('tab',name='대화로 찾기',exact=True).click()
    # A new tab starts with empty session memory, so the welcome hero is shown.
    fresh=browser.new_page(viewport={'width':1320,'height':900});fresh.on('pageerror',lambda e:errors.append(str(e)))
    fresh.goto(base+'/test-host',wait_until='networkidle');fui=fresh.frame_locator('#workspace');expect(fui.locator('#app')).to_be_visible()
    expect(fui.get_by_role('heading',name='어떤 알림을 찾고 계신가요?',exact=True)).to_have_count(1)
    fresh.wait_for_timeout(1200)
    box=fui.locator('.example').first.bounding_box()
    fresh.mouse.move(box['x']+box['width']*.5,box['y']+box['height']*.5);fresh.wait_for_timeout(100)
    fresh.mouse.move(box['x']+box['width']*.9,box['y']+box['height']*.1)
    assert fresh.frames[1].evaluate("document.querySelector('.example').style.getPropertyValue('--ry')")!='','tile did not follow the pointer'
    fresh.close()
    checked('apple_style_indicator_reveal_headline_tilt')
    calm=browser.new_page(viewport={'width':1320,'height':900},reduced_motion='reduce')
    calm.goto(base+'/test-host',wait_until='networkidle');expect(calm.frame_locator('#workspace').locator('#app')).to_be_visible()
    assert calm.frames[1].evaluate("document.querySelectorAll('.reveal,.word').length")==0,'motion ran under reduced motion'
    calm.close();checked('reduced_motion_disables_decorative_motion')

    # --- phone width: an open popover never widens or clips the page
    # Enough threads that the horizontal strip is far wider than the phone (live lists hold up to 100).
    for _ in range(12):api.post('/threads',params={'namespace':'production'}).raise_for_status()
    page.set_viewport_size({'width':390,'height':844});ui=open_host();page.wait_for_timeout(300)
    ui.locator('.brand .help summary').click()
    box=ui.locator('.brand .help-pop').bounding_box();assert box and box['x']>=0 and box['x']+box['width']<=390,box
    assert not frame().evaluate('document.documentElement.scrollWidth > window.innerWidth'),'horizontal overflow with popover open'
    # #chat clips overflow, so also check the composer itself stays on screen (thread strip must scroll).
    for sel in ('.conversation','.compose'):
     right=frame().evaluate(f"document.querySelector('{sel}').getBoundingClientRect().right")
     assert right<=390,(sel,right)
    page.screenshot(path=str(out/'session-mobile-help.png'))
    checked('mobile_popover_inside_viewport')

    assert not errors,errors;checked('no_browser_javascript_errors');report['passed']=True
    browser.close()
   api.close();store.engine.dispose()
 except Exception as exc:
  report['error']=type(exc).__name__+': '+str(exc);report['traceback']=traceback.format_exc();raise
 finally:
  if server:server.should_exit=True
  if thread:thread.join(timeout=3)
  (out/'browser-session-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
  print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
