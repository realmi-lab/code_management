"""Opt-in real-provider demo benchmark. Importing this module makes no API calls.

Run baseline and after into different, immutable phase directories under one output
root. Objective checks deliberately do not claim semantic entailment accuracy.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / 'docs/verification/catalog-skills-2026-09-22/manifest.json'
BASE = 'http://127.0.0.1:8010/api'
# Keep the exact public code grammar/boundaries from code_agent.models.CODE_IN_TEXT.
CODE = re.compile(r'(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]{0,15}-[0-9]{1,12})(?![A-Za-z0-9_])')
EVALUATOR_VERSION = 'catalog-skills-objective-v2'
EVALUATOR_CHANGES = [
    'Compare every JSON field and nested value of candidates and quantity rows with the frozen DB snapshot.',
    'Use the service code grammar, including underscores and ASCII numeric suffixes.',
    'Unrelated questions may retain original retrieval candidates; visible references and unsupported claims are assessed separately.',
    'Candidate nonregression requires retaining all previous candidates; additions and exact set/order equality are reported separately.',
]
QUANTITY = re.compile(r'(?<![\d,.+\-])([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(초|분|시간|일|회|자|원|%)')
OPERATOR = re.compile(r'^\s*(이후|이내|이상|이하|미만|초과|후|안에|뒤)')
SEARCH_SETTINGS = ('search_mode', 'reranking_enabled', 'reranker_model', 'reranker_top_k',
                   'retriever_top_k', 'hyde_enabled', 'hyde_model', 'multi_query_enabled',
                   'multi_query_count', 'llm_model', 'llm_temperature', 'embedding_provider',
                   'embedding_model', 'chunk_size', 'chunk_overlap', 'chunking_strategy',
                   'contextual_chunking_enabled', 'contextual_chunking_model', 'contextual_chunking_max_doc_chars',
                   'keyword_engine', 'rrf_constant', 'vector_weight', 'keyword_weight',
                   'cascading_bm25_threshold', 'cascading_min_qualifying_docs', 'cascading_min_doc_score',
                   'cascading_fallback_vector_weight', 'cascading_fallback_keyword_weight',
                   'query_expansion_enabled', 'query_expansion_max_keywords', 'multi_query_model',
                   'exact_citation_enabled', 'numeric_verification_enabled', 'guardrails',
                   'pii_detection_enabled', 'injection_detection_enabled', 'hallucination_detection_enabled',
                   'retrieval_quality_gate_enabled', 'faithfulness_enabled', 'cache_enabled',
                   'cache_search_ttl', 'llm_provider', 'system_prompt')
MODEL_SETTINGS = ('provider', 'model', 'reasoning_effort', 'judge_provider', 'judge_model',
                  'judge_reasoning_effort')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def write_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def api(path, body=None):
    """Only caller-controlled demo turns and read-only catalog/settings requests."""
    if body is not None and not (path.startswith('/code-catalog/threads') and 'namespace=demo' in path):
        raise ValueError('Benchmark mutations are restricted to demo conversations')
    req = urllib.request.Request(BASE + path, data=None if body is None else
                                 json.dumps(body, ensure_ascii=False).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=265) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors='replace')
        try:
            result = json.loads(raw)
        except ValueError:
            result = {'error_type': 'non_json_http_error'}
        return exc.code, result


def get(path):
    status, result = api(path)
    if status != 200:
        raise RuntimeError(f'Read failed: HTTP {status}, {path}')
    return result


def read_catalog(namespace):
    rows, version, offset = [], None, 0
    while True:
        page = get(f'/code-catalog/codes?namespace={namespace}&include_retired=true&limit=200&offset={offset}')
        if version is not None and version != page['catalog_version']:
            raise RuntimeError('Catalog changed during snapshot')
        version = page['catalog_version']
        rows.extend(page['items'])
        if len(rows) >= page['total']:
            break
        if not page['items']:
            raise RuntimeError('Incomplete catalog pagination')
        offset += len(page['items'])
    return {'version': version, 'rows': sorted(rows, key=lambda row: row['code'])}


def read_settings():
    settings = get('/settings')
    status = get('/code-catalog/status?namespace=demo')
    return {'search': {key: settings.get(key) for key in SEARCH_SETTINGS},
            'llm': {key: status.get('llm', {}).get(key) for key in MODEL_SETTINGS},
            'embedding': status.get('embedding'), 'index_ready': status.get('index_ready')}


def quantities(text):
    return {(str(Decimal(m.group(1).replace(',', '')).normalize()), m.group(2))
            for m in QUANTITY.finditer(text)}


def directional_quantities(text):
    result = set()
    for match in QUANTITY.finditer(text):
        operator = OPERATOR.match(text[match.end():])
        if operator:
            op = {'후': '이후', '뒤': '이후', '안에': '이내'}.get(operator.group(1), operator.group(1))
            result.add((str(Decimal(match.group(1).replace(',', '')).normalize()), match.group(2), op))
    return result


def code_blocks(answer):
    """Literal binding is conservative: evidence must follow its code before another code."""
    matches = list(CODE.finditer(answer))
    blocks = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(answer)
        blocks.setdefault(match.group(1).upper(), []).append(answer[match.end():end])
    return blocks


def original_record_matches(row, by_code):
    """API candidates are complete DB records; no field allowlist may hide loss.

    Canonical JSON ignores object key order but preserves JSON value types and
    nested source metadata, including absent-versus-null fields.
    """
    return row.get('code') in by_code and digest(row) == digest(by_code[row['code']])


def evaluate_case(case, result, status, corpus, quantity_result=None):
    by_code = {row['code']: row for row in corpus}
    candidates = result.get('candidates') or []
    codes = [row.get('code') for row in candidates]
    expected = case.get('expected_codes', [])
    answer = result.get('answer') or ''
    mentioned = {match.group(1).upper() for match in CODE.finditer(answer)}
    blocks = code_blocks(answer)
    checks = {'http_success': status == 200,
              'no_ai_error': not result.get('ai_error'),
              'no_draft': result.get('draft') is None,
              'candidates_unique': len(codes) == len(set(codes)),
              'candidate_original_fields_preserved': all(
                  original_record_matches(row, by_code) for row in candidates)}
    review = []
    kind = case['kind']
    if expected:
        checks['expected_candidates_present'] = set(expected) <= set(codes)
    if kind == 'direct':
        checks['direct_lookup_no_ai_used'] = result.get('ai_used') is False
        checks['direct_candidate_set_exact'] = set(codes) == set(expected)
    elif kind == 'missing':
        checks['missing_code_reported'] = set(case['missing_codes']) <= set(result.get('missing_codes') or [])
        checks['no_candidates'] = not candidates
        checks['no_invented_code'] = mentioned <= set(case['missing_codes'])
    elif kind == 'unrelated':
        checks['no_registered_code_claim'] = not mentioned
        checks['nonempty_response'] = bool(answer.strip())
        review.append('Verify that the response declines unsupported claims and makes no unsupported AI references; retained original retrieval candidates do not prove relevance. Structured AI references are unavailable in this API.')
    else:
        checks['visible_references_from_candidates'] = mentioned <= set(codes)
        for code in expected:
            checks[f'{code}:visible_reference'] = code in mentioned
            for field in case.get('literal_fields', ['message']):
                value = by_code[code].get(field, '')
                checks[f'{code}:{field}_bound_literal'] = bool(value) and any(value in block for block in blocks.get(code, []))
            if case.get('check_direction'):
                expected_directions = directional_quantities(by_code[code]['message'])
                observed = set().union(*(directional_quantities(block) for block in blocks.get(code, [])))
                checks[f'{code}:direction_bound'] = bool(expected_directions) and expected_directions <= observed
                extra = observed - directional_quantities(' '.join(str(by_code[code].get(k, '')) for k in ('message', 'menu', 'trigger')))
                if extra:
                    review.append(f'{code}: Additional directional quantity requires checking whether it is a contrast or an unsupported assertion.')
        if kind == 'broad':
            terms = quantities(case['query'])
            complete = {row['code'] for row in corpus if row.get('status') == 'active'
                        and terms <= quantities(' '.join(str(row.get(k, '')) for k in ('message', 'menu', 'trigger')))}
            checks['quantity_list_available'] = quantity_result is not None
            if quantity_result is not None:
                listed = [row['code'] for row in quantity_result['items']]
                checks['quantity_all_codes_exact'] = set(listed) == complete and len(listed) == len(complete)
                checks['quantity_total_exact'] = quantity_result['total'] == len(complete)
                checks['quantity_originals_preserved'] = all(
                    original_record_matches(row, by_code) for row in quantity_result['items'])
            checks['quantity_in_answer'] = terms <= quantities(answer)
            review.append('Semantic retrieval candidates and the complete literal quantity list serve different purposes; assess relevance separately.')
        if kind == 'false_premise':
            review.append('Required: verify that the false premise is explicitly corrected, not merely repeated beside a correct quote.')
        review.append('Check explanation entailment and relevance; literal/source checks alone do not prove semantic accuracy.')
    ranks = {code: codes.index(code) + 1 if code in codes else None for code in expected}
    return {'evaluator_version': EVALUATOR_VERSION,
            'objective_checks': checks, 'objective_pass': all(checks.values()),
            'manual_review': review, 'structured_references': 'unavailable_in_public_api',
            'visible_reference_codes': sorted(mentioned), 'expected_ranks': ranks,
            'expected_set_recall': sum(code in codes for code in expected) / len(expected) if expected else None,
            'reciprocal_rank': max((1 / rank for rank in ranks.values() if rank), default=0) if expected else None}


def parse_metrics(log_text):
    """Accept plain logs and the service's JSON-inside-JSON event logger."""
    found = {}
    marker = 'catalog_turn_metrics '
    for line in log_text.splitlines():
        if marker not in line:
            continue
        event = line
        try:
            outer = json.loads(line[line.index('{'):])
            if isinstance(outer.get('event'), str):
                event = outer['event']
        except (ValueError, AttributeError):
            pass
        try:
            value = json.loads(event.split(marker, 1)[1])
        except (ValueError, IndexError):
            continue
        key = (value.get('thread_id'), value.get('request_id'))
        if all(key):
            found.setdefault(key, []).append(value)
    return found


