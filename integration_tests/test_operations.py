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
    monkeypatch.setattr('code_agent.operations.SEARCH_POLICY',2)
    assert key!=cache.key('private query',state,{'x':1})
    monkeypatch.setattr('code_agent.operations.SEARCH_POLICY',3)
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
    llm=SimpleNamespace(generate=AsyncMock(return_value='private answer'),model='test-model',last_usage={'total_tokens':10},
                        last_detail={'claims':5,'supported':5,'model_checked':0,'model_calls':0,'text':'private evidence'})
    with turn_trace(Monitor(),123,'thread','request'):
        assert await TrackedLLM(llm,'Explanation').generate('private question')=='private answer'
    assert 'private' not in str(events)
    assert 'total_tokens' in str(events)
    assert next(e['output']['judge_detail'] for e in events if isinstance(e,dict) and 'judge_detail' in e.get('output',{})) == {'claims':5,'supported':5,'model_checked':0,'model_calls':0}

def test_usage_whitelist_preserves_unknown_and_rejects_content():
    from code_agent.operations import token_usage
    assert token_usage(None) is None
    assert token_usage({'prompt_tokens':None,'private':'answer'}) is None
    assert token_usage({'total_tokens':False,'prompt_tokens':-1}) is None
    assert token_usage({'prompt_tokens':0,'completion_tokens_details':{'reasoning_tokens':7,'private':'secret'},'secret':'key'})=={'prompt_tokens':0,'completion_tokens_details':{'reasoning_tokens':7}}

@pytest.mark.asyncio
async def test_concurrent_calls_log_distinct_usage_without_text(caplog):
    import asyncio,logging
    from code_agent.operations import _active_timings
    class Forkable:
        model='synthetic-model'
        next=0
        def fork(self):
            self.next+=1
            return Child(self.next)
    class Child:
        model='synthetic-model'
        def __init__(self,number):self.number=number
        async def generate(self,prompt,system_prompt=None):
            self.last_usage={'prompt_tokens':self.number,'completion_tokens':2,'total_tokens':self.number+2}
            await asyncio.sleep(0.01)
            return 'PRIVATE ANSWER'
    with caplog.at_level(logging.INFO),turn_trace(None,1,'test-thread','test-request'):
        llm=TrackedLLM(Forkable(),'Explanation')
        await asyncio.gather(llm.for_stage('faithfulness').generate('PRIVATE INPUT'),llm.for_stage('grounding').generate('PRIVATE INPUT'))
    event=json.loads(next(r.message.split('catalog_turn_metrics ',1)[1] for r in caplog.records if r.message.startswith('catalog_turn_metrics ')))
    assert event['request_id']=='test-request' and event['thread_id']=='test-thread'
    assert sorted(c['usage']['total_tokens'] for c in event['calls'])==[3,4]
    assert 'PRIVATE' not in caplog.text
