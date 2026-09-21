"""Chromium UI workflow tests.
Default: HTTP against an already-running LOCAL test instance (CM_TEST_TOKEN/CM_TEST_URL).
CM_BROWSER_OFFLINE=true: direct local assets with in-process API bridge, NOT HTTP E2E.
Creates test records; never point this script at a production instance.
"""
from __future__ import annotations
import json
import os
import time
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parent.parent
URL=os.getenv('CM_TEST_URL','http://127.0.0.1:8766')
TOKEN=os.getenv('CM_TEST_TOKEN','browser-test-only')
REPORT=ROOT/'docs'/'browser-test-results.json'
OFFLINE=os.getenv('CM_BROWSER_OFFLINE','false').lower()=='true'


def run():
    checks=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1080},device_scale_factor=1,permissions=['clipboard-read','clipboard-write'])
        harness=None
        if OFFLINE:
            from scripts.browser_harness import Harness
            harness=Harness(tempfile.mkdtemp(prefix='cm-ui-test-'),TOKEN);harness.install(context)
        page=context.new_page();page.on('pageerror',lambda err:errors.append(str(err)))
        if harness:harness.open(page)
        else:page.goto(URL,wait_until='networkidle')
        expect(page.locator('#auth-dialog')).to_be_visible()
        page.locator('#auth-token').fill(TOKEN)
        page.locator('#auth-form button[type=submit]').click()
        expect(page.locator('#query')).to_be_visible()
        checks.append('접속 키 로그인')
        page.locator('#namespace-button').click()
        expect(page.locator('#demo-banner')).to_be_visible()
        page.locator('#query').fill('AT-1923')
        page.locator('#search-form button[type=submit]').click()
        expect(page.locator('#results .card-message')).to_have_text('메뉴확인 30초 이후에 인증해주세요.')
        checks.append('정확한 코드번호 조회·원문 표시')
        page.locator('#results button[data-action=copy]').click()
        expect(page.locator('#toast')).to_contain_text('기획서에 넣을 내용을 복사했습니다.')
        copied=page.evaluate('navigator.clipboard.readText()')
        assert '메뉴확인 30초 이후에 인증해주세요.' in copied
        assert '실제 회사 코드가 아닌 데모' in copied
        checks.append('기획서용 원문 복사')
        page.locator('#results .code-id').click()
        expect(page.locator('.dialog-message')).to_have_text('메뉴확인 30초 이후에 인증해주세요.')
        page.locator('button[data-action=close-dialog]').click()
        checks.append('코드 상세·근거 조회')
        page.locator('#query').fill('인증 전에 30초 기다리라는 알림')
        page.locator('#search-form button[type=submit]').click()
        expect(page.locator('#results .code-id').first).to_have_text('AT-1923')
        expect(page.locator('#toast')).not_to_be_visible(timeout=6000)
        page.screenshot(path=str(ROOT/'docs'/'desktop-preview.png'),full_page=False)
        checks.append('상황 설명 검색')
        page.locator('#nav button[data-view=compare]').click()
        page.locator('#query').fill('메뉴확인 30초 이내에 인증해주세요.')
        page.locator('#search-form button[type=submit]').click()
        expect(page.locator('#results')).to_contain_text('조건 방향이 다릅니다.')
        checks.append('이후/이내 조건 차이 표시')
        page.locator('#nav button[data-view=new]').click()
        page.locator('#draft-message').fill('선택한 메뉴를 즐겨찾기에 추가했습니다.')
        page.locator('#draft-form input[name=menu]').fill('즐겨찾기')
        page.locator('#draft-form input[name=trigger]').fill('추가 완료')
        page.locator('#draft-form button[type=submit]').click()
        expect(page.locator('#draft-notice')).to_contain_text('정식 코드번호는 아직 없습니다.')
        checks.append('초안 저장·정식 번호 미발급')
        page.locator('#nav button[data-view=drafts]').click()
        page.locator('button[data-action=review-draft]').first.click()
        expect(page.locator('#approve-form')).to_be_visible()
        page.locator('#approve-form select[name=prefix]').select_option('EX')
        page.locator('#approve-form input[name=reason]').fill('브라우저 검증용 합성 예시 승인')
        page.locator('#approve-form input[name=duplicate_ack]').check()
        page.locator('#approve-form button[type=submit]').click()
        expect(page.locator('#detail-dialog')).not_to_be_visible()
        expect(page.locator('#content')).to_contain_text('정식 등록')
        checks.append('데모 초안 검토·번호 발급·등록')
        page.locator('#namespace-button').click()
        expect(page.locator('#demo-banner')).not_to_be_visible()
        page.locator('#nav button[data-view=import]').click()
        code='TST-'+str(int(time.time()))
        payload=('코드번호,등록문구,사용메뉴,노출조건\n'+code+',"<img src=x onerror=alert(1)> 원문",테스트,확인\n').encode('utf-8-sig')
        page.locator('#upload-file').set_input_files({'name':'browser_test.csv','mimeType':'text/csv','buffer':payload})
        page.locator('#import-form button[type=submit]').click()
        expect(page.locator('#import-preview')).to_contain_text(code)
        assert page.locator('#import-preview img').count()==0
        page.locator('button[data-action=commit-import]').click()
        expect(page.locator('#content')).to_contain_text(code)
        assert page.locator('#content img').count()==0
        checks.append('파일 업로드→미리보기→등록·HTML 이스케이프')
        with page.expect_download() as dl:
            page.locator('button[data-action=export-codes]').click()
        assert dl.value.suggested_filename.endswith('.csv')
        checks.append('코드 목록 파일 내보내기')
        # A changed Excel/CSV row requires item-level selection plus a reason.
        page.locator('#nav button[data-view=import]').click()
        updated=('코드번호,등록문구,사용메뉴,노출조건\n'+code+',승인된 새 원문,테스트,개정 확인\n').encode('utf-8-sig')
        page.locator('#upload-file').set_input_files({'name':'browser_update.csv','mimeType':'text/csv','buffer':updated})
        page.locator('#import-form button[type=submit]').click()
        expect(page.locator('.approve-update')).to_be_visible()
        page.locator('.approve-update').check()
        page.locator('#update-reason').fill('개정 원문 확인')
        page.locator('button[data-action=commit-import]').click()
        expect(page.locator('#content')).to_contain_text('승인된 새 원문')
        checks.append('충돌 항목 선택·사유 입력 후 원문 갱신')
        page.locator('#nav button[data-view=review]').click()
        page.locator('#review-form textarea').fill(code+'\nAT-99999999999')
        page.locator('#review-form button[type=submit]').click()
        expect(page.locator('#review-results')).to_contain_text('목록에 없습니다')
        checks.append('기획서 줄별 코드 검토')
        page.locator('#nav button[data-view=import]').click()
        with page.expect_download() as dl:
            page.locator('button[data-action=template]').click()
        assert dl.value.suggested_filename.endswith('.xlsx')
        checks.append('엑셀 양식 다운로드')
        mobile=context.new_page();mobile.set_viewport_size({'width':390,'height':844})
        mobile.on('pageerror',lambda err:errors.append(str(err)))
        if harness:harness.open(mobile,token=TOKEN,namespace='demo')
        else:
            mobile.add_init_script('sessionStorage.setItem("cm_token",'+json.dumps(TOKEN)+');sessionStorage.setItem("cm_namespace","demo");')
            mobile.goto(URL,wait_until='networkidle')
        mobile.locator('#query').fill('AT-1923');mobile.locator('#search-form button[type=submit]').click()
        expect(mobile.locator('#results .card-message')).to_be_visible()
        assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        mobile.screenshot(path=str(ROOT/'docs'/'mobile-preview.png'),full_page=True)
        checks.append('390px 모바일 화면·가로 넘침 없음')
        assert not errors,errors
        report={'passed':len(checks),'checks':checks,'javascript_errors':errors,'real_browser':'Chromium via Playwright','transport':'FastAPI TestClient bridge (offline)' if OFFLINE else 'HTTP',
          'not_tested':['사용자 Docker Local 배포','실제 회사 엑셀','실제 AI 모델 응답 품질']+(['브라우저 직접 HTTP/CSP/클립보드 권한'] if OFFLINE else []),'server':URL if not OFFLINE else 'in-process test instance'}
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
        browser.close()
        if harness:harness.close()

if __name__=='__main__':run()
