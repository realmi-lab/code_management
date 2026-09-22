"""Read-only demo retrieval audit; never creates an LLM or mutates search settings.

Run on the host with --container to use the deployed retrieval modules. The
default stops at the reranker input: it does not load another cross encoder or
compete with a running answer benchmark. JSON goes to stdout for explicit saving.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request


def stage_report(expected, stages):
    """Separate a retrieval miss from later candidate loss; keep rank evidence."""
    ranks = {name: {code: codes.index(code) + 1 if code in codes else None
                    for code in expected} for name, codes in stages.items()}
    missing = {}
    for code in expected:
        if code not in stages['vector'] and code not in stages['keyword']:
            missing[code] = 'candidate_collection'
        else:
            missing[code] = next((name for name in ('rrf', 'reranker_input', 'reranked', 'api_search')
                                  if name in stages and code not in stages[name]), None)
    return {'expected_ranks': ranks, 'first_loss': missing}


def length_summary(values):
    ordered = sorted(values)
    return {'count': len(ordered), 'min': min(ordered, default=0),
            'median': ordered[len(ordered) // 2] if ordered else 0,
            'max': max(ordered, default=0), 'over_512_characters': sum(n > 512 for n in ordered)}


def summarize_cases(cases):
    stages = sorted({name for case in cases for name in case['expected_ranks']})
    report = {}
    for stage in stages:
        labeled = [case for case in cases if case['expected_codes'] and stage in case['expected_ranks']]
        ranks = [rank for case in labeled for rank in case['expected_ranks'][stage].values()]
        report[stage] = {'labeled_cases': len(labeled), 'expected_count': len(ranks),
                         'recall': sum(rank is not None for rank in ranks) / len(ranks) if ranks else None,
                         'recall_at_1': sum(rank == 1 for rank in ranks) / len(ranks) if ranks else None,
                         'recall_at_5': sum(rank is not None and rank <= 5 for rank in ranks) / len(ranks) if ranks else None}
    return report


def add_api_search(report, specs):
    """At most five sequential demo diagnostic searches; this endpoint has no answer LLM."""
    if len(specs) > 5:
        raise ValueError('API diagnostic search is limited to five cases per invocation')
    if report['reranker_executed']:
        raise ValueError('Do not execute both a duplicate local reranker and the API reranker')
    report['raw_reranker_executed'] = report['reranker_executed']
    report['cache'] = 'Raw audit bypasses cache; API search uses existing service cache (inspect each trace)'
    report['latency_boundary'] = 'Uncontrolled live load; not an isolated latency benchmark'
    by_id = {case['id']: case for case in report['cases']}
    for spec in specs:
        started = time.monotonic()
        print('audit API search started: ' + spec['id'], file=sys.stderr, flush=True)
        request = urllib.request.Request('http://127.0.0.1:8010/api/code-catalog/search-test',
            data=json.dumps({'namespace': 'demo', 'query': spec['query']}, ensure_ascii=False).encode(),
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=170) as response:
                result = json.load(response)
            case = by_id[spec['id']]
            case['stages']['api_search'] = [row['code'] for row in result['items']]
            case.update(stage_report(case['expected_codes'], case['stages']))
            case['api_seconds'] = round(time.monotonic() - started, 3)
            case['api_trace'] = result['trace']
            print('audit API search completed: ' + spec['id'], file=sys.stderr, flush=True)
        except (urllib.error.URLError, TimeoutError) as exc:
            by_id[spec['id']]['api_error'] = {'type': type(exc).__name__, 'status': getattr(exc, 'code', None)}
            print('audit API search stopped: ' + spec['id'] + ' ' + type(exc).__name__, file=sys.stderr, flush=True)
            # Stop instead of piling up requests after a timeout or server error.
            break
    report['api_search_stage'] = 'gateway output after reranking and waiting-condition ordering; inspect trace for cache or reranker failure'
    report['api_reranker_executed_cases'] = sum(any(step.get('name') == 'reranking' and step.get('passed')
        for step in case.get('api_trace', [])) for case in report['cases'])
    report['reranker_executed'] = bool(report['api_reranker_executed_cases'])
    report['summary'] = summarize_cases(report['cases'])
    return report


async def audit(spec):
    # Imports stay inside the explicit entry point; tests/imports make no calls.
    audit_started = time.monotonic()
    import httpx
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.config import get_settings
    from app.services.settings import SettingsService
    from app.services.search.vector import VectorSearchEngine
    from app.services.search.keyword_es import ElasticsearchNoriEngine
    from app.services.search.rrf import RRFCombiner
    from code_agent.embeddings import LocalEmbedding, local_enabled
    from code_agent.gateway import catalog_index, index_identity
    from code_agent.indexer import text_for
    from code_agent.safety import CatalogSafety
    from code_agent.store import Store, SampleStore
    imports_seconds = round(time.monotonic() - audit_started, 3)

    if not local_enabled():
        raise RuntimeError('Audit permits local embeddings only; no provider calls allowed')
    env = get_settings()
    engine = create_async_engine(env.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        settings = await SettingsService(db=session).get_settings()
    if settings.search_mode != 'hybrid' or settings.hyde_enabled or settings.multi_query_enabled:
        raise RuntimeError('Audit requires the existing single-query hybrid configuration; settings were not changed')
    base_store = Store(env.database_url)
    store = SampleStore(base_store)
    state, rows = store.snapshot()
    if state['version'] != state['indexed_version'] or state['indexed_model'] != index_identity(settings.embedding_model):
        raise RuntimeError('Snapshot is stale; audit refuses reindexing')
    snapshot = state['snapshot']
    records = {row['code']: row for row in rows}
    safety = CatalogSafety()
    with store.engine.connect() as conn:
        indexed = [dict(row) for row in conn.execute(text(
            'SELECT id, content, metadata FROM cm_search_chunks WHERE document_id=:snapshot'),
            {'snapshot': snapshot}).mappings()]
        production_count = conn.execute(text('SELECT count(*) FROM cm_codes')).scalar_one()
        sample_count = conn.execute(text('SELECT count(*) FROM cm_sample_codes')).scalar_one()
    async with httpx.AsyncClient(base_url=env.elasticsearch_url, timeout=30) as client:
        response = await client.post('/' + catalog_index('demo') + '/_search', json={
            'size': 10000, 'query': {'term': {'document_id': snapshot}}})
        response.raise_for_status()
        es_rows = [hit['_source'] for hit in response.json()['hits']['hits']]
        mapping_response = await client.get('/' + catalog_index('demo') + '/_settings')
        mapping_response.raise_for_status()
        analysis = mapping_response.json()[catalog_index('demo')]['settings']['index'].get('analysis')
    pg_by_id = {str(row['id']): row for row in indexed}
    es_by_id = {str(row['chunk_id']): row for row in es_rows}
    by_code = Counter(row['metadata'].get('code') for row in indexed)
    index_checks = {
        'active_codes_equal_indexed_codes': set(by_code) == set(records),
        'exactly_one_chunk_per_active_row': all(count == 1 for count in by_code.values()),
        'pg_es_chunk_ids_equal': set(pg_by_id) == set(es_by_id),
        'pg_es_content_metadata_equal': all(ident in es_by_id and row['content'] == es_by_id[ident]['content']
            and row['metadata'] == es_by_id[ident]['metadata'] for ident, row in pg_by_id.items()),
        'index_content_equals_redacted_row': all(row['metadata'].get('code') in records and
            row['content'] == safety.redact(text_for(records[row['metadata']['code']])) for row in indexed),
        'indexed_revision_matches_db': all(row['metadata'].get('code') in records and
            row['metadata'].get('revision') == records[row['metadata']['code']]['revision'] for row in indexed),
    }

    class CatalogVector(VectorSearchEngine):
        # Same bound snapshot query as the deployed gateway; no unscoped search.
        _FILTERED_SQL = text('SELECT id AS chunk_id, document_id, content, embedding <=> CAST(:query_embedding AS vector) AS distance, metadata FROM cm_search_chunks WHERE document_id = :doc_id AND embedding IS NOT NULL ORDER BY distance ASC LIMIT :top_k')

    embedder = LocalEmbedding(model=settings.embedding_model, dimensions=1536)
    keyword = ElasticsearchNoriEngine(es_url=env.elasticsearch_url, index_name=catalog_index('demo'))
    vector = CatalogVector(sessions)
    rrf = RRFCombiner()
    reranker = None
    if spec.get('rerank'):
        from app.services.reranking.korean import KoreanCrossEncoder
        from code_agent.gateway import CatalogReranker
        reranker = CatalogReranker(KoreanCrossEncoder())
    cases = []
    setup_seconds = round(time.monotonic() - audit_started, 3)
    try:
        for case in spec['cases']:
            started = time.monotonic()
            query = safety.redact(case['query'])
            embedding = await embedder.embed_query(query)
            embedded_at = time.monotonic()
            vec, kw = await asyncio.gather(vector.search(embedding, settings.retriever_top_k, snapshot),
                                           keyword.search(query, settings.retriever_top_k, snapshot))
            retrieved_at = time.monotonic()
            fused = rrf.combine(vec, kw, k=settings.rrf_constant,
                                vector_weight=settings.vector_weight, keyword_weight=settings.keyword_weight)
            # Every catalog chunk has the same snapshot document_id, so document
            # scope selection cannot eliminate one row in this namespace.
            incoming = fused[:settings.reranker_top_k * 4]
            docs = {'vector': vec, 'keyword': kw, 'rrf': fused, 'reranker_input': incoming}
            if reranker is not None:
                docs['reranked'] = await reranker.rerank(query, incoming, top_k=settings.reranker_top_k,
                    score_mode=settings.reranker_score_mode, alpha=settings.reranker_alpha)
            stages = {name: [doc.metadata['code'] for doc in values] for name, values in docs.items()}
            cases.append({'id': case['id'], 'suite': case['suite'], 'expected_codes': case['expected_codes'],
                          'stages': stages, **stage_report(case['expected_codes'], stages),
                          'embedding_seconds': round(embedded_at - started, 3),
                          'pg_es_seconds': round(retrieved_at - embedded_at, 3),
                          'seconds': round(time.monotonic() - started, 3)})
            print('audit raw search completed: ' + case['id'], file=sys.stderr, flush=True)
    finally:
        await embedder.client.close()
        await keyword.close()
        await engine.dispose()
        base_store.engine.dispose()
    after_state = store.status()
    base_store.engine.dispose()
    if after_state['version'] != state['version']:
        raise RuntimeError('Catalog changed during audit; discard this run')
    return {'scope': 'demo synthetic only', 'llm_calls': 0,
            'imports_seconds': imports_seconds, 'setup_seconds': setup_seconds,
            'reranker_executed': reranker is not None, 'cache': 'not read or written',
            'catalog_version': state['version'], 'snapshot': snapshot,
            'production_count': production_count, 'sample_count': sample_count,
            'active_count': len(rows), 'pg_chunks': len(indexed), 'es_chunks': len(es_rows),
            'index_checks': index_checks, 'nori_analysis': analysis,
            'settings': {key: getattr(settings, key) for key in ('search_mode', 'retriever_top_k',
                'reranker_top_k', 'reranker_score_mode', 'reranker_alpha', 'rrf_constant', 'vector_weight',
                'keyword_weight', 'document_scope_enabled', 'chunk_size', 'chunk_overlap', 'chunking_strategy')},
            'rerank_input_policy': 'original indexed chunks; upstream candidate cap is reranker_top_k * 4',
            'index_characters': length_summary([len(row['content']) for row in indexed]),
            'rerank_characters': length_summary([len(row['content']) for row in indexed]),
            'truncated_rerank_codes': [row['metadata']['code'] for row in indexed if len(row['content']) > 512],
            'cases': cases, 'summary': summarize_cases(cases)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container')
    parser.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--rerank', action='store_true', help='Explicitly load a local cross encoder; may compete for CPU')
    parser.add_argument('--api-search', action='store_true', help='After raw audit, issue at most five sequential demo search-test requests')
    args = parser.parse_args()
    if args.inside:
        spec = json.load(sys.stdin)
    else:
        manifest_path = args.manifest or Path(__file__).resolve().parents[1] / 'docs/verification/catalog-skills-2026-09-22/manifest.json'
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('scope') != 'demo synthetic only' or not manifest.get('frozen'):
            raise ValueError('A frozen synthetic demo manifest is required')
        cases = [case for case in manifest['cases'] if case['kind'] == 'search']
        spec = {'cases': cases[:args.limit] if args.limit else cases, 'rerank': args.rerank}
    if args.container:
        if args.api_search and (len(spec['cases']) > 5 or args.rerank):
            raise ValueError('Use at most five cases and no --rerank with --api-search')
        completed = subprocess.run(['docker', 'exec', '-i', args.container, 'python', '-c',
            Path(__file__).read_text(), '--inside'], input=json.dumps(spec), text=True, check=False,
            stdout=subprocess.PIPE if args.api_search else None)
        if args.api_search and completed.returncode == 0:
            report = add_api_search(json.loads(completed.stdout), spec['cases'])
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return completed.returncode
    if args.api_search:
        raise ValueError('--api-search requires the host --container entry point')
    print(json.dumps(asyncio.run(audit(spec)), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
