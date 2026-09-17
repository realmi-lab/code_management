"""Regression checks for stale UI responses using isolated HTTP + Chrome CDP.

Only this process's temporary DB/server and newly-created browser context are used.
Routes pause requests to reproduce races; all API responses come from FastAPI.
No offline harness, production rows, external models or existing tabs are used.
"""
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
KEY = 'bugfix-browser-test-only'
SERVER = '''
import os
from pathlib import Path
import uvicorn
from catalog.config import Settings
from catalog.main import create_app
app = create_app(Settings(data_dir=Path(os.environ['CM_QA_DATA']), access_token='bugfix-browser-test-only'))
uvicorn.run(app, host='127.0.0.1', port=int(os.environ['CM_QA_PORT']), access_log=False, log_level='error')
'''
REPORT = {'synthetic_data': True, 'mock_model': False, 'model_called': False,
          'offline_harness': False, 'checks': []}


class HeldRequest:
    """Pause a real HTTP request until the browser has changed screens."""
    def __init__(self, page, pattern, method='GET'):
        self.page, self.pattern, self.method = page, pattern, method
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.completed = asyncio.Event()
        self.count = 0

    async def handler(self, route):
        if route.request.method != self.method:
            return await route.continue_()
        self.count += 1
        self.started.set()
        await self.release.wait()
        await route.continue_()
        self.completed.set()

    async def __aenter__(self):
        await self.page.route(self.pattern, self.handler)
        return self

    async def unblock(self):
        self.release.set()
        await asyncio.wait_for(self.completed.wait(), 10)
        await self.page.wait_for_load_state('networkidle')

    async def __aexit__(self, *_):
        self.release.set()
        await self.page.unroute(self.pattern, self.handler)


