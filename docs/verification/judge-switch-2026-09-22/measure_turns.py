"""Run demo conversation turns against the local API and collect per-stage timings from Langfuse.

Usage: python3 measure_turns.py <label> <out.json>
Reads .env via scripts/manage.load_env (no secrets are written to the output).
"""
import base64
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path('/Users/apple/Documents/ChatGPT/code_management')
sys.path.insert(0, str(ROOT / 'scripts'))
from manage import load_env  # noqa: E402

ENV = load_env(ROOT / '.env')
API = f"http://127.0.0.1:{ENV.get('API_PORT', '8010')}/api/code-catalog"
LF = f"http://127.0.0.1:{ENV.get('LANGFUSE_PORT', '3100')}"
LF_AUTH = base64.b64encode(f"{ENV['LANGFUSE_PUBLIC_KEY']}:{ENV['LANGFUSE_SECRET_KEY']}".encode()).decode()

DATASET = json.load(open(ROOT / 'docs/verification/catalog-quality-68/dataset.json'))
BY_ID = {row['id']: row for row in DATASET}
# Same six questions the 9/21 final check used (1,2,5,7,27,67) plus three more paraphrases and one unrelated query.
QUESTION_IDS = [1, 2, 5, 7, 27, 67, 3, 9, 12]
UNRELATED = {'id': 'weather', 'query': '오늘 서울 날씨 어때?', 'expected_code': None, 'kind': 'unrelated'}
BLOCK_MARK = '근거 검증을 통과하지 못했습니다'


def http(method, url, body=None, headers=None, timeout=250):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            payload = json.load(exc)
        except Exception:
            payload = {'detail': exc.read().decode(errors='replace')[:300]}
        return exc.code, payload


def langfuse(path):
    req = urllib.request.Request(LF + path, headers={'Authorization': 'Basic ' + LF_AUTH})
    return json.load(urllib.request.urlopen(req, timeout=30))


def find_trace(request_id, attempts=12):
    for _ in range(attempts):
        page = langfuse('/api/public/traces?limit=10&name=catalog-turn')
        for trace in page.get('data', []):
            inp = trace.get('input') or {}
            if isinstance(inp, str):
                try:
                    inp = json.loads(inp)
                except Exception:
                    inp = {}
            if inp.get('request') == request_id:
                return trace
        time.sleep(3)
    return None


def spans_for(trace_id):
    obs = langfuse(f'/api/public/observations?traceId={trace_id}&limit=100')
    out = {}
    for ob in obs.get('data', []):
        if ob.get('type') != 'SPAN' or ob.get('name') == 'catalog-turn':
            continue
        output = ob.get('output') if isinstance(ob.get('output'), dict) else {}
        usage = output.get('usage') if isinstance(output.get('usage'), dict) else None
        out[ob['name'].removeprefix('catalog-')] = {
            'duration_ms': output.get('duration_ms'),
            'model': output.get('model'),
            'status': output.get('status'),
            'judge_detail': output.get('judge_detail'),
            'completion_tokens': (usage or {}).get('completion_tokens'),
            'reasoning_tokens': ((usage or {}).get('completion_tokens_details') or {}).get('reasoning_tokens') if usage else None,
        }
    return out


def run_turn(row):
    status, thread = http('POST', f'{API}/threads?namespace=demo')
    if status != 200:
        return {'id': row['id'], 'error': f'thread create {status}: {thread}'}
    request_id = str(uuid.uuid4())
    body = {'request_id': request_id, 'expected_version': thread['version'], 'text': row['query']}
    start = time.monotonic()
    status, result = http('POST', f"{API}/threads/{thread['id']}/turn?namespace=demo", body)
    total = round(time.monotonic() - start, 1)
    record = {'id': row['id'], 'kind': row.get('kind'), 'query': row['query'], 'expected_code': row.get('expected_code'),
              'thread_id': thread['id'], 'request_id': request_id, 'http_status': status, 'total_s': total}
    if status == 200:
        codes = [c.get('code') for c in result.get('candidates', [])]
        answer = result.get('answer') or ''
        record.update({'action': result.get('action'), 'candidate_codes': codes,
                       'rank': (codes.index(row['expected_code']) + 1) if row.get('expected_code') in codes else None,
                       'answer_excerpt': answer[:160], 'answer_blocked': BLOCK_MARK in answer,
                       'ai_used': result.get('ai_used'), 'trace_flags': result.get('trace')})
        if row.get('expected_code'):
            expected_status, expected = http('GET', f"{API}/codes/{row['expected_code']}?namespace=demo")
            record['answer_contains_expected_original'] = (expected_status == 200 and expected.get('message','') in answer
                                                          and row['expected_code'] in answer)
        else:
            record['unrelated_has_no_candidates'] = not codes
    else:
        detail = result.get('detail') if isinstance(result, dict) else str(result)
        record.update({'detail': str(detail)[:300], 'answer_blocked': BLOCK_MARK in str(detail)})
    trace = find_trace(request_id)
    if trace:
        record['trace_id'] = trace['id']
        record['trace_output'] = trace.get('output')
        record['spans'] = spans_for(trace['id'])
    else:
        record['spans'] = None
    return record


def main():
    label, out_path = sys.argv[1], Path(sys.argv[2])
    _, status = http('GET', f'{API}/status?namespace=demo')
    rows = [BY_ID[i] for i in QUESTION_IDS] + [UNRELATED]
    results = []
    for row in rows:
        rec = run_turn(row)
        results.append(rec)
        spans = rec.get('spans') or {}
        judge = {k: v.get('duration_ms') for k, v in spans.items() if k.startswith('Explanation/')}
        print(f"[{label}] id={rec['id']} http={rec.get('http_status')} total={rec.get('total_s')}s rank={rec.get('rank')} "
              f"blocked={rec.get('answer_blocked')} judge_ms={judge} models={{ {', '.join(sorted({str(v.get('model')) for v in spans.values()}))} }}",
              flush=True)
        out_path.write_text(json.dumps({'label': label, 'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'status_llm': status.get('llm'),
                                        'namespace': 'demo', 'results': results}, ensure_ascii=False, indent=1))
        time.sleep(2)
    print('saved', out_path)


if __name__ == '__main__':
    main()
