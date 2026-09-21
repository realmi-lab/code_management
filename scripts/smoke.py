#!/usr/bin/env python3
"""Read-only HTTP checks after the REAL stack is started.

No fake server and no synthetic successful responses. By default this checks
readiness, original login, catalogue identity/listing, documents and frontend proxy. --query explicitly
performs a real RAG request (provider usage charges can apply). No upload,
modification, deletion or model key logging is performed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request
from manage import ROOT, SetupError, load_env, private_write, utc_now


def request_json(base, path, *, body=None, token=None, timeout=20):
    headers = {'Accept': 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Never copy a response body into logs; it can contain document content.
        raise SetupError(f'{path}: HTTP {exc.code}') from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise SetupError(f'{path}: connection/JSON failure ({type(exc).__name__})') from exc


def _exercise(root: Path = ROOT, query: str | None = None) -> dict:
    values = load_env(root / '.env')
    local=values.get('CODE_AUTH_MODE')=='local'
    if not values or (not local and not values.get('ADMIN_PASSWORD')): raise SetupError('Configure and start the full stack first.')
    api = f'http://127.0.0.1:{values.get("API_PORT", "8000")}'
    frontend = f'http://127.0.0.1:{values.get("WEB_PORT", "3500")}'
    checks = []
    request_json(api, '/api/health/ready')
    checks.append({'name': 'direct_api_readiness', 'passed': True})
    request_json(frontend, '/api/health/ready')
    checks.append({'name': 'frontend_to_api_proxy', 'passed': True})
    if local:
        if request_json(frontend,'/api/auth/mode').get('mode')!='local':raise SetupError('Local access mode is not active.')
        token=None
        checks.append({'name':'local_access_without_credentials','passed':True})
    else:
        login = request_json(frontend, '/api/auth/login', body={'username': values['ADMIN_USERNAME'], 'password': values['ADMIN_PASSWORD']})
        token = login.get('access_token')
        if not isinstance(token, str) or not token: raise SetupError('Login did not return an access token.')
        checks.append({'name': 'upstream_admin_login', 'passed': True})
    docs = request_json(frontend, '/api/documents?page=1&size=1', token=token)
    if not isinstance(docs.get('items'), list): raise SetupError('Document-list response shape is invalid.')
    checks.append({'name': 'document_listing', 'passed': True, 'document_count': docs.get('total')})
    profile = request_json(frontend, '/api/auth/me', token=token)
    catalog = request_json(frontend, '/api/code-catalog/status', token=token)
    if not profile.get('id') or catalog.get('user',{}).get('id') != profile['id']:
        raise SetupError('Original login and catalogue identity do not match.')
    checks.append({'name':'catalogue_uses_upstream_identity','passed':True})
    listing = request_json(frontend, '/api/code-catalog/codes?limit=1', token=token)
    if not isinstance(listing.get('items'),list): raise SetupError('Catalogue-list response shape is invalid.')
    checks.append({'name':'integrated_catalogue_listing','passed':True,'catalogue_count':listing.get('total')})
    if query:
        result = request_json(frontend, '/api/search/debug', token=token,
                              body={'query': query, 'generate_answer': True}, timeout=240)
        if not isinstance(result.get('answer'), str) or not isinstance(result.get('results'), list):
            raise SetupError('RAG response shape is invalid.')
        checks.append({'name': 'real_rag_request', 'passed': True,
                       'result_count': len(result['results']),
                       'trace_steps': [s.get('name') for s in result.get('pipeline_trace', [])],
                       'note': 'Successful request is not proof of a correct answer.'})
        print(result['answer'])
    report = {'at': utc_now(), 'real_http': True, 'passed': True, 'checks': checks,
              'rag_request_sent': bool(query), 'provider_call_independently_verified': False, 'quality_verified': False}
    private_write(root / '.local/http-smoke.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def exercise(root: Path = ROOT, query: str | None = None) -> dict:
    import uuid
    run_id=str(uuid.uuid4());started=utc_now()
    report={'run_id':run_id,'started_at':started,'passed':False,'state':'running','real_http':True,'quality_verified':False}
    path=root/'.local/http-smoke.json'
    private_write(path,json.dumps(report,indent=2))
    try:
        report={**_exercise(root,query),'run_id':run_id,'started_at':started,'state':'completed'}
        return report
    except Exception as exc:
        report.update(state='failed',error_type=type(exc).__name__,passed=False)
        raise
    finally:
        report['finished_at']=utc_now();private_write(path,json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', help='Explicitly send this query through the real RAG pipeline (provider charges may apply)')
    args = parser.parse_args()
    try:
        print(json.dumps(exercise(query=args.query), ensure_ascii=False, indent=2))
    except SetupError as exc:
        print(f'검증 실패: {exc}')
        raise SystemExit(1)
