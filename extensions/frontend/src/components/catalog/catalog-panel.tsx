"use client";
import {useEffect,useState} from 'react';
import {fetchJSON} from '@/lib/api';
import {useSessionState} from '@/lib/use-session-state';

type Row={message_code:string;title:string;business:string;message_type:string;purpose:string;spelling_check:string;title_en:string;contents_en:string;notes:string;added_date:string;status:string};
type Step={name:string;passed?:boolean;results_count?:number;duration_ms?:number};
type Result={items:Row[];total:number;trace?:Step[]};
const fields: [keyof Row,string][]=[['business','업무구분'],['message_type','타입'],['message_code','메시지코드'],['purpose','용도'],['title','title'],['spelling_check','맞춤법검사'],['title_en','영문 title'],['contents_en','영문 contents'],['notes','비고'],['added_date','추가날짜']];
export function CatalogPanel({search=false}:{search?:boolean}){
 const prefix=search?'catalog-search':'catalog-documents';
 const [namespace,setNamespace]=useSessionState(prefix+':namespace','demo'),[query,setQuery]=useSessionState(prefix+':query',''),[data,setData]=useSessionState<Result|null>(prefix+':result',null),[error,setError]=useSessionState(prefix+':error',''),[pending,setPending]=useSessionState<number|null>(prefix+':pending',null),[page,setPage]=useSessionState(prefix+':page',0),[detail,setDetail]=useSessionState<Row|null>(prefix+':detail',null);
 const busy=pending!==null&&typeof window!=='undefined'&&pending===performance.timeOrigin;
 const setBusy=(value:boolean)=>setPending(value?performance.timeOrigin:null);
 const [status,setStatus]=useState<{index_ready:boolean;embedding:string}|null>(null);
 useEffect(()=>{let active=true;
 fetchJSON<{index_ready:boolean;embedding:string}>('/api/code-catalog/status',{params:{namespace}}).then(r=>{if(active)setStatus(r)}).catch(e=>{if(active)setError(String(e.message))});
 if(!search){setBusy(true);fetchJSON<Result>('/api/code-catalog/codes',{params:{namespace,status:'all',limit:30,offset:page*30,q:query}}).then(r=>{if(active)setData(r)}).catch(e=>{if(active)setError(String(e.message))}).finally(()=>{if(active)setBusy(false)});}
 return()=>{active=false};
 },[namespace,page,search,search?'':query]);
 async function run(){setBusy(true);setError('');setData(null);try{setData(await fetchJSON<Result>('/api/code-catalog/search-test',{method:'POST',body:{namespace,query}}));}catch(e){setError(e instanceof Error?e.message:'검색 실패');}finally{setBusy(false)}}
 return <section className="space-y-4 rounded-lg border p-4" aria-label={search?'알림 DB 검색 테스트':'알림 DB 관리'}>
 <h3 className="text-lg font-semibold">{search?'알림 DB 검색 테스트':'알림 DB 카탈로그'}</h3>
 <p className="text-sm text-muted-foreground">PostgreSQL에 저장된 알림 데이터를 사용합니다. DB 샘플은 합성 자료이며 실제 등록 목록과 분리됩니다.</p>
 <div className="flex flex-wrap items-center gap-3">
 <label>목록 <select aria-label="알림 데이터 목록" disabled={busy} className="rounded border p-2" value={namespace} onChange={e=>{setNamespace(e.target.value);setPage(0);setData(null);setDetail(null);setError('')}}><option value="demo">DB 샘플</option><option value="production">실제 등록 목록</option></select></label>
 <span className="text-sm">{status?(status.index_ready?'검색 준비됨':'검색 준비 필요'):'상태 확인 중'}</span>
 <a className="underline text-sm" href="/settings/reranking">공통 리랭킹 설정</a><a className="underline text-sm" href="/codes">알림 관리·검색 준비</a>
 </div>
 <form className="flex gap-2" onSubmit={e=>{e.preventDefault();if(search)void run()}}>
 <input aria-label={search?'알림 검색 질문':'알림 DB 목록 검색'} className="min-w-0 flex-1 rounded border p-2" value={query} onChange={e=>{setQuery(e.target.value);setPage(0)}} placeholder={search?'예: 인증번호 전송 성공':'업무·코드·문구 검색'} disabled={busy&&search}/>
 {search&&<button className="rounded border px-4" disabled={busy||!query.trim()}>{busy?'검색 중…':'알림 검색'}</button>}
 </form>
 {error&&<p role="alert" className="text-red-700">{error}</p>}
 {data&&<><p>{search?'검색 결과':'전체'} {data.total}건</p>
 <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['메시지코드','업무구분','타입','title','용도','상태'].map(v=><th className="p-2 whitespace-nowrap" key={v}>{v}</th>)}</tr></thead><tbody>{data.items.map(r=><tr className="border-t" key={r.message_code}><td className="p-2"><button className="underline whitespace-nowrap" onClick={()=>setDetail(r)}>{r.message_code}</button></td><td className="p-2">{r.business}</td><td className="p-2">{r.message_type}</td><td className="p-2 min-w-64">{r.title}</td><td className="p-2">{r.purpose}</td><td className="p-2 whitespace-nowrap">{r.status==='retired'?'폐기':'사용 중'}</td></tr>)}</tbody></table></div>
 {!search&&<div className="flex gap-4"><button disabled={page===0||busy} onClick={()=>setPage(p=>p-1)}>이전</button><span>{page+1} 페이지</span><button disabled={(page+1)*30>=data.total||busy} onClick={()=>setPage(p=>p+1)}>다음</button></div>}
 {data.trace&&<div><h4 className="font-semibold">실제 검색 실행 단계</h4><ul>{data.trace.map((s,i)=><li key={i}>{s.name} · {s.passed===false?'실패':'완료'}{s.results_count!=null?` · ${s.results_count}건`:''}{s.duration_ms!=null?` · ${s.duration_ms}ms`:''}</li>)}</ul></div>}</>}
 {detail&&<section className="rounded border p-4 space-y-2" aria-label="알림 DB 상세"><div className="flex justify-between"><h4>{detail.message_code}</h4><button onClick={()=>setDetail(null)}>상세 닫기</button></div><dl>{fields.map(([key,label])=><div className="grid grid-cols-[120px_1fr] gap-3 py-1" key={key}><dt>{label}</dt><dd className="whitespace-pre-wrap break-words">{detail[key]||'—'}</dd></div>)}</dl></section>}
 </section>;
}
