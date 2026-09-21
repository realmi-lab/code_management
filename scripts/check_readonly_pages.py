"""Read-only built-page smoke check. Provider status probes are replaced."""
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


def main():
    paths = ['/', '/documents', '/search', '/settings/search', '/settings/chunking',
             '/settings/hyde', '/settings/embedding', '/settings/generation', '/settings/guardrails',
             '/settings/reranking', '/evaluation/runs', '/evaluation/compare', '/monitoring',
             '/monitoring/metrics', '/monitoring/traces', '/codes']
    errors, failures, visits = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda exc: errors.append({'path': urlparse(page.url).path, 'error': str(exc)[:250], 'stack': exc.stack}))
        page.on('response', lambda response: failures.append({'path': urlparse(response.url).path, 'status': response.status}) if response.status >= 500 else None)

        def guard(route):
            path = urlparse(route.request.url).path
            if path == '/api/system/status':
                return route.fulfill(json={'status': 'ok', 'components': {}})
            if path.startswith('/api/health') and path not in ('/api/health/live', '/api/health/ready'):
                raise AssertionError('Unexpected provider probe: ' + path)
            if route.request.method not in ('GET', 'HEAD', 'OPTIONS'):
                raise AssertionError('Unexpected mutation: ' + path)
            return route.continue_()

        page.route('**/api/**', guard)
        for path in paths:
            response = page.goto('http://127.0.0.1:3500' + path, wait_until='networkidle')
            visits.append({'path': path, 'status': response.status})
            assert response.status == 200, path
        browser.close()
    report = {'passed': not errors and not failures, 'mode': 'real built UI and read-only APIs; provider status mocked',
              'provider_inference': False, 'visits': visits, 'page_errors': errors, 'http_5xx': failures}
    out = Path(__file__).resolve().parents[1]/'docs/verification/bug-audit-2026-09-21'
    out.mkdir(parents=True, exist_ok=True)
    (out/'readonly-pages.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))
    assert report['passed']


if __name__ == '__main__':
    main()