def sum_usage(metrics):
    calls = [call for event in metrics for call in event.get('calls', [])]
    fields = ('prompt_tokens', 'completion_tokens', 'total_tokens', 'reasoning_tokens', 'cached_tokens')
    totals = {field: 0 for field in fields}
    present = {field: 0 for field in fields}
    for call in calls:
        usage = call.get('usage')
        if not isinstance(usage, dict):
            continue
        values = {**usage,
                  'reasoning_tokens': (usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
                  'cached_tokens': (usage.get('prompt_tokens_details') or {}).get('cached_tokens')}
        for field in fields:
            value = values.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                totals[field] += value
                present[field] += 1
    # No calls with a present event is verified zero usage. Missing events are unknown.
    return {'calls': len(calls), 'actual_model_called': bool(calls) if metrics else None,
            'complete': bool(metrics) and present['total_tokens'] == len(calls),
            'totals': {field: totals[field] if metrics and present[field] == len(calls) else None for field in fields},
            'observed_subtotals': totals, 'field_coverage': present,
            'missing_usage_calls': sum(not isinstance(call.get('usage'), dict) for call in calls)}


def quantity_pages(query, version):
    rows, offset, total = [], 0, None
    while True:
        path = '/code-catalog/quantity-matches?' + urllib.parse.urlencode(
            {'namespace': 'demo', 'q': query, 'limit': 100, 'offset': offset, 'version': version})
        page = get(path)
        if total is not None and total != page['total']:
            raise RuntimeError('Quantity list changed during pagination')
        total = page['total']
        rows.extend(page['items'])
        if not page['has_more']:
            return {'items': rows, 'total': total}
        if not page['items']:
            raise RuntimeError('Incomplete quantity list')
        offset += len(page['items'])


def run_case(case, repeat, corpus):
    row = {'case_id': case['id'], 'suite': case['suite'], 'repeat': repeat,
           'query': case['query'], 'request_id': str(uuid.uuid4()), 'thread_id': None}
    start = time.monotonic()
    status, result, quantity_result = None, {}, None
    try:
        thread_status, thread = api('/code-catalog/threads?namespace=demo', {})
        if thread_status != 200:
            raise RuntimeError(f'Thread creation HTTP {thread_status}')
        row['thread_id'] = thread['id']
        status, result = api(f"/code-catalog/threads/{thread['id']}/turn?namespace=demo", {
            'request_id': row['request_id'], 'expected_version': thread['version'],
            'text': case['query'], 'action': case.get('action', 'auto')})
        row['api_error'] = None if status == 200 else {'status': status, 'detail': result}
        if case['kind'] == 'broad' and status == 200:
            quantity_result = quantity_pages(case['query'], result['catalog_version'])
    except Exception as exc:
        row['api_error'] = {'type': type(exc).__name__, 'message': str(exc)}
    row.update(status=status, result=result, quantity_result=quantity_result,
               ai_error=result.get('ai_error'), ai_used=result.get('ai_used'),
               seconds=round(time.monotonic() - start, 3))
    row.update(evaluate_case(case, result, status, corpus, quantity_result))
    return row


def attach_metrics(rows, log_text, cases):
    parsed = parse_metrics(log_text)
    by_id = {case['id']: case for case in cases}
    for row in rows:
        events = parsed.get((row['thread_id'], row['request_id']), [])
        apply_metrics(row, by_id[row['case_id']], events)


def apply_metrics(row, case, events):
    """Apply only observed per-turn metrics, including for offline regrading."""
    row['metrics'] = events
    row['usage'] = sum_usage(events)
    row['actual_model_called'] = row['usage']['actual_model_called']
    if case['kind'] == 'direct':
        row['objective_checks']['direct_no_model_calls'] = row['actual_model_called'] is False
    elif case['kind'] not in ('missing', 'unrelated'):
        row['objective_checks']['expected_ai_was_used'] = row['ai_used'] is True
        row['objective_checks']['expected_model_call_observed'] = row['actual_model_called'] is True
    row['objective_pass'] = all(row['objective_checks'].values())
    row['ai_success'] = (row['status'] == 200 and not row['ai_error'] and row['ai_used'] is True
                         and row['actual_model_called'] is True)


def summarize(rows):
    complete = [row for row in rows if row['usage']['complete']]
    relevant = [row for row in rows if row['expected_set_recall'] is not None]
    return {'evaluator_version': EVALUATOR_VERSION,
            'attempts': len(rows), 'http_success': sum(row['status'] == 200 for row in rows),
            'api_errors': sum(bool(row['api_error']) for row in rows),
            'ai_errors': sum(bool(row['ai_error']) for row in rows),
            'actual_model_called': sum(row['actual_model_called'] is True for row in rows),
            'ai_success': sum(row['ai_success'] for row in rows),
            'objective_pass': sum(row['objective_pass'] for row in rows),
            'manual_review_cases': sum(bool(row['manual_review']) for row in rows),
            'usage_complete_attempts': len(complete),
            'total_tokens_all_attempts': sum(row['usage']['totals']['total_tokens'] for row in complete) if len(complete) == len(rows) else None,
            'observed_total_tokens': sum(row['usage']['observed_subtotals']['total_tokens'] for row in rows),
            'mean_tokens_all_attempts': statistics.mean(row['usage']['totals']['total_tokens'] for row in complete) if complete and len(complete) == len(rows) else None,
            'mean_expected_set_recall': statistics.mean(row['expected_set_recall'] for row in relevant) if relevant else None,
            'mean_reciprocal_rank': statistics.mean(row['reciprocal_rank'] for row in relevant) if relevant else None,
            'median_seconds': statistics.median(row['seconds'] for row in rows) if rows else None,
            'accuracy_claim': 'Objective contract checks only; semantic accuracy requires the recorded manual review.'}


def compare_runs(before, after):
    old = {(row['case_id'], row['repeat']): row for row in before}
    pairs, deltas, successful_deltas = [], [], []
    for row in after:
        prior = old[(row['case_id'], row['repeat'])]
        old_codes = [item['code'] for item in prior['result'].get('candidates', [])]
        new_codes = [item['code'] for item in row['result'].get('candidates', [])]
        usage_complete = row['usage']['complete'] and prior['usage']['complete']
        delta = row['usage']['totals']['total_tokens'] - prior['usage']['totals']['total_tokens'] if usage_complete else None
        pair = {'case_id': row['case_id'], 'repeat': row['repeat'],
                'evaluation_contract_equal': prior.get('evaluator_version') == row.get('evaluator_version'),
                'candidate_set_equal': set(new_codes) == set(old_codes),
                'candidate_set_preserved': set(old_codes) <= set(new_codes),
                'candidate_codes_lost': sorted(set(old_codes) - set(new_codes)),
                'candidate_codes_added': sorted(set(new_codes) - set(old_codes)),
                'candidate_order_equal': new_codes == old_codes,
                'objective_regression': prior['objective_pass'] and not row['objective_pass'],
                'ai_regression': prior['ai_success'] and not row['ai_success'],
                'total_token_delta': delta}
        pairs.append(pair)
        if delta is not None:
            deltas.append(delta)
            if prior['objective_pass'] and row['objective_pass']:
                successful_deltas.append(delta)
    passed = all(pair['evaluation_contract_equal'] and pair['candidate_set_preserved']
                 and not pair['objective_regression'] and not pair['ai_regression'] for pair in pairs)
    return {'pairs': pairs, 'candidate_and_objective_nonregression': passed,
            'all_usage_pairs_complete': len(deltas) == len(pairs),
            'total_token_delta': sum(deltas) if len(deltas) == len(pairs) else None,
            'successful_response_pairs': len(successful_deltas),
            'successful_response_token_delta': sum(successful_deltas) if successful_deltas else None,
            'token_saving_verified': passed and len(successful_deltas) == len(pairs) and sum(successful_deltas) < 0,
            'semantic_accuracy_verified': False}


def regrade_saved_phase(source, output):
    """Re-evaluate completed saved evidence without API, Docker or model calls."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise RuntimeError('Evidence directory already exists; refusing to overwrite: ' + str(output))
    if source in output.parents:
        raise RuntimeError('Regrade output must be outside the immutable source phase')
    required = ('context.json', 'manifest.json', 'corpus.json', 'results.json', 'summary.json')
    raw = {}
    for name in required:
        path = source / name
        if not path.is_file():
            raise RuntimeError('Source phase is incomplete: missing ' + name)
        raw[name] = path.read_bytes()
    saved = {name: json.loads(value) for name, value in raw.items()}
    context, manifest, corpus = (saved[name] for name in required[:3])
    rows, previous_summary = saved['results.json'], saved['summary.json']
    if digest(manifest) != context['manifest_hash'] or digest(corpus) != context['corpus_hash']:
        raise RuntimeError('Saved manifest or corpus does not match the source context')
    for name in ('settings.json', 'production.json'):
        if (source / name).is_file():
            raw[name] = (source / name).read_bytes()
    if 'settings.json' in raw and digest(json.loads(raw['settings.json'])) != context['settings_hash']:
        raise RuntimeError('Saved settings do not match the source context')
    expected = {(case_id, repeat) for case_id in context['selected_cases']
                for repeat in range(1, context['runs'] + 1)}
    observed = [(row['case_id'], row['repeat']) for row in rows]
    if set(observed) != expected or len(observed) != len(expected) or previous_summary['attempts'] != len(rows):
        raise RuntimeError('Source phase has missing, duplicate or unexpected results')
    cases = {case['id']: case for case in manifest['cases']}
    for row in rows:
        case = cases[row['case_id']]
        row.update(evaluate_case(case, row['result'], row['status'], corpus['rows'], row.get('quantity_result')))
        apply_metrics(row, case, row.get('metrics', []))
    summary = summarize(rows)
    for key in ('production_unchanged', 'corpus_unchanged', 'settings_unchanged', 'metrics_collection_success'):
        summary[key] = previous_summary.get(key)
    receipt = {'mode': 'offline_regrade', 'evaluator_version': EVALUATOR_VERSION,
               'reasons': EVALUATOR_CHANGES, 'source_phase': str(source),
               'source_evaluator_version': previous_summary.get('evaluator_version', 'legacy-unversioned'),
               'source_sha256': {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()},
               'raw_model_outputs_reused': True, 'model_calls_made': 0,
               'semantic_accuracy_verified': False}
    output.mkdir(parents=True, exist_ok=False)
    for name in ('context.json', 'manifest.json', 'corpus.json', 'settings.json', 'production.json'):
        if name in raw:
            (output / name).write_bytes(raw[name])
    (output / 'source-summary.json').write_bytes(raw['summary.json'])
    write_json(output / 'results.json', rows)
    write_json(output / 'summary.json', summary)
    write_json(output / 'regrade.json', receipt)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=('baseline', 'after'))
    parser.add_argument('--regrade', type=Path, metavar='SAVED_PHASE_DIR',
                        help='Offline regrade of a completed phase into a new --output directory; no service calls')
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--runs', type=int, default=2)
    parser.add_argument('--concurrency', type=int, choices=(1, 2), default=2)
    parser.add_argument('--concurrency2', dest='concurrency', action='store_const', const=2)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--suite', choices=('core', 'holdout', 'all'), default='core')
    args = parser.parse_args(argv)
    if args.regrade is not None:
        if args.phase is not None:
            parser.error('--regrade cannot be combined with --phase')
        print(json.dumps(regrade_saved_phase(args.regrade, args.output), ensure_ascii=False), flush=True)
        return
    if args.phase is None:
        parser.error('--phase is required for a live benchmark')
    if args.runs < 1 or args.limit < 0:
        parser.error('runs must be positive and limit nonnegative')
    manifest = json.loads(args.manifest.read_text())
    cases = [case for case in manifest['cases'] if args.suite == 'all' or case['suite'] == args.suite]
    cases = cases[:args.limit or None]
    if not cases:
        parser.error('No selected cases')
    phase = args.output / args.phase
    if phase.exists():
        raise RuntimeError('Evidence directory already exists; refusing to overwrite: ' + str(phase))
    if args.phase == 'after' and not (args.output / 'baseline/context.json').is_file():
        raise RuntimeError('After requires baseline/context.json under the same output root')
    if args.phase == 'after':
        baseline_summary_path = args.output / 'baseline/summary.json'
        if not baseline_summary_path.is_file():
            raise RuntimeError('Baseline is incomplete: summary.json is missing')
        baseline_summary = json.loads(baseline_summary_path.read_text())
        if baseline_summary['attempts'] != len(cases) * args.runs or not all(
                baseline_summary[key] for key in ('production_unchanged', 'corpus_unchanged', 'settings_unchanged')):
            raise RuntimeError('Baseline was incomplete or its environment changed')
    corpus = read_catalog('demo')
    if not all(row.get('source', {}).get('synthetic') for row in corpus['rows']):
        raise RuntimeError('Demo contains records without synthetic provenance')
    by_code = {row['code']: row for row in corpus['rows']}
    for case in cases:
        if not set(case.get('expected_codes', [])) <= set(by_code):
            raise RuntimeError('Expected code missing from frozen corpus: ' + case['id'])
        if set(case.get('missing_codes', [])) & set(by_code):
            raise RuntimeError('Missing-code case exists in corpus: ' + case['id'])
    settings = read_settings()
    context = {'manifest_hash': digest(manifest), 'corpus_hash': digest(corpus),
               'settings_hash': digest(settings), 'selected_cases': [case['id'] for case in cases],
               'runs': args.runs, 'concurrency': args.concurrency,
               'scope': 'demo synthetic only', 'cache_policy': 'existing service cache; no invalidation'}
    if args.phase == 'after':
        prior = json.loads((args.output / 'baseline/context.json').read_text())
        if prior != context:
            raise RuntimeError('Baseline/after manifest, corpus, settings or execution parameters differ')
    phase.mkdir(parents=True, exist_ok=False)
    write_json(phase / 'context.json', context)
    write_json(phase / 'manifest.json', manifest)
    write_json(phase / 'corpus.json', corpus)
    write_json(phase / 'settings.json', settings)
    production_before = digest(read_catalog('production'))
    write_json(phase / 'production.json', {'before_hash': production_before})
    started = datetime.now(timezone.utc).isoformat()
    rows = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for repeat in range(1, args.runs + 1):
            futures = [pool.submit(run_case, case, repeat, corpus['rows']) for case in cases]
            for future in as_completed(futures):
                row = future.result()
                rows.append(row)
                write_json(phase / 'results.json', rows)
                print(json.dumps({key: row[key] for key in ('case_id', 'repeat', 'status', 'seconds', 'objective_pass')}, ensure_ascii=False), flush=True)
    sys.path.insert(0, str(ROOT / 'scripts'))
    import manage
    logs = subprocess.run(manage.compose_args() + ['logs', '--no-color', '--since', started, 'rag-api'],
                          capture_output=True, text=True, timeout=60)
    attach_metrics(rows, logs.stdout + '\n' + logs.stderr if logs.returncode == 0 else '', cases)
    write_json(phase / 'results.json', rows)
    production_after = digest(read_catalog('production'))
    write_json(phase / 'production.json', {'before_hash': production_before, 'after_hash': production_after,
                                         'unchanged': production_before == production_after})
    summary = summarize(rows)
    summary.update(production_unchanged=production_before == production_after,
                   corpus_unchanged=digest(read_catalog('demo')) == context['corpus_hash'],
                   settings_unchanged=digest(read_settings()) == context['settings_hash'],
                   metrics_collection_success=logs.returncode == 0)
    write_json(phase / 'summary.json', summary)
    if args.phase == 'after':
        before = json.loads((args.output / 'baseline/results.json').read_text())
        comparison = compare_runs(before, rows)
        comparison['environment_unchanged'] = all(summary[key] for key in ('production_unchanged', 'corpus_unchanged', 'settings_unchanged'))
        if not comparison['environment_unchanged']:
            comparison['token_saving_verified'] = False
        write_json(phase / 'comparison.json', comparison)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
