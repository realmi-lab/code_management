"""Offline tests for audit attribution; no retrieval/model/provider calls."""
import importlib.util
import json
from pathlib import Path


spec = importlib.util.spec_from_file_location('retrieval_audit', Path(__file__).resolve().parents[1] /
                                             'scripts/audit_catalog_retrieval.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_retrieval_miss_is_not_misattributed_to_reranker():
    report = audit.stage_report(['EXPECTED'], {'vector': ['OTHER'], 'keyword': [],
        'rrf': ['OTHER'], 'reranker_input': ['OTHER']})
    assert report['first_loss'] == {'EXPECTED': 'candidate_collection'}


def test_single_engine_hit_can_be_lost_at_reranker_boundary():
    report = audit.stage_report(['EXPECTED'], {'vector': ['EXPECTED'], 'keyword': ['OTHER'],
        'rrf': ['OTHER', 'EXPECTED'], 'reranker_input': ['OTHER']})
    assert report['expected_ranks']['rrf']['EXPECTED'] == 2
    assert report['first_loss']['EXPECTED'] == 'reranker_input'


def test_unexecuted_reranker_has_no_claimed_output():
    stages = {'vector': ['EXPECTED'], 'keyword': [], 'rrf': ['EXPECTED'], 'reranker_input': ['EXPECTED']}
    report = audit.stage_report(['EXPECTED'], stages)
    assert report['first_loss']['EXPECTED'] is None
    assert 'reranked' not in report['expected_ranks']


def test_reranked_loss_and_recall_preserve_multiple_relevance_labels():
    case = {'expected_codes': ['A', 'B'], **audit.stage_report(['A', 'B'], {
        'vector': ['A', 'B'], 'keyword': ['B'], 'rrf': ['B', 'A'],
        'reranker_input': ['B', 'A'], 'reranked': ['B']})}
    assert case['first_loss'] == {'A': 'reranked', 'B': None}
    summary = audit.summarize_cases([case])
    assert summary['reranked']['recall'] == 0.5
    assert summary['rrf']['recall'] == 1


def test_character_limit_is_strictly_above_512():
    assert audit.length_summary([0, 512, 513])['over_512_characters'] == 1


def test_metadata_challenge_labels_match_synthetic_source_fields():
    root = Path(__file__).resolve().parents[1]
    folder = root / 'docs/verification/catalog-skills-2026-09-22'
    cases = json.loads((folder / 'retrieval-challenge.json').read_text())['cases']
    rows = json.loads((root / 'extensions/code_agent/data/sample_catalog_300.json').read_text())
    for case in cases:
        matches = {row['message_code'] for row in rows if row['_meta']['status'] == 'active' and all(
            row.get(field) == value for field, value in case['evidence_fields'].items())}
        assert matches == set(case['expected_codes'])
