"""Built Next UI with synthetic write/evaluation responses; no provider calls.

Reads real local settings, but never changes them or starts background jobs.
This is a browser contract check, not a live AI/embedding quality test.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect


def main():
    out = Path(os.getenv('VERIFICATION_DIR', str(Path(__file__).resolve().parents[1] / 'docs/verification/functional-parity-2026-09-21')))
    out.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        base = 'http://127.0.0.1:3500'
        settings = page.request.get(base + '/api/settings').json()
        assert 'search_mode' in settings and 'multi_query_enabled' in settings
        # Browser fixtures explicitly select unavailable embedding capability.
        settings['embedding_provider'] = 'none'
        settings['search_mode'] = 'vector'
        settings['hyde_enabled'] = settings['multi_query_enabled'] = True
        writes = []
        watcher_requests = []
        run = {'id': 'synthetic-run', 'dataset_id': 'synthetic-dataset', 'dataset_name': '합성 UI 검사',
               'status': 'completed', 'metrics': {'faithfulness': 0, 'context_precision': .5},
               'per_question_results': [], 'created_at': '2026-09-21T00:00:00Z'}

        def api(route):
            req = route.request
            path = urlparse(req.url).path
            if path == '/api/settings':
                if req.method == 'PATCH':
                    writes.append(req.post_data_json)
                    settings.update(req.post_data_json)
                return route.fulfill(json=settings)
            if path == '/api/system/status':
                # Prevent the status widget from probing provider /models APIs.
                return route.fulfill(json={'status': 'ok', 'components': {}})
            if path == '/api/watcher/status':
                return route.fulfill(json={'running': False, 'directories': [], 'use_polling': False})
            if path == '/api/watcher/start':
                watcher_requests.append(parse_qs(urlparse(req.url).query))
                return route.fulfill(json={'running': True, 'message': 'synthetic UI response'})
            if path == '/api/watcher/scan':
                return route.fulfill(json={'scanned_files': 0, 'directories': ['/watch/합성 검사']})
            if path.startswith('/api/evaluation/'):
                if path == '/api/evaluation/runs':
                    return route.fulfill(json={'items': [run], 'total': 1})
                if path == '/api/evaluation/runs/synthetic-run':
                    return route.fulfill(json=run)
                return route.fulfill(json={'items': [], 'total': 0})
            if req.method not in ('GET', 'HEAD'):
                raise AssertionError('Unexpected real mutation: ' + path)
            return route.continue_()

        page.route('**/api/**', api)
        page.goto(base + '/settings/search')
        expect(page.locator('[data-embedding-availability="search"]')).to_be_visible()
        expect(page.locator('form').get_by_role('combobox').first).to_contain_text('벡터')
        page.get_by_role('button', name='저장', exact=True).click()
        expect(page.get_by_text('검색 설정이 저장되었습니다.', exact=True)).to_be_visible()
        assert writes[-1]['search_mode'] == 'vector' and writes[-1]['multi_query_enabled'] is True
        checks.append('requested_search_preferences_remain_editable_without_embeddings')
        for name in ('hyde', 'chunking'):
            page.goto(base + '/settings/' + name)
            expect(page.locator('[data-embedding-availability="' + name + '"]')).to_be_visible()
        checks.append('hyde_and_chunking_prerequisites_visible')
        page.goto(base + '/settings/watcher')
        page.get_by_role('button', name='추가', exact=True).first.click()
        page.get_by_placeholder('/data/documents').first.fill('/watch/합성 검사')
        page.get_by_role('button', name='시작', exact=True).click()
        expect(page.get_by_text('감시가 시작되었습니다.', exact=True)).to_be_visible()
        assert watcher_requests[-1]['directories'] == ['/watch/합성 검사']
        checks.append('watcher_directory_reaches_request_without_starting_real_job')
        page.get_by_role('button', name='수동 스캔', exact=True).click()
        expect(page.get_by_text('지원 파일 0개를 확인했습니다. 이 작업은 인덱싱을 실행하지 않습니다.', exact=True)).to_be_visible()
        checks.append('scan_reports_actual_file_count_without_claiming_indexing')
        page.goto(base + '/evaluation/runs')
        expect(page.get_by_role('cell', name='미측정', exact=True)).to_have_count(2)
        expect(page.get_by_role('cell', name='0.0', exact=True)).to_have_count(1)
        page.get_by_role('button', name='상세', exact=True).click()
        expect(page.get_by_role('dialog').get_by_text('미측정', exact=True)).to_have_count(2)
        expect(page.get_by_role('dialog').get_by_text('0.0%', exact=True)).to_be_visible()
        checks.append('unmeasured_metrics_distinguished_from_true_zero')
        assert not errors, errors
        page.screenshot(path=str(out / 'evaluation-unmeasured.png'), full_page=True)
        browser.close()
    report = {'passed': True, 'built_next_ui': True, 'write_and_evaluation_responses': 'synthetic browser fixtures',
              'provider_calls': False, 'production_mutations': False, 'checks': checks}
    (out / 'functional-ui.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
