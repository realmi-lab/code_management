"""Real worker cancellation tests, with no Torch or neural model initialization."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import threading
from types import SimpleNamespace
from weakref import WeakKeyDictionary

import pytest

from code_agent import rerank_runtime as runtime


@pytest.fixture
def worker_runtime(monkeypatch):
    pools = []
    initializer_threads = []

    class ObservedPool(ThreadPoolExecutor):
        def __init__(self, *args, **kwargs):
            self.submissions = []
            super().__init__(*args, **kwargs)
            pools.append(self)

        def submit(self, *args, **kwargs):
            self.submissions.append((args, kwargs))
            return super().submit(*args, **kwargs)

    monkeypatch.setattr(runtime, '_executor', None)
    monkeypatch.setattr(runtime, '_gates', WeakKeyDictionary())
    monkeypatch.setattr(runtime, '_init_worker', lambda: initializer_threads.append(threading.get_ident()))
    monkeypatch.setattr(runtime, 'ThreadPoolExecutor', ObservedPool)
    yield SimpleNamespace(pools=pools, initializer_threads=initializer_threads, pool_type=ObservedPool)
    for pool in pools:
        # Test jobs have bounded waits and every blocking test releases them in finally.
        pool.shutdown(wait=True, cancel_futures=True)


async def wait_started(event):
    observed = await asyncio.wait_for(asyncio.to_thread(event.wait, 5), timeout=7)
    assert observed, 'The actual worker did not start before the test deadline'


async def clean_tasks(*tasks):
    for task in tasks:
        if task is not None and not task.done():
            task.cancel()
    await asyncio.gather(*(task for task in tasks if task is not None), return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_await_keeps_gate_until_real_worker_finishes(worker_runtime):
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    next_started = threading.Event()
    order = []

    class BlockingBase:
        async def rerank(self, query, documents, **options):
            if query == 'first':
                order.append('first-start')
                started.set()
                try:
                    if not release.wait(5):
                        raise TimeoutError('Test worker was not released')
                    return documents
                finally:
                    order.append('first-finished')
                    finished.set()
            next_started.set()
            order.append('next-start')
            assert finished.is_set(), 'The next inference overlapped the cancelled request'
            return documents

    base = BlockingBase()
    first = asyncio.create_task(runtime.run_rerank(base, 'first', ['first'], 1, {}))
    second = None
    try:
        await wait_started(started)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(runtime.run_rerank(base, 'next', ['second'], 1, {}))
        await asyncio.sleep(0)  # Let the next caller reach the occupied gate.
        assert len(worker_runtime.pools[0].submissions) == 1
        assert not next_started.is_set()
        assert not second.done()
        release.set()
        assert await asyncio.wait_for(second, 5) == ['second']
        assert order == ['first-start', 'first-finished', 'next-start']
    finally:
        release.set()
        await clean_tasks(first, second)


@pytest.mark.asyncio
async def test_cancelling_waiter_never_submits_a_worker_job(worker_runtime):
    started = threading.Event()
    release = threading.Event()
    queries = []

    class BlockingBase:
        async def rerank(self, query, documents, **options):
            queries.append(query)
            if query == 'first':
                started.set()
                if not release.wait(5):
                    raise TimeoutError('Test worker was not released')
            return documents

    base = BlockingBase()
    first = asyncio.create_task(runtime.run_rerank(base, 'first', [1], 1, {}))
    waiting = None
    try:
        await wait_started(started)
        waiting = asyncio.create_task(runtime.run_rerank(base, 'cancel-before-start', [2], 1, {}))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert len(worker_runtime.pools[0].submissions) == 1
        release.set()
        assert await asyncio.wait_for(first, 5) == [1]
        assert await asyncio.wait_for(runtime.run_rerank(base, 'after', [3], 1, {}), 5) == [3]
        assert queries == ['first', 'after']
        assert len(worker_runtime.pools[0].submissions) == 2
    finally:
        release.set()
        await clean_tasks(first, waiting)


@pytest.mark.asyncio
async def test_worker_exception_releases_gate_for_next_request(worker_runtime):
    class FailingBase:
        async def rerank(self, query, documents, **options):
            if query == 'fail':
                raise ValueError('Synthetic inference failure')
            return documents

    base = FailingBase()
    with pytest.raises(ValueError, match='Synthetic inference failure'):
        await runtime.run_rerank(base, 'fail', [], 1, {})
    result = await asyncio.wait_for(runtime.run_rerank(base, 'recovered', ['kept'], 1, {}), 5)
    assert result == ['kept']
    assert len(worker_runtime.pools[0].submissions) == 2


@pytest.mark.asyncio
async def test_documents_top_k_options_and_context_are_forwarded_without_reduction(worker_runtime):
    correlation = ContextVar('synthetic-rerank-context')
    marker = object()
    documents = [object() for _ in range(57)]
    options = {'score_mode': 'calibrated', 'alpha': 0.17, 'custom': {'identity': marker}}
    observed = {}
    calling_thread = threading.get_ident()

    class RecordingBase:
        async def rerank(self, query, docs, top_k, **kwargs):
            observed.update(query=query, docs=docs, top_k=top_k, options=kwargs,
                            context=correlation.get(), worker_thread=threading.get_ident())
            return docs

    token = correlation.set('request-context')
    try:
        result = await runtime.run_rerank(RecordingBase(), 'original query', documents, 50, options)
    finally:
        correlation.reset(token)
    assert observed['docs'] is documents and result is documents
    assert len(result) == 57
    assert observed['query'] == 'original query' and observed['top_k'] == 50
    assert observed['options'] == options
    assert observed['options']['custom'] is options['custom']
    assert options['custom']['identity'] is marker
    assert observed['context'] == 'request-context'
    assert observed['worker_thread'] != calling_thread
    assert worker_runtime.initializer_threads == [observed['worker_thread']]


@pytest.mark.asyncio
async def test_submit_exception_releases_gate(worker_runtime, monkeypatch):
    async def rank(query, documents, **options):
        return documents

    base = SimpleNamespace(rerank=rank)
    await runtime.run_rerank(base, 'create-pool', [], 1, {})
    pool = worker_runtime.pools[0]
    original_submit = pool.submit

    def rejected_submit(*args, **kwargs):
        raise RuntimeError('Synthetic submit failure')

    monkeypatch.setattr(pool, 'submit', rejected_submit)
    with pytest.raises(RuntimeError, match='Synthetic submit failure'):
        await asyncio.wait_for(runtime.run_rerank(base, 'rejected', [], 1, {}), 5)
    monkeypatch.setattr(pool, 'submit', original_submit)
    assert await asyncio.wait_for(runtime.run_rerank(base, 'after', ['kept'], 1, {}), 5) == ['kept']


@pytest.mark.asyncio
async def test_executor_creation_exception_releases_gate(worker_runtime, monkeypatch):
    async def rank(query, documents, **options):
        return documents

    def failed_constructor(*args, **kwargs):
        raise RuntimeError('Synthetic executor creation failure')

    base = SimpleNamespace(rerank=rank)
    monkeypatch.setattr(runtime, 'ThreadPoolExecutor', failed_constructor)
    with pytest.raises(RuntimeError, match='Synthetic executor creation failure'):
        await runtime.run_rerank(base, 'rejected', [], 1, {})
    assert not runtime._gates[asyncio.get_running_loop()].locked()
    monkeypatch.setattr(runtime, 'ThreadPoolExecutor', worker_runtime.pool_type)
    assert await asyncio.wait_for(runtime.run_rerank(base, 'after', ['kept'], 1, {}), 5) == ['kept']
