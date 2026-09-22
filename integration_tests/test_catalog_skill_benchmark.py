"""Offline evaluator contract checks. No external models or live service calls."""
import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('catalog_skill_benchmark', ROOT / 'scripts/benchmark_catalog_skills.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def record(code, message, **overrides):
    return dict(code=code, message=message, menu='검사', trigger='검사 조건', revision=1,
                status='active', **overrides)


def test_bound_literals_reject_swapped_sources():
    corpus = [record('AA-1', '30초 이후에 요청하세요.'), record('BB-2', '30초 이내에 완료하세요.')]
    case = {'kind': 'compare', 'expected_codes': ['AA-1', 'BB-2'], 'check_direction': True}
    result = {'candidates': corpus, 'answer': 'AA-1: 30초 이내에 완료하세요.\nBB-2: 30초 이후에 요청하세요.'}
    checked = bench.evaluate_case(case, result, 200, corpus)
    assert not checked['objective_pass']
    assert not checked['objective_checks']['AA-1:message_bound_literal']
    assert not checked['objective_checks']['AA-1:direction_bound']


def test_direct_lookup_uses_candidate_original_not_answer_quote():
    corpus = [record('AA-1', '원문입니다.')]
    case = {'kind': 'direct', 'expected_codes': ['AA-1']}
    result = {'answer': '등록된 원문을 아래에서 확인하세요.', 'candidates': corpus, 'ai_used': False}
    assert bench.evaluate_case(case, result, 200, corpus)['objective_pass']
    result['candidates'] = [dict(corpus[0], trigger='다른 조건')]
    assert not bench.evaluate_case(case, result, 200, corpus)['objective_pass']


@pytest.mark.parametrize('field', ['business', 'message_type', 'message_code', 'purpose', 'title',
                                  'spelling_check', 'title_en', 'contents_en', 'notes', 'added_date',
                                  'source', 'id', 'updated_at'])
@pytest.mark.parametrize('mutation', ['changed', 'removed'])
def test_all_public_db_fields_must_be_preserved(field, mutation):
    source = record('AA-1', '등록 문구', **{field: {'nested': ['original', None]} if field == 'source' else 'original'})
    candidate = dict(source)
    if mutation == 'removed':
        candidate.pop(field)
    else:
        candidate[field] = 'changed'
    result = {'answer': '원문', 'candidates': [candidate], 'ai_used': False}
    checked = bench.evaluate_case({'kind': 'direct', 'expected_codes': ['AA-1']}, result, 200, [source])
    assert not checked['objective_checks']['candidate_original_fields_preserved']
    assert not checked['objective_pass']


def test_original_comparison_preserves_nested_json_types_and_absent_fields():
    source = record('AA-1', '원문', source={'synthetic': True, 'tags': ['one', 'two']}, notes=None)
    originals = {'AA-1': source}
    assert bench.original_record_matches(dict(reversed(list(source.items()))), originals)
    assert not bench.original_record_matches({**source, 'source': {'synthetic': 1, 'tags': ['one', 'two']}}, originals)
    assert not bench.original_record_matches({k: v for k, v in source.items() if k != 'notes'}, originals)
    assert not bench.original_record_matches({**source, 'unexpected': 'extra'}, originals)


@pytest.mark.parametrize('text', ['QA_X-1: 원문', 'qa_x-0001', 'A-0', 'A' * 16 + '-123456789012',
                                  'A' * 17 + '-1', 'AA-1234567890123', '_QA-1', 'QA-1_',
                                  'QA-1suffix', 'QA-１２', '한글QA-1한글', '`QA_X-1` BB-2'])
def test_code_parser_matches_service_contract(text):
    from code_agent.models import CODE_IN_TEXT
    assert bench.CODE.findall(text) == CODE_IN_TEXT.findall(text)


def test_underscore_code_binds_original_to_the_complete_identifier():
    source = record('QA_X-1', '등록 문구')
    checked = bench.evaluate_case({'kind': 'search', 'expected_codes': ['QA_X-1']},
                                 {'candidates': [source], 'answer': 'QA_X-1: 등록 문구'}, 200, [source])
    assert checked['objective_pass']
    assert checked['visible_reference_codes'] == ['QA_X-1']


def test_http_success_with_ai_error_is_not_objective_success():
    checked = bench.evaluate_case({'kind': 'unrelated'}, {'ai_error': {'status': 502}, 'answer': '실패'}, 200, [])
    assert not checked['objective_pass']


def test_unrelated_answer_cannot_claim_registered_code():
    checked = bench.evaluate_case({'kind': 'unrelated'}, {'answer': 'AA-1을 사용하세요.'}, 200, [])
    assert not checked['objective_pass']


def test_unrelated_answer_keeps_original_candidates_and_requires_semantic_review():
    corpus = [record('AA-1', '등록 원문', title_en='Original title')]
    result = {'answer': '등록된 근거로 날씨를 확인할 수 없습니다.', 'candidates': corpus}
    checked = bench.evaluate_case({'kind': 'unrelated'}, result, 200, corpus)
    assert checked['objective_pass']
    assert 'no_candidates' not in checked['objective_checks']
    assert checked['objective_checks']['no_registered_code_claim']
    assert checked['objective_checks']['candidate_original_fields_preserved']
    assert checked['manual_review'] and checked['structured_references'] == 'unavailable_in_public_api'
    result['candidates'] = [{**corpus[0], 'title_en': 'Changed'}]
    assert not bench.evaluate_case({'kind': 'unrelated'}, result, 200, corpus)['objective_pass']


def test_complete_quantity_set_is_snapshot_derived_and_checks_pagination():
    corpus = [record('AA-1', '30초 이후'), record('BB-2', '30초 이내'), record('CC-3', '130초 이후')]
    case = {'kind': 'broad', 'query': '30초 알림'}
    result = {'answer': 'AA-1: 30초 이후', 'candidates': corpus[:1]}
    incomplete = {'items': corpus[:1], 'total': 2}
    checked = bench.evaluate_case(case, result, 200, corpus, incomplete)
    assert not checked['objective_checks']['quantity_all_codes_exact']
    complete = {'items': corpus[:2], 'total': 2}
    assert bench.evaluate_case(case, result, 200, corpus, complete)['objective_pass']


def test_quantity_list_preserves_fields_beyond_the_message():
    source = record('AA-1', '30초 이후', notes='원문 비고')
    changed = {**source, 'notes': '다른 비고'}
    checked = bench.evaluate_case({'kind': 'broad', 'query': '30초 알림'},
                                 {'answer': '30초', 'candidates': [source]}, 200, [source],
                                 {'items': [changed], 'total': 1})
    assert checked['objective_checks']['quantity_all_codes_exact']
    assert not checked['objective_checks']['quantity_originals_preserved']


def test_quantity_commas_units_and_numeric_boundaries():
    assert bench.quantities('1,000원') == bench.quantities('1000원')
    assert bench.quantities('130초') != bench.quantities('30초')
    assert bench.quantities('30분') != bench.quantities('30초')


def test_nested_metrics_and_full_token_breakdown():
    metric = {'thread_id': 't', 'request_id': 'r', 'calls': [{'stage': 'Explanation', 'usage': {
        'prompt_tokens': 10, 'completion_tokens': 7, 'total_tokens': 17,
        'completion_tokens_details': {'reasoning_tokens': 4}, 'prompt_tokens_details': {'cached_tokens': 2}}}]}
    line = 'rag-api | ' + json.dumps({'event': 'catalog_turn_metrics ' + json.dumps(metric)})
    parsed = bench.parse_metrics(line)
    usage = bench.sum_usage(parsed[('t', 'r')])
    assert usage['complete'] and usage['actual_model_called']
    assert usage['totals'] == {'prompt_tokens': 10, 'completion_tokens': 7, 'total_tokens': 17,
                               'reasoning_tokens': 4, 'cached_tokens': 2}


def test_usage_missing_is_unknown_not_zero_and_failed_call_is_included():
    assert bench.sum_usage([])['totals']['total_tokens'] is None
    usage = bench.sum_usage([{'calls': [{'stage': 'generation', 'usage': {'total_tokens': 10}},
                                      {'stage': 'judge', 'status': 'failed', 'usage': None}]}])
    assert usage['actual_model_called'] is True
    assert not usage['complete']
    assert usage['totals']['total_tokens'] is None
    assert usage['observed_subtotals']['total_tokens'] == 10
    zero = bench.sum_usage([{'calls': []}])
    assert zero['complete'] and zero['totals']['total_tokens'] == 0
    assert zero['actual_model_called'] is False


def test_metrics_cannot_cross_threads_or_requests():
    rows = [{'case_id': 'direct', 'thread_id': 't', 'request_id': 'right', 'objective_checks': {},
             'status': 200, 'ai_error': None, 'ai_used': False}]
    logs = 'catalog_turn_metrics ' + json.dumps({'thread_id': 't', 'request_id': 'wrong', 'calls': []})
    bench.attach_metrics(rows, logs, [{'id': 'direct', 'kind': 'direct'}])
    assert rows[0]['actual_model_called'] is None
    assert not rows[0]['objective_pass']
    assert not rows[0]['ai_success']


def test_token_reduction_cannot_hide_candidate_loss_or_ai_failure():
    def row(tokens, candidates, passed=True):
        return {'case_id': 'one', 'repeat': 1, 'result': {'candidates': [{'code': c} for c in candidates]},
                'usage': {'complete': True, 'totals': {'total_tokens': tokens}},
                'objective_pass': passed, 'ai_success': passed}
    before = [row(100, ['AA-1', 'BB-2'])]
    assert not bench.compare_runs(before, [row(50, ['AA-1'])])['token_saving_verified']
    assert not bench.compare_runs(before, [row(50, ['AA-1', 'BB-2'], False)])['token_saving_verified']
    assert not bench.compare_runs([row(100, ['AA-1'], False)], [row(50, ['AA-1'], False)])['token_saving_verified']
    assert bench.compare_runs(before, [row(50, ['AA-1', 'BB-2'])])['token_saving_verified']
    growth = bench.compare_runs(before, [row(50, ['AA-1', 'BB-2', 'CC-3'])])
    assert growth['token_saving_verified']
    assert growth['pairs'][0]['candidate_set_preserved']
    assert not growth['pairs'][0]['candidate_set_equal']
    assert growth['pairs'][0]['candidate_codes_added'] == ['CC-3']
    new_contract = {**row(50, ['AA-1', 'BB-2']), 'evaluator_version': bench.EVALUATOR_VERSION}
    assert not bench.compare_runs(before, [new_contract])['token_saving_verified']


def test_false_premise_always_requires_semantic_review():
    corpus = [record('AA-1', '30초 이후')]
    checked = bench.evaluate_case({'kind': 'false_premise', 'expected_codes': ['AA-1']},
                                 {'answer': 'AA-1: 30초 이후', 'candidates': corpus}, 200, corpus)
    assert checked['objective_pass']
    assert any(item.startswith('Required:') for item in checked['manual_review'])
    assert checked['structured_references'] == 'unavailable_in_public_api'


def test_manifest_has_separate_frozen_core_and_holdout_without_answer_strings():
    manifest = json.loads(bench.DEFAULT_MANIFEST.read_text())
    assert manifest['frozen'] is True
    assert sum(case['suite'] == 'core' for case in manifest['cases']) == 12
    assert sum(case['suite'] == 'holdout' for case in manifest['cases']) == 8
    assert len({case['id'] for case in manifest['cases']}) == 20
    assert all('expected_message' not in case for case in manifest['cases'])


def test_existing_output_fails_before_any_api_call(tmp_path, monkeypatch):
    (tmp_path / 'baseline').mkdir()
    monkeypatch.setattr(bench, 'api', lambda *args, **kwargs: pytest.fail('API must not be called'))
    with pytest.raises(RuntimeError, match='refusing to overwrite'):
        bench.main(['--output', str(tmp_path), '--phase', 'baseline'])


def test_production_mutations_rejected_before_network():
    with pytest.raises(ValueError, match='demo conversations'):
        bench.api('/code-catalog/threads?namespace=production', {})


def test_baseline_and_after_runner_preserves_immutable_evidence_and_matches_settings(tmp_path, monkeypatch):
    manifest = tmp_path / 'input.json'
    case = {'id': 'direct', 'suite': 'core', 'kind': 'direct', 'query': 'AA-1', 'expected_codes': ['AA-1']}
    manifest.write_text(json.dumps({'cases': [case]}))
    corpus = [record('AA-1', '원문입니다.', source={'synthetic': True})]
    monkeypatch.setattr(bench, 'read_catalog', lambda scope: {'version': 1, 'rows': corpus if scope == 'demo' else []})
    settings = {'model': 'same', 'guardrails': True}
    monkeypatch.setattr(bench, 'read_settings', lambda: dict(settings))
    def fake_case(selected, repeat, rows):
        result = {'candidates': rows, 'answer': '원문을 확인하세요.', 'ai_used': False}
        return {'case_id': selected['id'], 'suite': 'core', 'repeat': repeat, 'thread_id': 't', 'request_id': 'r',
                'status': 200, 'result': result, 'api_error': None, 'ai_error': None, 'ai_used': False, 'seconds': 1,
                **bench.evaluate_case(selected, result, 200, rows)}
    monkeypatch.setattr(bench, 'run_case', fake_case)
    metrics = 'catalog_turn_metrics ' + json.dumps({'thread_id': 't', 'request_id': 'r', 'calls': []})
    monkeypatch.setattr(bench.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout=metrics, stderr=''))
    output = tmp_path / 'output'
    common = ['--output', str(output), '--manifest', str(manifest), '--runs', '1']
    bench.main(common + ['--phase', 'baseline'])
    baseline = (output / 'baseline/results.json').read_bytes()
    settings['guardrails'] = False
    with pytest.raises(RuntimeError, match='differ'):
        bench.main(common + ['--phase', 'after'])
    assert not (output / 'after').exists()
    settings['guardrails'] = True
    bench.main(common + ['--phase', 'after'])
    assert (output / 'baseline/results.json').read_bytes() == baseline
    summary = json.loads((output / 'after/summary.json').read_text())
    assert summary['objective_pass'] == 1
    assert summary['ai_success'] == 0
    assert summary['total_tokens_all_attempts'] == 0
    assert summary['production_unchanged']


