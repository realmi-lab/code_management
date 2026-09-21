import fs from 'node:fs';
for(const path of ['src/app/monitoring/page.tsx','src/app/monitoring/traces/page.tsx']){
 let s=fs.readFileSync(path,'utf8');if(s.includes('traceDate'))throw new Error('Already patched monitoring');
 if(!s.includes('trace.created_at')||!s.includes('trace.total_duration_ms'))throw new Error('Pinned monitoring contract changed');
 s=s.replace('"use client";','"use client";\nimport {traceDate,traceDuration,traceLabel,traceVariant} from "@/lib/trace-display";');
 s=s.replaceAll('new Date(trace.created_at).toLocaleTimeString("ko-KR")','traceDate(trace.created_at,true)').replaceAll('new Date(trace.created_at).toLocaleString("ko-KR")','traceDate(trace.created_at)');
 s=s.replaceAll('{(trace.total_duration_ms / 1000).toFixed(2)}s','{traceDuration(trace.total_duration_ms)}').replaceAll('trace.status === "success" ? "default" : "destructive"','traceVariant(trace.status)').replaceAll('trace.status === "success" ? "성공" : "오류"','traceLabel(trace.status)');
 s=s.replaceAll('trace.total_duration_ms > 0','trace.total_duration_ms != null && trace.total_duration_ms > 0').replaceAll('span.duration_ms / trace.total_duration_ms','(span.duration_ms ?? 0) / trace.total_duration_ms').replaceAll('{span.duration_ms}ms','{traceDuration(span.duration_ms)}');
 fs.writeFileSync(path,s);
}
const path='src/types/index.ts';let s=fs.readFileSync(path,'utf8');
const start=s.indexOf('export interface TraceSpan {'),end=s.indexOf('export interface CostEntry {');if(start<0||end<0)throw new Error('Pinned trace type contract changed');
let chunk=s.slice(start,end).replaceAll('duration_ms: number','duration_ms: number | null').replace('status: "success" | "error"','status: "success" | "error" | "unknown"').replace('created_at: string','created_at: string | null');
s=s.slice(0,start)+chunk+s.slice(end);fs.writeFileSync(path,s);

for(const path of ['src/app/monitoring/page.tsx','src/app/monitoring/metrics/page.tsx']){
 let s=fs.readFileSync(path,'utf8');s=s.replaceAll('오늘 쿼리 수','오늘 트레이스 수').replaceAll('오늘 쿼리','오늘 트레이스');fs.writeFileSync(path,s);
}
const list='src/app/monitoring/traces/page.tsx';let page=fs.readFileSync(list,'utf8');
const marker='      {/* Total count */}';if(page.split(marker).length!==2)throw new Error('Pinned trace pagination UI contract changed');
page=page.replace(marker,`      <div className="flex items-center gap-4">
        <Button variant="outline" disabled={isLoading || (params.page ?? 1) <= 1} onClick={() => setParams(p => ({...p,page:(p.page ?? 1)-1}))}>이전</Button>
        <span>{params.page ?? 1} 페이지</span>
        <Button variant="outline" disabled={isLoading || (params.page ?? 1)*(params.size ?? 20) >= (data?.total ?? 0)} onClick={() => setParams(p => ({...p,page:(p.page ?? 1)+1}))}>다음</Button>
      </div>
`+marker);fs.writeFileSync(list,page);
