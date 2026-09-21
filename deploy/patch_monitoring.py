from pathlib import Path
import sys,ast
root=Path(sys.argv[1]);p=root/'app/api/monitoring.py';s=p.read_text()
for old,new in [
 ('    items = traces.get("data", [])','    from code_agent.monitoring import normalize_trace\n    items = [normalize_trace(t) for t in traces.get("data", [])]'),
 ('    return trace\n','    from code_agent.monitoring import normalize_trace\n    return normalize_trace(trace)\n')]:
 if s.count(old)!=1:raise RuntimeError('Pinned monitoring contract changed')
 s=s.replace(old,new)
for old,new in [
 ('from fastapi import APIRouter, Depends, Request','from fastapi import APIRouter, Depends, Request, Query'),
 ('async def list_traces(_admin: User = Depends(require_admin)):', 'async def list_traces(page: int = Query(1,ge=1), size: int = Query(20,ge=1,le=100), _admin: User = Depends(require_admin)):'),
 ('params={"limit": 50}', 'params={"limit": size, "page": page}'),
 ('return TraceListResponse(items=items, total=len(items))', 'return TraceListResponse(items=items, total=traces.get("meta", {}).get("totalItems", len(items)))')]:
 if s.count(old)!=1:raise RuntimeError('Pinned monitoring pagination contract changed')
 s=s.replace(old,new)
start=s.index('async def _get_langfuse_query_stats()')
# This is the last upstream function; pin its old ending before replacing it.
if not s[start:].rstrip().endswith('return 0, 0.0'):raise RuntimeError('Pinned stats contract changed')
s=s[:start]+'''async def _get_langfuse_query_stats() -> tuple[int,float]:
    from code_agent.monitoring import daily_trace_stats
    return await daily_trace_stats(_langfuse_api_get)
'''
ast.parse(s);p.write_text(s)
