"""Normalize Langfuse public trace payloads without inventing success or duration."""
import json,math
from datetime import datetime

def obj(value):
    if isinstance(value,dict):return value
    if isinstance(value,str):
        try:
            parsed=json.loads(value)
            return parsed if isinstance(parsed,dict) else {}
        except (ValueError,TypeError):pass
    return {}

def number(value):
    if isinstance(value,bool):return None
    try:
        v=float(value)
        return v if math.isfinite(v) and v>=0 else None
    except (TypeError,ValueError):return None

def stamp(value):
    if not isinstance(value,str):return None
    try:datetime.fromisoformat(value.replace('Z','+00:00'));return value
    except ValueError:return None

def normalize_trace(raw):
    output=obj(raw.get('output'));input_value=raw.get('input');inputs=obj(input_value)
    query=raw.get('query') or inputs.get('query') or inputs.get('question')
    if not isinstance(query,str):query=None
    if not query and isinstance(input_value,str) and not inputs:query=input_value
    if not query:query='알림 코드 대화 · 질문 원문 미저장' if raw.get('name')=='catalog-turn' else raw.get('name') or '질문 정보 없음'
    duration=number(raw.get('total_duration_ms'))
    if duration is None:duration=number(output.get('duration_ms'))
    if duration is None:
        latency=number(raw.get('latency'));duration=latency*1000 if latency is not None else None
    status=str(output.get('status') or raw.get('status') or '').lower()
    status='success' if status in ('success','completed') else 'error' if status in ('error','failed') or raw.get('level')=='ERROR' else 'unknown'
    spans=[]
    for span in raw.get('observations') or []:
        if not isinstance(span,dict):continue
        ms=None;start=stamp(span.get('startTime'));end=stamp(span.get('endTime'))
        if start and end:
            try:ms=number((datetime.fromisoformat(end.replace('Z','+00:00'))-datetime.fromisoformat(start.replace('Z','+00:00'))).total_seconds()*1000)
            except TypeError:pass
        spans.append({'name':span.get('name') or span.get('type') or '단계','duration_ms':ms,'status':'error' if span.get('level')=='ERROR' else 'unknown'})
    return {'id':raw.get('id',''),'query':query,'created_at':stamp(raw.get('timestamp')) or stamp(raw.get('created_at')) or stamp(raw.get('createdAt')),'total_duration_ms':duration,'status':status,'spans':spans}

async def daily_trace_stats(fetch,now=None):
    """Aggregate today's actual traces; provider limit is 100, not 1000."""
    from datetime import timezone,timedelta
    from zoneinfo import ZoneInfo
    import os
    zone=ZoneInfo(os.getenv('CODE_MONITORING_TIMEZONE','Asia/Seoul'))
    now=now or datetime.now(timezone.utc)
    start=now.astimezone(zone).replace(hour=0,minute=0,second=0,microsecond=0)
    end=start+timedelta(days=1)
    params={'limit':100,'page':1,'fromTimestamp':start.isoformat(),'toTimestamp':end.isoformat()}
    count=0;durations=[]
    while True:
        response=await fetch('/api/public/traces',params=params)
        if response is None:return 0,0.0
        rows=response.get('data',[])
        for raw in rows:
            row=normalize_trace(raw);created=row['created_at']
            if not created:continue
            at=datetime.fromisoformat(created.replace('Z','+00:00'))
            if at.tzinfo is None:at=at.replace(tzinfo=timezone.utc)
            if not start<=at<end:continue
            count+=1
            if row['total_duration_ms'] is not None:durations.append(row['total_duration_ms'])
        pages=response.get('meta',{}).get('totalPages',1)
        if not rows or params['page']>=pages:break
        params['page']+=1
    return count,round(sum(durations)/len(durations),2) if durations else 0.0
