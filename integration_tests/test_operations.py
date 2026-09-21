import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from code_agent.operations import RedisQuota, SearchCache, turn_trace, TrackedLLM
from code_agent.store import DomainError


@pytest.mark.asyncio
async def test_quota_uses_authenticated_actor_and_atomic_redis(monkeypatch):
    from test_upstream_adapter import module
    redis=SimpleNamespace(eval=AsyncMock(return_value=31))
    module(monkeypatch,'app.redis',get_redis=AsyncMock(return_value=redis))
    with pytest.raises(DomainError) as err:await RedisQuota().check(123,'turn')
    assert err.value.status==429
    args=redis.eval.await_args.args
    assert args[1]==1 and args[2].startswith('cm:quota:123:turn:') and args[3]==90


@pytest.mark.asyncio
async def test_quota_outage_fails_closed(monkeypatch):
    from test_upstream_adapter import module
    module(monkeypatch,'app.redis',get_redis=AsyncMock(side_effect=OSError('down')))
    with pytest.raises(DomainError) as err:await RedisQuota().check(123,'turn')
    assert err.value.status==503


@pytest.mark.asyncio
async def test_cache_keeps_only_references_and_versions_in_key(monkeypatch):
    from test_upstream_adapter import module
    redis=SimpleNamespace(setex=AsyncMock(),get=AsyncMock(return_value='invalid json'))
    module(monkeypatch,'app.redis',get_redis=AsyncMock(return_value=redis))
    cache=SearchCache();state={'version':1,'snapshot':'a','indexed_model':'m'}
    key=cache.key('private query',state,{'x':1})
    assert 'private' not in key
    assert key!=cache.key('private query',dict(state,version=2),{'x':1})
    assert key!=cache.key('private query',state,{'x':2})
    await cache.put(key,[{'code':'AT-1','revision':2,'message':'private message'}])
    assert json.loads(redis.setex.await_args.args[2])==[{'code':'AT-1','revision':2}]
    assert await cache.get(key) is None


@pytest.mark.asyncio
async def test_telemetry_has_no_prompt_or_answer():
    events=[]
    class Span:
        def start_span(self,**kw):return self
        def update(self,**kw):events.append(kw)
        def end(self):pass
    class Monitor:
        def create_trace(self,*args):events.append(args);return Span()
    llm=SimpleNamespace(generate=AsyncMock(return_value='private answer'),model='test-model',last_usage={'total_tokens':10})
    with turn_trace(Monitor(),123,'thread','request'):
        assert await TrackedLLM(llm,'Explanation').generate('private question')=='private answer'
    assert 'private' not in str(events)
    assert 'total_tokens' in str(events)
