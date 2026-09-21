from code_agent.monitoring import normalize_trace,daily_trace_stats

def test_actual_langfuse_fields_and_units():
 r=normalize_trace({'id':'a','timestamp':'2026-09-21T02:57:16.440Z','input':'인증번호 전송 성공','latency':25.989})
 assert r['query']=='인증번호 전송 성공' and r['total_duration_ms']==25989
 assert r['created_at']=='2026-09-21T02:57:16.440Z' and r['status']=='unknown'

def test_catalog_failure_and_private_input():
 r=normalize_trace({'name':'catalog-turn','input':{'actor_hash':'private','thread':'id'},'output':{'status':'failed','duration_ms':0},'latency':5})
 assert r['status']=='error' and r['total_duration_ms']==0 and 'private' not in str(r)

def test_missing_malformed_data_never_fabricates_success():
 for value in (None,'bad',float('nan'),-1):
  r=normalize_trace({'timestamp':'invalid','latency':value})
  assert r['created_at'] is None and r['total_duration_ms'] is None and r['status']=='unknown'

def test_detail_span_conversion_and_success():
 r=normalize_trace({'output':{'status':'success'},'observations':['id',{'name':'search','startTime':'2026-09-21T00:00:00Z','endTime':'2026-09-21T00:00:02Z'}]})
 assert r['status']=='success' and r['spans'][0]['duration_ms']==2000

import pytest
from datetime import datetime,timezone
@pytest.mark.asyncio
async def test_today_statistics_paginates_and_averages_only_valid_today_values():
    calls=[]
    async def fetch(path,params):
        calls.append(dict(params))
        if params['page']==1:return {'data':[{'timestamp':'2026-09-20T15:00:00Z','latency':2},{'timestamp':'2026-09-20T14:59:59Z','latency':999}], 'meta':{'totalPages':2}}
        return {'data':[{'timestamp':'2026-09-21T03:00:00Z','latency':4},{'timestamp':'2026-09-21T02:00:00Z','latency':None}], 'meta':{'totalPages':2}}
    count,avg=await daily_trace_stats(fetch,datetime(2026,9,21,4,tzinfo=timezone.utc))
    assert count==3 and avg==3000
    assert len(calls)==2 and all(c['limit']==100 for c in calls)
    assert calls[0]['fromTimestamp']=='2026-09-21T00:00:00+09:00'