async def verify(base, api):
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp('http://127.0.0.1:9223')
        context = await browser.new_context(viewport={'width': 1360, 'height': 900})
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        async def navigate(view):
            await page.locator(f'.nav-item[data-view="{view}"]').click()
            await expect(page.locator('#content .loading')).to_have_count(0)

        async def switch(namespace):
            if await page.evaluate('state.namespace') != namespace:
                await page.locator('#namespace-button').click()
            await expect(page.locator('#content .loading')).to_have_count(0)

        def passed(name):
            REPORT['checks'].append(name)

        try:
            await page.goto(base, wait_until='domcontentloaded')
            await page.locator('#auth-token').fill(KEY)
            await page.locator('#auth-form button[type=submit]').click()
            await expect(page.locator('#auth-dialog')).not_to_be_visible()
            await expect(page.locator('#query')).to_be_visible()
            passed('authenticated_actual_http')

            # A slow demo metadata read may not overwrite a later live response.
            async with HeldRequest(page, '**/api/meta?namespace=demo') as request:
                await page.locator('#namespace-button').click()
                await asyncio.wait_for(request.started.wait(), 5)
                await page.locator('#namespace-button').click()
                await expect(page.locator('#query')).to_be_visible()
                await request.unblock()
            assert await page.evaluate('state.namespace') == 'live'
            assert await page.evaluate('state.meta.counts.total') == 1
            await expect(page.locator('#namespace-button')).to_contain_text('실제 목록')
            passed('stale_namespace_metadata_discarded')

            # Repeated submit events (including keyboard/programmatic submission)
            # while AI/save is pending must make only one POST and one draft.
            await navigate('new')
            await page.locator('#draft-message').fill('중복 제출 회귀 검사')
            async with HeldRequest(page, '**/api/drafts', 'POST') as request:
                await page.locator('#draft-form button[type=submit]').click()
                await asyncio.wait_for(request.started.wait(), 5)
                await page.locator('#draft-form').evaluate('(form) => {form.requestSubmit(); form.requestSubmit();}')
                await page.wait_for_timeout(100)
                assert request.count == 1, request.count
                await request.unblock()
            await expect(page.locator('#draft-notice')).to_contain_text('초안이 저장되었습니다.')
            assert len(api.get('/api/drafts').json()['items']) == 1
            passed('pending_form_blocks_duplicate_writes')

            # A saved old draft must not inject results into a fresh draft screen.
            await navigate('new')
            await page.locator('#draft-message').fill('이전 화면에서 저장한 초안')
            async with HeldRequest(page, '**/api/drafts', 'POST') as request:
                await page.locator('#draft-form button[type=submit]').click()
                await asyncio.wait_for(request.started.wait(), 5)
                await navigate('catalog')
                await navigate('new')
                await page.locator('#draft-message').fill('지금 작성 중인 내용')
                await request.unblock()
            await expect(page.locator('#draft-message')).to_have_value('지금 작성 중인 내용')
            await expect(page.locator('#draft-notice')).to_be_empty()
            assert len(api.get('/api/drafts').json()['items']) == 2
            passed('saved_draft_response_does_not_overwrite_new_screen')

            # Changing the chosen file invalidates both a shown preview and an
            # in-flight preview. A stale import ID cannot remain committable.
            await navigate('import')
            file_a = {'name': 'first.csv', 'mimeType': 'text/csv',
                      'buffer': '코드번호,등록문구\nAT-8200,첫 파일 문구\n'.encode()}
            file_b = {'name': 'second.csv', 'mimeType': 'text/csv',
                      'buffer': '코드번호,등록문구\nAT-8300,두 번째 파일 문구\n'.encode()}
            await page.locator('#upload-file').set_input_files(file_a)
            await page.locator('#import-form button[type=submit]').click()
            await expect(page.locator('[data-action="commit-import"]')).to_be_enabled()
            await page.locator('#upload-file').set_input_files(file_b)
            await expect(page.locator('[data-action="commit-import"]')).to_have_count(0)
            assert await page.evaluate('state.preview') is None
            await page.locator('#upload-file').set_input_files(file_a)
            async with HeldRequest(page, '**/api/imports/preview', 'POST') as request:
                await page.locator('#import-form button[type=submit]').click()
                await asyncio.wait_for(request.started.wait(), 5)
                await page.locator('#upload-file').set_input_files(file_b)
                await request.unblock()
            await expect(page.locator('#import-preview')).to_be_empty()
            await page.locator('#import-form button[type=submit]').click()
            await expect(page.locator('#import-preview')).to_contain_text('AT-8300')
            await page.locator('[data-action="commit-import"]').click()
            await expect(page.locator('#content')).to_contain_text('AT-8300')
            assert api.get('/api/codes/AT-8200').status_code == 404
            passed('file_change_invalidates_shown_and_pending_preview')

            await navigate('import')
            await page.locator('#upload-file').set_input_files(file_a)
            async with HeldRequest(page, '**/api/imports/preview', 'POST') as request:
                await page.locator('#import-form button[type=submit]').click()
                await asyncio.wait_for(request.started.wait(), 5)
                await switch('demo')
                await request.unblock()
            assert await page.evaluate('state.preview') is None
            await expect(page.locator('[data-action="commit-import"]')).to_have_count(0)
            passed('preview_cannot_cross_namespace')
            await switch('live')

            # Existing identical rows are still a valid confirmation/import.
            await page.locator('#upload-file').set_input_files(file_b)
            await page.locator('#import-form button[type=submit]').click()
            await expect(page.locator('[data-action="commit-import"]')).to_have_text('기존 목록 확인 완료')
            await expect(page.locator('[data-action="commit-import"]')).to_be_enabled()
            await page.locator('[data-action="commit-import"]').click()
            await expect(page.locator('#content')).to_contain_text('AT-8300')
            passed('unchanged_import_can_be_confirmed')

            # Delayed dialogs must not reopen after navigating or closing them.
            async with HeldRequest(page, '**/api/codes/AT-8100?namespace=live') as request:
                await page.locator('[data-action="detail"][data-code="AT-8100"]').click()
                await asyncio.wait_for(request.started.wait(), 5)
                await navigate('new')
                await request.unblock()
            await expect(page.locator('#detail-dialog')).not_to_be_visible()
            passed('stale_detail_does_not_reopen_after_navigation')

            await navigate('catalog')
            await page.locator('[data-action="detail"][data-code="AT-8100"]').click()
            await expect(page.locator('#detail-dialog')).to_be_visible()
            async with HeldRequest(page, '**/api/codes/AT-8100?namespace=live') as request:
                await page.locator('[data-action="revision"]').click()
                await asyncio.wait_for(request.started.wait(), 5)
                await page.locator('[data-action="close-dialog"]').click()
                await request.unblock()
            assert await page.evaluate('state.view') == 'catalog'
            await expect(page.locator('#detail-dialog')).not_to_be_visible()
            passed('closed_dialog_cannot_trigger_late_navigation')

            # Lock must remove private data, invalidate pending reads and stay
            # modal even when Escape is pressed.
            async with HeldRequest(page, '**/api/codes/AT-8100?namespace=live') as request:
                await page.locator('[data-action="detail"][data-code="AT-8100"]').click()
                await asyncio.wait_for(request.started.wait(), 5)
                await page.locator('[data-action="lock"]').click()
                await page.keyboard.press('Escape')
                await request.unblock()
            await expect(page.locator('#auth-dialog')).to_be_visible()
            await expect(page.locator('#detail-dialog')).not_to_be_visible()
            assert '비공개 회귀 검사 문구' not in await page.locator('body').inner_text()
            assert await page.evaluate('state.meta') is None
            passed('lock_clears_private_content_and_pending_reads')
            assert not errors, errors
            passed('no_javascript_page_errors')
        finally:
            await context.close()


def main():
    with tempfile.TemporaryDirectory(prefix='cm-bugfix-browser-') as directory:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {k: v for k, v in os.environ.items()
               if not k.startswith('AI_') and k not in {'ACCESS_TOKEN', 'DATA_DIR'}}
        env.update(CM_QA_DATA=directory, CM_QA_PORT=str(port))
        process = subprocess.Popen([sys.executable, '-c', SERVER], cwd=ROOT, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        try:
            with httpx.Client(base_url=base, headers={'Authorization': 'Bearer ' + KEY},
                              trust_env=False, timeout=10) as api:
                for _ in range(70):
                    try:
                        if api.get('/api/health').status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError('Isolated QA server failed to start')
                rows = '코드번호,등록문구\nAT-8100,비공개 회귀 검사 문구\n'.encode()
                preview = api.post('/api/imports/preview', files={'file': ('seed.csv', rows)}).json()
                result = api.post(f"/api/imports/{preview['import_id']}/commit",
                                  json={'expected_catalog_version': preview['catalog_version']})
                result.raise_for_status()
                asyncio.run(verify(base, api))
                REPORT['success'] = True
        except Exception as exc:
            REPORT.update(success=False, error=str(exc)[:1600])
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            print(json.dumps(REPORT, ensure_ascii=False))


if __name__ == '__main__':
    main()
