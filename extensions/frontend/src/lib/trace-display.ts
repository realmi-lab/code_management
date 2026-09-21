export function traceDate(value:string|null,timeOnly=false){
 if(!value)return '—';const date=new Date(value);if(!Number.isFinite(date.getTime()))return '—';
 return timeOnly?date.toLocaleTimeString('ko-KR'):date.toLocaleString('ko-KR');
}
export function traceDuration(value:number|null){return typeof value==='number'&&Number.isFinite(value)&&value>=0?`${(value/1000).toFixed(2)}s`:'—';}
export function traceLabel(value:string){return value==='success'?'성공':value==='error'?'오류':'미확인';}
export function traceVariant(value:string):'default'|'destructive'|'secondary'{return value==='success'?'default':value==='error'?'destructive':'secondary';}