def test_missing_baseline_completion_rejected_without_api_calls(tmp_path, monkeypatch):
    (tmp_path / 'baseline').mkdir()
    (tmp_path / 'baseline/context.json').write_text('{}')
    monkeypatch.setattr(bench, 'api', lambda *a, **kw: pytest.fail('No API before baseline validation'))
    with pytest.raises(RuntimeError, match='incomplete'):
        bench.main(['--output', str(tmp_path), '--phase', 'after'])


@pytest.fixture
def saved_phase(tmp_path):
    source = tmp_path / 'saved' / 'baseline'
    source.mkdir(parents=True)
    case = {'id': 'negative', 'suite': 'core', 'kind': 'unrelated', 'query': '등록되지 않은 날씨 정보'}
    corpus = {'version': 1, 'rows': [record('QA_X-1', '등록 원문', contents_en='Original content')]}
    manifest, settings = {'cases': [case]}, {'llm': {'model': 'saved-model'}}
    context = {'manifest_hash': bench.digest(manifest), 'corpus_hash': bench.digest(corpus),
               'settings_hash': bench.digest(settings), 'selected_cases': ['negative'], 'runs': 1}
    row = {'case_id': 'negative', 'repeat': 1, 'suite': 'core', 'query': case['query'],
           'thread_id': 't', 'request_id': 'r', 'status': 200, 'seconds': 2.0,
           'result': {'answer': '등록된 근거로 날씨를 확인할 수 없습니다.', 'candidates': corpus['rows']},
           'quantity_result': None, 'ai_error': None, 'api_error': None, 'ai_used': True,
           'objective_checks': {'no_candidates': False}, 'objective_pass': False,
           'metrics': [{'thread_id': 't', 'request_id': 'r', 'calls': [{'usage': {'total_tokens': 12}}]}]}
    summary = {'attempts': 1, 'objective_pass': 0, 'production_unchanged': True,
               'corpus_unchanged': True, 'settings_unchanged': True, 'metrics_collection_success': True}
    values = {'context.json': context, 'manifest.json': manifest, 'corpus.json': corpus,
              'results.json': [row], 'summary.json': summary, 'settings.json': settings,
              'production.json': {'before_hash': 'same', 'after_hash': 'same', 'unchanged': True}}
    for name, value in values.items():
        (source / name).write_text(json.dumps(value, ensure_ascii=False))
    return source


