"""Real browser + HTTP settings UI; isolated SQLite/auth doubles, no paid inference."""
import json,os,socket,sys,tempfile,threading,time
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'extensions'),str(ROOT/'integration_tests')]
from browser_check import HOST,SCRIPT
from code_agent.store import Store
from test_api import app_for
from fastapi.responses import HTMLResponse,Response
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright,expect
import uvicorn


def main():
 out=Path(os.getenv('VERIFICATION_DIR',str(ROOT/'docs/verification')));out.mkdir(parents=True,exist_ok=True)
 report={'passed':False,'authentication':'test dependency, NOT upstream JWT','external_AI_calls':False,'local_model_health':'explicit synthetic health double, NOT live service','checks':[]}
 server=None;previous={key:os.environ.get(key) for key in ('CODE_AI_SETTINGS_FILE','LOCAL_EMBEDDING_URL')}
 try:
  local_health={'local_configured':True,'local_available':False,'local_state':'unavailable'}
  with tempfile.TemporaryDirectory() as tmp,patch('code_agent.ai_config.local_status',side_effect=lambda:dict(local_health)):
   os.environ['CODE_AI_SETTINGS_FILE']=tmp+'/ai.json';os.environ['LOCAL_EMBEDDING_URL']='http://local-embeddings:8080'
   store=Store('sqlite:///'+tmp+'/test.db');store.initialize();app=app_for(store)
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
    browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),headless=True)
    page=browser.new_page(viewport={'width':1280,'height':1050});page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{port}/test-host',wait_until='networkidle');ui=page.frame_locator('#workspace')
    ui.locator('[data-view=ai-settings]').click()
    expect(ui.locator('#ai-embedding option[value="local"]')).to_be_disabled()
    expect(ui.locator('#ai-local-status')).to_contain_text('준비 중')
    report['checks'].append('unavailable_local_embedding_explicit_and_disabled')
    for provider in ('deepseek','anthropic','openai'):
     ui.locator('#ai-provider').select_option(provider)
     ui.locator('#ai-key').fill('synthetic-browser-'+provider)
     ui.locator('#ai-embedding').select_option('none')
     ui.locator('#ai-save').click()
     expect(ui.locator('#ai-key-status')).to_contain_text('설정되어')
     expect(ui.locator('#ai-key')).to_have_value('')
     page.reload(wait_until='networkidle');ui.locator('[data-view=ai-settings]').click()
     expect(ui.locator('#ai-provider')).to_have_value(provider)
     expect(ui.locator('#ai-embedding')).to_have_value('none')
     expect(ui.locator('#index-state')).to_contain_text('키워드 검색')
     report['checks'].append(provider+'_saved_and_reloaded')
    local_health.update(local_available=True,local_state='ready')
    page.reload(wait_until='networkidle');ui.locator('[data-view=ai-settings]').click()
    expect(ui.locator('#ai-local-status')).to_contain_text('준비되어')
    ui.locator('#ai-provider').select_option('anthropic');ui.locator('#ai-embedding').select_option('local');ui.locator('#ai-save').click()
    expect(ui.locator('#ai-settings-result')).to_contain_text('다음 요청')
    expect(ui.locator('#ai-key')).to_have_value('')
    report['checks'].append('claude_with_local_embedding_without_openai_dependency')
    ui.locator('#ai-embedding').select_option('openai')
    expect(ui.locator('#ai-embedding-key-field')).to_be_visible()
    ui.locator('#ai-embedding-key').fill('synthetic-separate-embedding')
    ui.locator('#ai-save').click()
    expect(ui.locator('#ai-embedding-key')).to_have_value('')
    expect(ui.locator('#ai-embedding-key-status')).to_contain_text('설정되어')
    page.reload(wait_until='networkidle');ui.locator('[data-view=ai-settings]').click()
    expect(ui.locator('#ai-provider')).to_have_value('anthropic')
    expect(ui.locator('#ai-embedding')).to_have_value('openai')
    expect(ui.locator('#ai-embedding-key')).to_have_value('')
    report['checks'].append('claude_with_separate_openai_embedding_key_and_no_browser_key_retention')
    page.screenshot(path=str(out/'ai-settings-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(300)
    assert ui.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(out/'ai-settings-mobile.png'),full_page=True)
    report['checks'].append('mobile_no_horizontal_overflow')
    assert not errors,errors
    browser.close()
   report['passed']=True
 finally:
  if server:server.should_exit=True;thread.join(timeout=5)
  for key,value in previous.items():
   if value is None:os.environ.pop(key,None)
   else:os.environ[key]=value
  (out/'browser-ai-settings.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
