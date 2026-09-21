"""Live original Next/JWT settings check; never loads sample company/catalog data."""
import json,os,sys
from pathlib import Path
from manage import ROOT,load_env
from playwright.sync_api import sync_playwright,expect


def main():
 values=load_env(ROOT/'.env');out=ROOT/'docs/verification/completion-2026-09-21';out.mkdir(parents=True,exist_ok=True)
 base='http://127.0.0.1:'+values.get('WEB_PORT','3500')
 report={'passed':False,'original_next':True,'original_JWT':values.get('CODE_AUTH_MODE')!='local','local_access':values.get('CODE_AUTH_MODE')=='local','synthetic_catalog_inserted':False,'checks':[]}
 errors=[]
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),headless=True)
   page=browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
   if values.get('CODE_AUTH_MODE')=='local':
    mode=page.request.get(base+'/api/auth/mode').json();assert mode['mode']=='local'
    report['checks'].append('headerless_local_mode')
   else:
    page.goto(base+'/login',wait_until='networkidle');page.locator('#username').fill(values['ADMIN_USERNAME']);page.locator('#password').fill(values['ADMIN_PASSWORD'])
    with page.expect_response(lambda r:r.url.endswith('/api/auth/login')) as login_response:
     page.get_by_role('button',name='로그인',exact=True).click()
    report['login_http_status']=login_response.value.status
    sent=login_response.value.request.post_data_json
    report['credentials_match']={'username':sent.get('username')==values['ADMIN_USERNAME'],'password':sent.get('password')==values['ADMIN_PASSWORD']}
    if login_response.value.status!=200:
     report['login_error']=login_response.value.json().get('detail');raise RuntimeError('Original browser login failed')
    page.wait_for_url(base+'/',timeout=20000)
    report['checks'].append('original_admin_login')
   page.goto(base+'/codes');ui=page.frame_locator('iframe[title="알림 코드 대화 작업실"]')
   expect(ui.locator('#app')).to_be_visible(timeout=15000)
   ui.locator('[data-view=ai-settings]').click();expect(ui.locator('#ai-model')).not_to_have_value('')
   expect(ui.locator('#ai-key')).to_have_value('')
   report['checks'].append('real_backend_AI_settings_read')
   original_mode=ui.locator('#ai-embedding').input_value()
   # Keep the selected provider and its existing key; write only the mode then restore.
   try:
    ui.locator('#ai-embedding').select_option('none');ui.locator('#ai-save').click()
    expect(ui.locator('#ai-settings-result')).to_contain_text('다음 요청',timeout=15000)
    expect(ui.locator('#index-state')).to_contain_text('키워드 검색')
    page.reload();expect(ui.locator('#app')).to_be_visible(timeout=15000);ui.locator('[data-view=ai-settings]').click()
    expect(ui.locator('#ai-save')).to_be_enabled()
    expect(ui.locator('#ai-embedding')).to_have_value('none')
    expect(ui.locator('#ai-key')).to_have_value('')
    report['checks'].append('admin_keyword_mode_saved_and_reloaded')
   finally:
    ui.locator('#ai-embedding').select_option(original_mode);ui.locator('#ai-save').click()
    expect(ui.locator('#ai-settings-result')).to_contain_text('다음 요청',timeout=15000)
   page.screenshot(path=str(out/'live-ai-settings-desktop.png'),full_page=True)
   assert not any(c['name']=='refresh_token' for c in page.context.cookies()) if values.get('CODE_AUTH_MODE')=='local' else True
   report['checks'].append('original_search_mode_restored')
   assert not errors,errors
   browser.close()
  report['passed']=True
 finally:(out/'live-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