def test_offline_regrade_is_versioned_and_preserves_raw_inputs_without_calls(saved_phase, tmp_path, monkeypatch):
    monkeypatch.setattr(bench, 'api', lambda *a, **kw: pytest.fail('Offline regrade cannot call API'))
    monkeypatch.setattr(bench.subprocess, 'run', lambda *a, **kw: pytest.fail('Offline regrade cannot run Docker'))
    original = {path.name: path.read_bytes() for path in saved_phase.iterdir()}
    output = tmp_path / 'regraded'
    bench.main(['--regrade', str(saved_phase), '--output', str(output)])
    assert {path.name: path.read_bytes() for path in saved_phase.iterdir()} == original
    old = json.loads(original['results.json'])[0]
    new = json.loads((output / 'results.json').read_text())[0]
    assert new['result'] == old['result'] and new['metrics'] == old['metrics']
    assert new['objective_pass'] and new['evaluator_version'] == bench.EVALUATOR_VERSION
    assert new['usage']['totals']['total_tokens'] == 12
    summary = json.loads((output / 'summary.json').read_text())
    assert summary['objective_pass'] == 1 and summary['production_unchanged']
    receipt = json.loads((output / 'regrade.json').read_text())
    assert receipt['source_sha256']['results.json'] == hashlib.sha256(original['results.json']).hexdigest()
    assert receipt['evaluator_version'] == bench.EVALUATOR_VERSION and receipt['reasons']
    assert receipt['model_calls_made'] == 0 and not receipt['semantic_accuracy_verified']
    assert (output / 'corpus.json').read_bytes() == original['corpus.json']
    assert (output / 'source-summary.json').read_bytes() == original['summary.json']


def test_offline_regrade_refuses_overwrite_or_writing_inside_source(saved_phase, tmp_path):
    with pytest.raises(RuntimeError, match='refusing to overwrite'):
        bench.regrade_saved_phase(saved_phase, saved_phase)
    with pytest.raises(RuntimeError, match='outside'):
        bench.regrade_saved_phase(saved_phase, saved_phase / 'new')
    assert not (saved_phase / 'new').exists()


@pytest.mark.parametrize('fault', ['running', 'changed_corpus', 'changed_settings', 'duplicate_result'])
def test_offline_regrade_rejects_incomplete_or_changed_saved_evidence(saved_phase, tmp_path, fault):
    if fault == 'running':
        (saved_phase / 'summary.json').unlink()
    elif fault in ('changed_corpus', 'changed_settings'):
        name = 'corpus.json' if fault == 'changed_corpus' else 'settings.json'
        (saved_phase / name).write_text('{}')
    else:
        path = saved_phase / 'results.json'
        rows = json.loads(path.read_text())
        path.write_text(json.dumps(rows + rows))
    output = tmp_path / 'regraded'
    with pytest.raises(RuntimeError):
        bench.regrade_saved_phase(saved_phase, output)
    assert not output.exists()
