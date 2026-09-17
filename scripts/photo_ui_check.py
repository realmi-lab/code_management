"""Read-only UI checks against the isolated, photograph-derived test catalogue.

Uses actual HTTP and a new Chrome CDP context. Does not invoke a model, write any
catalogue rows, or change existing browser tabs. Never prints the access token.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run import load_env

REPORT = {
    "user_photo_transcription": True, "synthetic_data": False,
    "model_called": False, "offline_harness": False,
    "catalogue_mutations": False, "checks": [],
}


async def verify():
    load_env(ROOT / '.env')
    token = os.getenv('CM_PHOTO_TEST_TOKEN') or os.environ['ACCESS_TOKEN']
    base = os.getenv('CM_PHOTO_TEST_URL', 'http://localhost:2999/code-management/')
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp('http://127.0.0.1:9223')
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        errors, api_requests = [], []
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: api_requests.append(request.url)
                if '/api/' in request.url else None)

        async def navigate(view):
            await page.locator(f'.nav-item[data-view="{view}"]').click()
            await expect(page.locator('#content .loading')).to_have_count(0)

        def passed(name):
            REPORT['checks'].append(name)

        try:
            await page.goto(base, wait_until='domcontentloaded')
            if token:
                await page.locator('#auth-token').fill(token)
                await page.locator('#auth-form button[type=submit]').click()
                await expect(page.locator('#auth-dialog')).not_to_be_visible()
            else:
                await expect(page.locator('#auth-dialog')).not_to_be_visible()
            await expect(page.locator('#query')).to_be_visible()
            assert await page.evaluate('state.meta.counts.total') == 33
            await expect(page.locator('#namespace-button')).to_contain_text('사진 테스트 목록')
            await expect(page.locator('#catalog-banner')).to_be_visible()
            passed('authenticated_33_photo_rows_through_proxy')

            await expect(page.locator('[data-query="S-C-2"]')).to_be_visible()
            await page.locator('[data-query="S-C-2"]').click()
            await expect(page.locator('#results .code-card')).to_have_count(1)
            card = page.locator('#results .code-card')
            await expect(card.locator('.code-id')).to_have_text('S-C-2')
            await expect(card.locator('.card-fields')).to_contain_text('알럿')
            await expect(card.locator('.card-title')).to_contain_text('예치최종실행')
            await expect(card.locator('.source-review')).to_be_visible()
            await expect(card.locator('.card-message')).to_contain_text('[닫기] [신청하기]')
            await expect(card.locator('.message-button')).to_have_count(0)
            passed('exact_code_preserves_source_type_title_and_review_note')

            await card.locator('[data-action="detail"]').click()
            await expect(page.locator('#detail-dialog')).to_be_visible()
            await expect(page.locator('#detail-content')).to_contain_text('영문타이틀')
            await expect(page.locator('#detail-content')).to_contain_text('영문컨텐츠')
            await expect(page.locator('#detail-content')).to_contain_text('7360.jpg')
            await expect(page.locator('#detail-content .details-grid')).to_contain_text('알럿')
            await expect(page.locator('#detail-content .dialog-message')).to_contain_text('[닫기] [신청하기]')
            await expect(page.locator('#detail-content .message-button')).to_have_count(0)
            await page.locator('[data-action="close-dialog"]').click()
            passed('detail_keeps_all_worksheet_fields_and_photo_source')

            await page.locator('#query').fill('S-C-5')
            await page.locator('#search-form button[type=submit]').click()
            await expect(page.locator('#results .code-id')).to_have_text('S-C-5')
            text = await page.locator('#results .card-message').inner_text()
            assert '\n' in text and '[닫기][로그인]' in text
            await expect(page.locator('#results .message-button')).to_have_count(0)
            original = await page.evaluate("api('/api/codes/S-C-5?namespace=live')")
            copied = await page.evaluate("api('/api/codes/S-C-5/copy?namespace=live')")
            assert original['message'].endswith('[닫기][로그인]')
            assert text == original['message']
            assert original['message'] in copied['text']
            await page.locator('#results [data-action="detail"]').click()
            await page.locator('#detail-content [data-action="revision"]').click()
            await expect(page.locator('#draft-message')).to_have_value(original['message'])
            await navigate('search')
            passed('multiline_raw_message_copy_and_edit_preserved')

            for code, labels, variable in [
                ('S-A-1', ['나가기'], ''),
                ('S-A-19', ['확인'], ''),
                ('S-C-6', ['취소', '계좌연결'], ''),
                ('S-A-24', ['확인'], '$심볼명$'),
                ('S-A-22', ['확인'], '{서비스 차단 시 선택한 비고항목의 텍스트 노출}'),
            ]:
                await page.locator('#query').fill(code)
                await page.locator('#search-form button[type=submit]').click()
                await expect(page.locator('#results .code-id')).to_have_text(code)
                raw_message = await page.locator('#results .card-message').inner_text()
                positions = [raw_message.index(f'[{label}]') for label in labels]
                assert positions == sorted(positions)
                await expect(page.locator('#results .message-button')).to_have_count(0)
                if variable:
                    await expect(page.locator('#results .card-message')).to_contain_text(variable)
            passed('bracket_labels_order_and_variables_preserved_in_body')

            await page.locator('#query').fill('네트워크 오류')
            ai_toggle = page.locator('input[name="use_ai"]')
            if await ai_toggle.count():
                await ai_toggle.uncheck()
            await page.locator('#search-form button[type=submit]').click()
            await expect(page.locator('#results .result-header small')).to_have_text('기본 검색')
            assert await page.locator('#results .code-card').count() > 0
            await expect(page.locator('#results .code-id').first).to_have_text('S-A-19')
            passed('basic_situation_search_returns_photo_catalogue')

            await navigate('catalog')
            await expect(page.locator('thead')).to_contain_text('업무구분 · 타입')
            await expect(page.locator('thead')).to_contain_text('타이틀 · 컨텐츠')
            await page.locator('#catalog-form input[name="q"]').fill('S-T-1')
            await page.locator('#catalog-form button[type=submit]').click()
            await expect(page.locator('tbody tr')).to_have_count(1)
            await expect(page.locator('tbody')).to_contain_text('보유자산 부족')
            await expect(page.locator('tbody')).to_contain_text('토스트')
            await expect(page.locator('tbody .message-button')).to_have_count(0)
            await page.locator('#catalog-form input[name="q"]').fill('S-C-6')
            await page.locator('#catalog-form button[type=submit]').click()
            await expect(page.locator('tbody .code-id')).to_have_text('S-C-6')
            await expect(page.locator('tbody .message-cell')).to_contain_text('[취소][계좌연결]')
            await expect(page.locator('tbody .message-button')).to_have_count(0)
            passed('catalogue_columns_and_literal_bracket_labels')

            await page.locator('#namespace-button').click()
            await expect(page.locator('#namespace-button')).to_contain_text('예시 목록')
            await expect(page.locator('#catalog-banner')).not_to_be_visible()
            await page.locator('#namespace-button').click()
            await expect(page.locator('#namespace-button')).to_contain_text('사진 테스트 목록')
            await expect(page.locator('#catalog-banner')).to_be_visible()
            passed('photo_notice_and_demo_scope_are_separate')

            await navigate('search')
            await page.set_viewport_size({"width": 390, "height": 844})
            await expect(page.locator('#query')).to_be_visible()
            await page.locator('#query').fill('S-C-5')
            await page.locator('#search-form button[type=submit]').click()
            await expect(page.locator('#results .code-id')).to_have_text('S-C-5')
            await expect(page.locator('#results .card-message')).to_contain_text('[닫기][로그인]')
            await expect(page.locator('#results .message-button')).to_have_count(0)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert await page.locator('#results .card-message').evaluate("el => getComputedStyle(el).fontSize") == '14px'
            (ROOT / '.runtime').mkdir(exist_ok=True)
            await page.screenshot(path=str(ROOT / '.runtime/raw-messages-mobile.png'), full_page=True)
            await page.set_viewport_size({"width": 1440, "height": 1000})
            await page.screenshot(path=str(ROOT / '.runtime/raw-messages-desktop.png'), full_page=True)
            passed('mobile_raw_message_14px_and_no_document_overflow')

            if token:
                await page.locator('[data-action="lock"]').click()
                await expect(page.locator('#auth-dialog')).to_be_visible()
                await expect(page.locator('#catalog-banner')).not_to_be_visible()
                assert await page.evaluate("sessionStorage.getItem(sessionKey('cm_token'))") is None
                passed('locking_clears_scoped_session_and_catalogue_banner')
            else:
                assert 'hidden' in (await page.locator('[data-action="lock"]').get_attribute('class') or '')
                passed('direct_access_hides_general_access_lock')

            expected_prefix = base.rstrip('/') + '/api/'
            assert api_requests and all(url.startswith(expected_prefix) for url in api_requests)
            passed('all_api_requests_use_proxy_prefix')
            assert not errors, errors
            passed('no_browser_javascript_errors')
            REPORT['passed'] = True
            REPORT['javascript_errors'] = 0
        finally:
            await context.close()


if __name__ == '__main__':
    asyncio.run(verify())
    report = ROOT / 'docs/photo-browser-check.json'
    report.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({"passed": REPORT['passed'], "checks": len(REPORT['checks']),
                      "offline_harness": False, "model_called": False,
                      "catalogue_mutations": False}, ensure_ascii=False))
