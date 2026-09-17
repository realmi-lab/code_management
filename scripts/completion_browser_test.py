"""Isolated HTTP/browser workflow check using the existing Chrome CDP endpoint.
Synthetic catalog and mocked model only. Never writes to the operational DB.
"""
import json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
KEY='workflow-test-only'
SERVER_CODE="""
import json,os
from pathlib import Path
import uvicorn
from catalog.main import create_app
from catalog.config import Settings
app=create_app(Settings(data_dir=Path(os.environ['DATA_DIR']),access_token='workflow-test-only',ai_enabled=True,ai_chat_model='mock-search'))
async def response(endpoint,payload):
    return {'choices':[{'message':{'content':json.dumps({'queries':['휴대폰 번호 중복 가입']})}}]}
app.state.ai.request=response
uvicorn.run(app,host='127.0.0.1',port=int(os.environ['CM_QA_PORT']),access_log=False,log_level='error')
"""
report={'synthetic_data':True,'mock_model':True,'offline_harness':False,'checks':[]}
def passed(name): report['checks'].append(name)
with tempfile.TemporaryDirectory(prefix='cm-workflow-qa-') as directory:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    env={**os.environ,'DATA_DIR':directory,'CM_QA_PORT':str(port)}
    for k in list(env):
        if k.startswith('AI_') or k=='ACCESS_TOKEN':env.pop(k)
    process=subprocess.Popen([sys.executable,'-c',SERVER_CODE],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base=f'http://127.0.0.1:{port}'
    try:
        with httpx.Client(base_url=base,headers={'Authorization':'Bearer '+KEY},trust_env=False,timeout=10) as api:
            for _ in range(50):
                try:
                    if api.get('/api/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.1)
            with sync_playwright() as pw:
                browser=pw.chromium.connect_over_cdp('http://127.0.0.1:9223')
                context=browser.new_context(viewport={'width':1360,'height':900})
                page=context.new_page()
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                try:
                    page.goto(base,wait_until='domcontentloaded')
                    page.locator('#auth-token').fill(KEY)
                    page.locator('#auth-form button[type=submit]').click()
                    expect(page.locator('#auth-dialog')).not_to_be_visible()
                    passed('authenticated_http_ui')
                    page.locator('.nav-item[data-view="new"]').click()
                    page.locator('#draft-message').fill('처음 저장한 문구')
                    page.locator('#draft-form [name=menu]').fill('가입')
                    page.locator('#draft-form [name=trigger]').fill('중복 번호')
                    page.locator('#draft-form button[type=submit]').click()
                    expect(page.locator('#draft-notice')).to_contain_text('초안이 저장되었습니다.')
                    page.locator('.nav-item[data-view="drafts"]').click()
                    page.locator('[data-action="review-draft"]').first.click()
                    page.locator('[data-action="edit-draft"]').click()
                    page.locator('#draft-message').fill('이미 가입된 전화번호입니다.')
                    page.locator('[name=edit_reason]').fill('기획 검토 반영')
                    page.locator('#draft-form button[type=submit]').click()
                    expect(page.locator('.draft-card')).to_contain_text('이미 가입된 전화번호입니다.')
                    passed('draft_create_edit')
                    page.locator('[data-action="review-draft"]').first.click()
                    page.locator('[data-action="handoff"]').click()
                    expect(page.locator('.draft-card')).to_contain_text('엑셀 등록 요청')
                    rows='코드번호,등록문구,사용메뉴,노출조건\nAT-8000,이미 가입된 전화번호입니다.,가입,중복 번호\n'
                    preview=api.post('/api/imports/preview',files={'file':('synthetic.csv',rows.encode())}).json()
                    r=api.post('/api/imports/'+preview['import_id']+'/commit',json={'expected_catalog_version':preview['catalog_version']})
                    assert r.status_code==200,r.text
                    page.locator('[data-action="review-draft"]').first.click()
                    page.locator('[data-action="external-matches"]').click()
                    expect(page.locator('#detail-dialog')).to_contain_text('문구·메뉴·조건 일치')
                    page.locator('[data-action="pick-external"]').click()
                    page.locator('#external-link-form [name=reason]').fill('확정 엑셀과 대조 완료')
                    page.locator('#external-link-form button[type=submit]').click()
                    expect(page.locator('.draft-card')).to_contain_text('정식 등록')
                    assert api.get('/api/drafts').json()['items'][0]['registered_code']=='AT-8000'
                    passed('excel_handoff_import_review_link')
                    page.locator('.nav-item[data-view="search"]').click()
                    expect(page.locator('[name=use_ai]')).to_be_checked()
                    page.locator('#query').fill('전에 쓰던 번호로 또 가입하려는 사람')
                    page.locator('#search-form button[type=submit]').click()
                    expect(page.locator('#results')).to_contain_text('AI 검색어 보완')
                    expect(page.locator('#results')).to_contain_text('AT-8000')
                    passed('ai_search_expansion_and_original_result')
                    page.locator('[name=use_ai]').uncheck()
                    page.locator('#query').fill('전화번호')
                    page.locator('#search-form button[type=submit]').click()
                    expect(page.locator('#results')).to_contain_text('기본 검색')
                    passed('basic_search_opt_out')
                    context2=browser.new_context(viewport={'width':390,'height':844})
                    mobile=context2.new_page()
                    try:
                        mobile.goto(base,wait_until='domcontentloaded')
                        mobile.locator('#auth-token').fill(KEY)
                        mobile.locator('#auth-form button[type=submit]').click()
                        expect(mobile.locator('#auth-dialog')).not_to_be_visible()
                        assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                        passed('mobile_no_horizontal_overflow')
                    finally:context2.close()
                    assert not errors,errors
                    passed('no_browser_javascript_errors')
                finally:context.close()
        report['success']=True
    except Exception as exc:
        report['success']=False;report['error']=str(exc)[:1800]
        raise
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        (ROOT/'docs/completion-browser-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False))
