"""Bounded CPU inference without dropping candidates or orphaning timed-out jobs."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import os
from weakref import WeakKeyDictionary

_executor = None
_gates = WeakKeyDictionary()


def _init_worker():
    # Torch otherwise competes with itself and the local embedding service on
    # every available virtual CPU. This changes execution, not ranking inputs.
    import torch
    torch.set_num_threads(max(1, min(4, int(os.getenv('CODE_RERANK_THREADS', '2')))))


async def run_rerank(base, query, documents, top_k, options):
    global _executor
    loop = asyncio.get_running_loop()
    gate = _gates.setdefault(loop, asyncio.BoundedSemaphore(1))
    await gate.acquire()
    try:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, initializer=_init_worker,
                                           thread_name_prefix='catalog-rerank')
        context = copy_context()
        future = _executor.submit(context.run, lambda: asyncio.run(
            base.rerank(query, documents, top_k=top_k, **options)))
    except BaseException:
        gate.release()
        raise

    def release_when_finished(_):
        # Cancelling an await cannot stop an active PyTorch call. Keep the gate
        # until the actual job ends, so subsequent turns cannot pile up work.
        try:
            loop.call_soon_threadsafe(gate.release)
        except RuntimeError:
            pass  # The app loop already shut down; this gate cannot be reused.

    future.add_done_callback(release_when_finished)
    return await asyncio.wrap_future(future)
