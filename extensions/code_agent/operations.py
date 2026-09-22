"""Redis quotas/cache and content-free per-turn telemetry."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import time
import logging
from .store import DomainError

_validation_context=ContextVar('catalog_validation_context',default=None)
_active_trace=ContextVar('catalog_trace',default=None)
_active_timings=ContextVar('catalog_timings',default=None)
log=logging.getLogger(__name__)
SEARCH_POLICY=4  # Original indexed chunks replace catalogue-only text/window ranking.


def token_usage(value):
    """Provider-reported counts only. Missing usage is unknown, never zero or an estimate."""
    if not isinstance(value,dict):return None
    result={k:value[k] for k in ('prompt_tokens','completion_tokens','total_tokens','input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens')
            if type(value.get(k)) is int and value[k]>=0}
    for field,keys in (('prompt_tokens_details',('cached_tokens',)),('completion_tokens_details',('reasoning_tokens',))):
        detail=value.get(field)
        if isinstance(detail,dict):
            counts={k:detail[k] for k in keys if type(detail.get(k)) is int and detail[k]>=0}
            if counts:result[field]=counts
    return result or None


def observe(target,method,*args,**kwargs):
    """Telemetry outages must not fail or duplicate a completed user operation."""
    if target is None:return None
    try:return getattr(target,method)(*args,**kwargs)
    except Exception:return None


class RedisQuota:
    SCRIPT="local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n"
    async def check(self, actor_id, operation):
        limits={'turn':30,'review':10,'index':3,'import':10}
        try:
            from app.redis import get_redis
            redis=await get_redis()
            bucket=int(time.time())//60
            key=f'cm:quota:{actor_id}:{operation}:{bucket}'
            count=await redis.eval(self.SCRIPT,1,key,90)
        except Exception as exc:
            raise DomainError('요청 제한 서비스를 확인할 수 없어 처리를 중단했습니다.',503) from exc
        if count>limits[operation]:
            raise DomainError('분당 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.',429)


class SearchCache:
    def key(self, query, state, settings):
        raw=json.dumps({'query':query,'snapshot':state['snapshot'],'version':state['version'],
                        'model':state.get('indexed_model'),'settings':settings,'policy':SEARCH_POLICY},sort_keys=True,ensure_ascii=False)
        return 'cm:search:'+hashlib.sha256(raw.encode()).hexdigest()

    async def get(self,key):
        try:
            from app.redis import get_redis
            data=await (await get_redis()).get(key)
            return json.loads(data) if data else None
        except Exception:
            return None # Optional cache failure executes real retrieval, never a fake search.

    async def put(self,key,candidates):
        try:
            from app.redis import get_redis
            refs=[{'code':item['code'],'revision':item['revision']} for item in candidates]
            await (await get_redis()).setex(key,300,json.dumps(refs))
        except Exception:
            pass


@contextmanager
def turn_trace(monitor,actor_id,thread_id,request_id):
    trace=None
    if monitor:
        # Never put user text, DB records, tokens or raw actor IDs into telemetry.
        identity=hashlib.sha256(str(actor_id).encode()).hexdigest()[:16]
        trace=observe(monitor,'create_trace','catalog-turn',json.dumps({'actor_hash':identity,'thread':thread_id,'request':str(request_id)}))
    context_token=_validation_context.set({'thread_id':thread_id,'request_id':str(request_id)})
    token=_active_trace.set(trace)
    timings=[];timing_token=_active_timings.set(timings)
    start=time.monotonic()
    try:
        yield
        observe(trace,'update',output={'status':'success','duration_ms':round((time.monotonic()-start)*1000)})
    except BaseException as exc:
        observe(trace,'update',output={'status':'failed','error_type':type(exc).__name__})
        raise
    finally:
        log.info('catalog_turn_metrics %s',json.dumps({**(_validation_context.get() or {}),'duration_ms':round((time.monotonic()-start)*1000),'calls':timings}))
        _active_timings.reset(timing_token)
        _active_trace.reset(token)
        _validation_context.reset(context_token)
        observe(trace,'end')


class TrackedLLM:
    def __init__(self,llm,stage,skill=None):self.llm=llm;self.stage=stage;self.skill=skill
    def for_stage(self,suffix,llm=None):return TrackedLLM(llm or self.llm,self.stage+"/"+suffix,self.skill)
    @property
    def client(self):return self.llm.client
    async def generate(self,prompt,system_prompt=None):
        trace=_active_trace.get();span=observe(trace,'start_span',name='catalog-'+self.stage)
        llm=self.llm.fork() if callable(getattr(self.llm,'fork',None)) else self.llm
        start=time.monotonic();status='failed';usage=None;judge_detail=None
        try:
            result=await llm.generate(prompt,system_prompt=system_prompt)
            status='success';usage=token_usage(getattr(llm,'last_usage',None))
            detail=getattr(llm,'last_detail',None)
            # Counts distinguish deterministic comparison from actual Apple model calls. No claim text is logged.
            judge_detail={k:detail[k] for k in ('claims','supported','model_checked','model_calls')
                          if type(detail.get(k)) is int} if isinstance(detail,dict) else None
            observe(span,'update',output={'status':'success','model':getattr(llm,'model',None),
                'duration_ms':round((time.monotonic()-start)*1000),'usage':usage,
                **({'judge_detail':judge_detail} if judge_detail is not None else {})})
            return result
        except BaseException as exc:
            observe(span,'update',output={'status':'failed','error_type':type(exc).__name__})
            raise
        finally:
            timings=_active_timings.get()
            if timings is not None:timings.append({'stage':self.stage,'status':status,'model':getattr(llm,'model',None),
                **({'skill':self.skill} if self.skill else {}),
                'duration_ms':round((time.monotonic()-start)*1000),'usage':usage,
                'prompt_chars':len(prompt),'system_chars':len(system_prompt or ''),
                **({'judge_detail':judge_detail} if judge_detail is not None else {})})
            observe(span,'end')
