'use strict';
/* Alert-code workspace. Runs inside the original app's iframe under a strict CSP
   (script-src/style-src 'self'): no inline handlers, no style attributes in markup.
   Every stored value is rendered with textContent, never as HTML. */

const $=(s,root=document)=>root.querySelector(s);
const $$=(s,root=document)=>Array.from(root.querySelectorAll(s));
const base='/api/code-catalog';
const COUNT_AT=3200;
const CATALOG_PAGE=30;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/* The API speaks in record verbs; the screen speaks to a planner. */
const AUDIT_ACTION={import_create:'코드 신규 등록',import_update:'코드 내용 변경',draft_create:'초안 생성',approve:'초안 등록 승인',revise:'코드 수정'};
const INSPECTION_MODE={exact_lookup:'코드번호 직접 조회',catalog_rules:'원문·규칙 비교 · AI 호출 없음',semantic:'의미 검색 후보 · 조건은 규칙 비교'};

let localMode=false,token=null,user=null;
let catalogNamespace='demo',inspectionGeneration=0;
let thread=null,selected=null,busy=false,pendingApproval=null;
let catalogQuery='',catalogStatus='all',catalogOffset=0,catalogRequest=0;
let aiSettings=null;
let leaving=false;

/* ------------------------------------------------------------------ session memory */
/* The shell remounts this iframe whenever the planner visits another screen. Work in
   flight lives on in the server; sessionStorage (per browser tab, per user) remembers
   enough to show it again on return. Never store credentials here. */
const RESUME_WINDOW=260000; // the server abandons a turn after 240 s
const NAMESPACES=['production','demo'];
function sessionKey(name){return 'code-workspace:v1:'+(user?user.id:'anon')+':'+name;}
function remember(name,value){
 if(!user)return;
 try{
  if(value===null||value===undefined)sessionStorage.removeItem(sessionKey(name));
  else sessionStorage.setItem(sessionKey(name),JSON.stringify(value));
 }catch{/* full or blocked storage: the screen still works, it just forgets */}
}
function recall(name){
 if(!user)return null;
 try{const raw=sessionStorage.getItem(sessionKey(name));return raw===null?null:JSON.parse(raw);}catch{return null;}
}
function rememberUi(patch){remember('ui',{...(recall('ui')||{}),...patch});}
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
window.addEventListener('pagehide',()=>{leaving=true;});

/* ------------------------------------------------------------------ dom helpers */

/** h('div','cls',child,'text',...) — strings become text nodes; null/undefined/false/0/''
    are skipped so `list.length&&node` reads naturally. Pass String(n) to render a number. */
function h(tag,cls,...children){
 const n=document.createElement(tag);
 if(cls)n.className=cls;
 for(const c of children.flat())if(c!==null&&c!==undefined&&c!==false&&c!==0&&c!=='')n.append(c);
 return n;
}
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function button(label,cls,onClick){
 const b=el('button',label,cls===undefined?'btn':cls);b.type='button';
 if(onClick)b.addEventListener('click',()=>Promise.resolve().then(()=>onClick(b)).catch(error));
 return b;
}
function bind(id,fn){$(id).addEventListener('click',()=>Promise.resolve().then(fn).catch(error));}
function metaRow(term,value){return h('div',null,el('dt',term),el('dd',value));}
function emptyState(title,body,cls,action){return h('div',cls||'list-empty',el('strong',title),el('p',body),action);}
function skeleton(rows){
 return h('div','skeleton-stack',Array.from({length:rows},()=>h('div','skeleton',el('div',undefined,'skeleton-line'),el('div',undefined,'skeleton-line'),el('div',undefined,'skeleton-line'))));
}
/* A skeleton that flashes for 80ms is worse than none: wait past the threshold first.
   isCurrent() lets a superseded request neither paint nor leave a skeleton behind. */
function withSkeleton(host,rows,run,isCurrent=()=>true){
 const timer=setTimeout(()=>{if(isCurrent())host.replaceChildren(skeleton(rows));},140);
 return Promise.resolve().then(run).catch(e=>{
  if(isCurrent()&&host.querySelector(':scope > .skeleton-stack'))host.replaceChildren();
  throw e;
 }).finally(()=>clearTimeout(timer));
}
function statusTag(status,code){
 const map={registered:['등록됨','tag-registered'],active:['사용 중','tag-registered'],retired:['폐기','tag-retired'],draft:['미등록 초안','tag-draft']};
 const [label,cls]=map[status]||map.registered;
 return el('span',code?label+' '+code:label,'tag '+cls);
}
function dataTable(label,headers,rows){
 const wrap=h('div','table-wrap');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',label);
 const hr=h('tr',null,headers.map(text=>{const th=el('th',text);th.scope='col';return th;}));
 wrap.append(h('table','data-table',h('thead',null,hr),h('tbody',null,rows)));
 return wrap;
}
function td(content,cls){return h('td',cls,content);}

/* ------------------------------------------------------------------ formatting */

function requestId(){
 if(typeof crypto.randomUUID==='function')return crypto.randomUUID();
 const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
 const x=[...bytes].map(b=>b.toString(16).padStart(2,'0')).join('');
 return x.slice(0,8)+'-'+x.slice(8,12)+'-'+x.slice(12,16)+'-'+x.slice(16,20)+'-'+x.slice(20);
}
/* Records carry machine ids and UTC timestamps; both are unreadable in a log. */
function stamp(value){
 const d=new Date(value);
 if(isNaN(d.getTime()))return value||'';
 const p=n=>String(n).padStart(2,'0');
 return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes());
}
function auditEntity(entity){return !entity?'':UUID.test(entity)?'#'+entity.slice(0,8):entity;}
function catalogFields(c){return {...(c.source?.catalog_fields||{}),...c};}
/** The planner's clipboard block. Synthetic samples say so, so they never pass as real codes. */
function copyPayload(c){
 return (c.source?.synthetic?'[합성 샘플 · 실제 등록 코드 아님]\n':'')+'알림 코드: '+c.code+'\n표시 문구: '+c.message+'\n기존 노출 조건: '+(c.trigger||'미기재')+'\n이번 기획의 조건: [별도 작성]';
}
function readableAnswer(text){
 // Long saved prose gets visual paragraph breaks; stored text stays unchanged.
 if(text.length<180||text.includes('\n')||typeof Intl.Segmenter!=='function')return text;
 return [...new Intl.Segmenter('ko',{granularity:'sentence'}).segment(text)].map(s=>s.segment.trim()).join('\n\n');
}

/* ------------------------------------------------------------------ feedback */

function error(e){
 const box=$('#error');
 $('.error-message',box).textContent=(e&&e.message)?e.message:String(e);
 box.hidden=false;
}
function clearError(){$('#error').hidden=true;}
let noticeTimer=0;
function note(text){
 clearTimeout(noticeTimer);$('#notice').textContent=text;
 noticeTimer=setTimeout(()=>{$('#notice').textContent='';},6000);
}
/* Buttons report work without dropping their label: the label is what names the control. */
function setBusy(btn,on){
 if(on)btn.setAttribute('aria-busy','true');else btn.removeAttribute('aria-busy');
 btn.disabled=on;
}
function markDone(btn,label){
 if(btn.dataset.done==='1')return;
 const original=btn.textContent;
 btn.dataset.done='1';btn.classList.add('is-done');btn.textContent=label;
 setTimeout(()=>{btn.classList.remove('is-done');btn.textContent=original;delete btn.dataset.done;},1400);
}

/* ------------------------------------------------------------------ api */

function ns(path){return path+(path.includes('?')?'&':'?')+'namespace='+encodeURIComponent(catalogNamespace);}
function authHeaders(){return token?{Authorization:'Bearer '+token}:{};}
async function api(path,body,method){
 if(!token&&!localMode)throw new Error('원본 로그인이 필요합니다.');
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),250000);
 try{
  const headers=authHeaders();
  if(body&&!(body instanceof FormData))headers['Content-Type']='application/json';
  const r=await fetch(base+path,{method:method||(body?'POST':'GET'),headers,body:body instanceof FormData?body:body?JSON.stringify(body):undefined,signal:controller.signal});
  if(r.status===401){
   if(localMode)throw new Error('공용 작업실에 연결하지 못했습니다. 새로고침해주세요.');
   token=null;window.parent.postMessage({type:'catalog-refresh'},location.origin);
   throw new Error('로그인 정보를 갱신하고 있습니다. 갱신 후 다시 보내주세요.');
  }
  if(!r.ok){
   let d={};try{d=await r.json();}catch{}
   const failure=new Error(typeof d.detail==='string'?d.detail:'요청을 처리하지 못했습니다. ('+r.status+')');
   failure.status=r.status;throw failure;
  }
  return await r.json();
 }catch(e){
  if(e.name==='AbortError')throw new Error('요청 시간이 초과되었습니다. 대화를 새로 불러와 상태를 확인해주세요.');
  throw e;
 }finally{clearTimeout(timer);}
}
const getCode=code=>api(ns('/codes/'+encodeURIComponent(code)));

/* ------------------------------------------------------------------ auth + boot */

async function init(){
 const s=await api(ns('/status'));
 user=s.user;
 $$('.admin').forEach(x=>{x.hidden=user.role!=='admin';});
 $('#external-ack').closest('label').hidden=s.authority!=='excel';
 $('#auth').hidden=true;$('#app').hidden=false;
 showIndex(s);syncTabs();
 await restoreSession();
}
async function restoreSession(){
 const ui=recall('ui')||{};
 const switchNs=NAMESPACES.includes(ui.namespace)&&ui.namespace!==catalogNamespace;
 if(switchNs){$('#catalog-namespace').value=ui.namespace;updateCatalogNamespace(false);}
 const saved=recall('catalog');
 if(saved){
  catalogQuery=String(saved.q||'');catalogStatus=['all','active','retired'].includes(saved.status)?saved.status:'all';catalogOffset=Math.max(0,Number(saved.offset)||0);
  $('#catalog-query').value=catalogQuery;$('#catalog-status').value=catalogStatus;
 }
 await Promise.all([loadThreads(),refreshCatalogHint(),switchNs&&refreshStatus()]);
 const turn=recall('turn');
 const threadId=turn&&turn.namespace===catalogNamespace?turn.threadId:recall('thread:'+catalogNamespace);
 if(threadId){
  try{await loadThread(threadId);}catch{remember('thread:'+catalogNamespace,null);}
 }
 restoreInspections();
 const tab=ui.view&&tabs.find(t=>t.dataset.view===ui.view);
 if(tab&&!tab.hidden&&ui.view!=='chat')await selectTab(tab);
 if(turn)resumeTurn(turn).catch(error);
}
window.addEventListener('message',event=>{
 if(event.origin!==location.origin||event.source!==window.parent||event.data?.type!=='catalog-auth')return;
 if(event.data.local===true){
  const first=!localMode;localMode=true;token=null;if(first)init().catch(error);
 }else if(typeof event.data.token==='string'&&event.data.token){
  const first=!token||localMode;localMode=false;token=event.data.token;if(first)init().catch(error);
 }else{
  token=null;localMode=false;
  $('#auth').hidden=false;$('#auth').textContent='원본 로그인 화면에서 다시 로그인해주세요.';
  $('#app').hidden=true;
 }
});
window.parent.postMessage({type:'catalog-ready'},location.origin);

function showIndex(s){
 const pill=$('#index-state');
 const state=s.index_error?'error':(s.index_ready!==false&&s.version===s.indexed_version?'ready':'pending');
 pill.dataset.state=state;
 pill.textContent=(s.embedding==='none'?'키워드 검색 · ':'')+(state==='error'?'검색 준비 오류':state==='ready'?'검색 준비됨':'변경분 준비 필요');
 pill.title=state==='error'&&s.index_error?String(s.index_error):'';
}
async function refreshStatus(){
 const namespace=catalogNamespace,s=await api(ns('/status'));
 if(namespace===catalogNamespace)showIndex(s);
}

async function refreshCatalogHint(){
 const namespace=catalogNamespace;
 const result=await api(ns('/codes?limit=1'));
 if(namespace!==catalogNamespace)return;
 $('#catalog-empty-hint')?.remove();
 const welcome=$('.welcome');
 if(welcome)welcome.hidden=result.total===0;
 if(result.total!==0)return;
 const production=namespace==='production';
 const hint=emptyState(production?'연결된 DB에 알림 코드가 없습니다':'샘플 목록이 비어 있습니다',
  production?'DB 조회는 정상입니다. 연결된 실제 목록에 데이터가 없습니다. DB 데이터 연동 상태를 확인해주세요.':'현재 선택한 샘플 목록에 검색할 항목이 없습니다.',
  'list-empty',button('전체 코드 확인','btn',()=>selectTab($('#tab-catalog'))));
 hint.id='catalog-empty-hint';$('#messages').before(hint);
}

/* ------------------------------------------------------------------ tabs */

const tabs=$$('[role=tab]');
let tabFocus=0;
function visibleTabs(){return tabs.filter(t=>!t.hidden);}
function syncTabs(){
 const vis=visibleTabs();
 if(!vis.length)return;
 if(!vis.includes(tabs[tabFocus]))tabFocus=tabs.indexOf(vis[0]);
 tabs.forEach(t=>{t.tabIndex=t===tabs[tabFocus]?0:-1;});
}
function selectTab(btn){
 rememberUi({view:btn.dataset.view});
 tabs.forEach(t=>t.setAttribute('aria-selected',String(t===btn)));
 tabFocus=tabs.indexOf(btn);syncTabs();
 return view(btn.dataset.view);
}
tabs.forEach(t=>{
 t.addEventListener('click',()=>selectTab(t).catch(error));
 t.addEventListener('focus',()=>{tabFocus=tabs.indexOf(t);syncTabs();});
 t.addEventListener('keydown',event=>{
  const vis=visibleTabs(),i=vis.indexOf(t);
  if(i<0)return;
  let next=null;
  if(event.key==='ArrowRight')next=vis[(i+1)%vis.length];
  else if(event.key==='ArrowLeft')next=vis[(i-1+vis.length)%vis.length];
  else if(event.key==='Home')next=vis[0];
  else if(event.key==='End')next=vis[vis.length-1];
  else if(event.key==='Enter'||event.key===' '){event.preventDefault();selectTab(t).catch(error);return;}
  if(next){event.preventDefault();tabFocus=tabs.indexOf(next);syncTabs();next.focus();}
 });
});

const LOADERS={chat:()=>refreshCatalogHint(),catalog:()=>catalog(),drafts:()=>loadDrafts(),audit:()=>audit(),'ai-settings':()=>loadAISettings()};
async function view(name){
 for(const v of $$('.view')){
  if(v.id===name){v.hidden=false;v.classList.add('enter');}
  else v.hidden=true;
 }
 $('#main').scrollTop=0;
 clearError();
 await LOADERS[name]?.();
}

/* ------------------------------------------------------------------ ai settings */

const LOCAL_STATUS={ready:'로컬 임베딩 모델이 준비되어 있습니다.',unconfigured:'로컬 임베딩 서비스가 구성되지 않았습니다. 지금은 키워드 검색 또는 OpenAI 임베딩을 선택할 수 있습니다.',unavailable:'로컬 임베딩 서비스가 응답하지 않거나 모델을 준비 중입니다. 준비가 끝난 뒤 설정을 다시 열어주세요.',model_mismatch:'로컬 임베딩 모델이 설치 설정과 일치하지 않습니다. 서비스 설정을 확인해주세요.'};
function showAILocalStatus(){
 $('#ai-local-status').textContent=LOCAL_STATUS[aiSettings.local_state]||'로컬 임베딩 상태를 확인할 수 없습니다.';
 $('#ai-embedding option[value="local"]').disabled=!aiSettings.local_available;
}
function aiProvider(){return $('#ai-provider').value==='deepseek'?$('#ai-deepseek-connection').value:$('#ai-provider').value;}
function showAIEmbedding(){
 if(!aiSettings)return;
 $('#ai-embedding-key-field').hidden=!($('#ai-embedding').value==='openai'&&aiProvider()!=='openai');
 $('#ai-embedding-key').value='';
 $('#ai-embedding-key-status').textContent=aiSettings.configured.openai?'검색용 OpenAI 키가 설정되어 있습니다. 빈칸으로 저장하면 기존 키를 유지합니다.':'OpenAI 임베딩에는 검색용 OpenAI 키가 별도로 필요합니다.';
}
function showAIProvider(resetModel=true){
 if(!aiSettings)return;
 $('#deepseek-connection').hidden=$('#ai-provider').value!=='deepseek';
 const p=aiProvider();
 if(resetModel)$('#ai-model').value=aiSettings.models[p];
 $('#ai-key').value='';
 $('#ai-key-status').textContent=aiSettings.configured[p]?'API 키가 설정되어 있습니다. 빈칸으로 저장하면 기존 키를 유지합니다.':'이 공급자의 API 키가 필요합니다.';
 showAIEmbedding();
}
function setAIFormDisabled(on){
 for(const field of $$('input,select,button',$('#ai-settings-form')))field.disabled=on;
}
async function loadAISettings(){
 setAIFormDisabled(true);
 try{
  aiSettings=await api('/ai-settings');
  $('#ai-provider').value=aiSettings.provider==='commandcode'?'deepseek':aiSettings.provider;
  $('#ai-deepseek-connection').value=aiSettings.provider==='commandcode'?'commandcode':'deepseek';
  $('#ai-model').value=aiSettings.model;$('#ai-embedding').value=aiSettings.embedding;
  showAILocalStatus();showAIProvider(false);
 }finally{setAIFormDisabled(false);}
}
$('#ai-provider').addEventListener('change',()=>showAIProvider());
$('#ai-deepseek-connection').addEventListener('change',()=>showAIProvider());
$('#ai-embedding').addEventListener('change',showAIEmbedding);
$('#ai-settings-form').addEventListener('submit',async event=>{
 event.preventDefault();
 const btn=$('#ai-save');
 if(!aiSettings)return;
 setBusy(btn,true);$('#ai-settings-result').textContent='';
 try{
  aiSettings=await api('/ai-settings',{version:aiSettings.version,provider:aiProvider(),model:$('#ai-model').value,embedding:$('#ai-embedding').value,api_key:$('#ai-key').value,embedding_api_key:$('#ai-embedding-key').value},'PUT');
  $('#ai-settings-result').textContent=aiSettings.notice;
  showAIProvider(false);showAILocalStatus();
  await refreshStatus();
 }catch(e){error(e);}finally{
  // Keys never linger in the page after a save attempt.
  $('#ai-key').value='';$('#ai-embedding-key').value='';setBusy(btn,false);
 }
});

/* ------------------------------------------------------------------ candidate cards */

function differenceBox(comparison){
 return h('div','difference',el('strong',comparison.label),comparison.differences.join('\n'));
}
function candidateCard(c,comparison,actions){
 const code=el('span',c.code,'code-chip');code.setAttribute('translate','no');
 const src=c.source||{};
 const meta=h('dl','meta',
  metaRow('메뉴',c.menu||'미기재'),
  metaRow('노출 조건',c.trigger||'미기재 · 재사용 전 확인'),
  src.filename&&metaRow('출처',[src.filename,src.sheet,src.cells||src.row].filter(Boolean).join(' / ')));
 return h('article','card',
  h('div','card-head',code,statusTag(c.status)),
  el('p',c.message,'message'),
  meta,
  comparison&&differenceBox(comparison),
  actions?.length&&h('div','card-actions',actions));
}
function chooseCandidate(code){
 selected=code;
 if(!$('#question').value.trim())$('#question').value=code+'에 대해 설명해줘';
 setSelection(code);autosize();$('#question').focus();
}
function chatCard(c,comparison){
 const copy=button('기획서에 복사','btn',async b=>{
  await navigator.clipboard.writeText(copyPayload(c));
  markDone(b,'복사됨');note('원문을 복사했습니다.');
 });
 return candidateCard(c,comparison,[copy,button('이 후보 선택','btn',()=>chooseCandidate(c.code))]);
}
function draftCard(d,detail,cls){
 const registered=d.status==='registered';
 const candidates=d.payload.candidates||[];
 const meta=h('dl','meta',
  d.owner!==undefined&&metaRow('작성자',String(d.owner)),
  d.catalog_version!==undefined&&metaRow('검토 기준','목록 버전 '+d.catalog_version),
  candidates.length&&metaRow('관련 후보',candidates.map(c=>c.code).join(', ')),
  detail&&metaRow('상태',detail));
 return h('article',cls||'card draft-card',
  h('div','card-head',statusTag(registered?'registered':'draft',registered?d.registered_code:''),d.created_at&&el('span',stamp(d.created_at),'tag tag-soft stamp')),
  el('p',d.payload.message,'message'),
  meta.childElementCount&&meta);
}

/* ------------------------------------------------------------------ chat */

async function loadThreads(){
 const namespace=catalogNamespace,rows=await api(ns('/threads'));
 if(namespace!==catalogNamespace)return;
 const list=$('#threads');
 if(!rows.length){
  list.replaceChildren(emptyState('아직 대화가 없습니다','상황을 설명하면 이곳에 대화가 쌓입니다.','threads-empty'));
  return;
 }
 list.replaceChildren(...rows.map(r=>{
  const b=button(r.title||'(제목 없음)','',()=>loadThread(r.id));
  b.dataset.id=r.id;
  return b;
 }));
 markActiveThread();
}
function markActiveThread(){
 for(const b of $$('#threads button[data-id]')){
  if(thread&&b.dataset.id===thread.id)b.setAttribute('aria-current','true');else b.removeAttribute('aria-current');
 }
}
function addBubble(role,text,tag){
 const shouldTag=tag===undefined?role==='assistant':tag;
 const n=h('div','bubble '+role,shouldTag&&el('span','AI 설명','tag tag-ai'),el('div',role==='assistant'?readableAnswer(text):text,'bubble-body'));
 $('#messages').append(n);
 return n;
}
function setBubbleText(node,text){$('.bubble-body',node).textContent=node.classList.contains('assistant')?readableAnswer(text):text;}
function scrollMessages(node){
 const box=$('#messages');
 if(node)box.scrollTop=Math.max(0,node.offsetTop-box.offsetTop-8);else box.scrollTop=box.scrollHeight;
}
async function loadThread(id){
 if(busy){note('답변을 받는 중입니다. 완료된 뒤 다른 대화를 열어주세요.');return;}
 const namespace=catalogNamespace;
 const loaded=await api(ns('/threads/'+encodeURIComponent(id)));
 // A code deleted since (404) is left out; any other failure is reported, not hidden.
 const candidates=(await Promise.all(loaded.candidates.map(c=>getCode(c.code).catch(e=>{if(e.status===404)return null;throw e;})))).filter(Boolean);
 if(namespace!==catalogNamespace)return;
 thread=loaded;clearSelection();remember('thread:'+namespace,loaded.id);
 const box=$('#messages');box.replaceChildren();
 for(const m of thread.history)addBubble(m.role,m.content,m.role==='assistant'&&m.ai_used!==false);
 if(candidates.length||thread.draft)showResults({candidates,comparisons:[],draft:thread.draft});
 else if(!thread.history.length)box.append(emptyState('비어 있는 대화입니다','아래에 상황을 적으면 기존 코드를 찾아 드립니다.'));
 scrollMessages();markActiveThread();
}
function showResults(result){
 const comparisons=result.comparisons||[];
 const cards=h('div','cards stagger',(result.candidates||[]).map(c=>chatCard(c,comparisons.find(x=>x.code===c.code))));
 const draft=result.draft&&h('div','draft-slot',draftCard(result.draft,result.draft.status==='registered'
  ?'등록된 코드입니다. 추가 변경은 별도로 검토해주세요.'
  :'초안함에서 유사 항목 재검토 후 등록을 진행합니다.'));
 if(!cards.childElementCount&&!draft)return;
 $('#messages').append(h('div','result-group',cards.childElementCount&&cards,draft));
}

function setSelection(code){
 $('#selection .selection-text').textContent='선택한 후보: '+code+' · 다음 질문에서 함께 확인합니다.';
 $('#selection').hidden=false;
}
function clearSelection(){
 selected=null;
 $('#selection .selection-text').textContent='';
 $('#selection').hidden=true;
}
bind('#clear-selection',clearSelection);

/** First "..." or “...” phrase in the question, verbatim; '' when there is none. */
function quotedPhrase(text){const m=/["“]([^"”\n]+)["”]/.exec(text);return m?m[1].trim():'';}
function autosize(){
 const q=$('#question');
 q.style.height='auto';q.style.height=Math.min(q.scrollHeight+2,220)+'px';
}
function updateCount(){
 const n=$('#question').value.length;
 $('#compose-count').textContent=n>COUNT_AT?n+' / 4000':'';
}
$('#question').addEventListener('input',()=>{updateCount();autosize();});
$('#question').addEventListener('keydown',e=>{
 if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#ask-form').requestSubmit();}
});
for(const b of $$('.example'))b.addEventListener('click',()=>{
 const q=$('#question');q.value=b.dataset.query||b.textContent;
 updateCount();autosize();q.focus();
});

$('#ask-form').addEventListener('submit',async event=>{
 event.preventDefault();
 if(busy)return;
 const text=$('#question').value;
 if(!text.trim())return;
 clearError();
 busy=true;$('#catalog-namespace').disabled=true;
 const send=$('#send');setBusy(send,true);
 let pending;
 try{
  if(!thread){thread=await api(ns('/threads'),{});remember('thread:'+catalogNamespace,thread.id);$('#messages').replaceChildren();}
  addBubble('user',text);
  pending=addBubble('assistant','기존 코드와 사용 조건을 확인하고 있습니다…',false);
  pending.classList.add('is-pending');scrollMessages();
  // The wording to compare or keep verbatim is the phrase the planner quotes in the question,
  // sent exactly as typed (explicit actions skip the AI planner, so it must travel as a field).
  // Menu/trigger comparison lives in the 문구 비교 tab.
  const payload={request_id:requestId(),expected_version:thread.version,text,action:$('#action').value,selected_code:selected,proposed_message:quotedPhrase(text)};
  remember('turn',{namespace:catalogNamespace,threadId:thread.id,version:thread.version,text,startedAt:Date.now()});
  const result=await api(ns('/threads/'+thread.id+'/turn'),payload);
  remember('turn',null);
  pending.classList.remove('is-pending');setBubbleText(pending,result.answer);
  if(result.ai_used===true)pending.prepend(el('span','AI 설명','tag tag-ai'));
  showResults(result);
  thread.version=result.version;
  $('#question').value='';updateCount();autosize();clearSelection();
  scrollMessages(pending);
  await Promise.all([loadThreads(),refreshStatus()]);
 }catch(e){
  // Leaving the page aborts the fetch, not the server: keep the turn for resumeTurn().
  if(leaving)return;
  remember('turn',null);
  if(pending){pending.classList.remove('is-pending');setBubbleText(pending,'요청이 완료되지 않았습니다. 위 오류를 확인해주세요.');}
  error(e);
 }finally{
  busy=false;$('#catalog-namespace').disabled=false;setBusy(send,false);
 }
});

function lockComposer(on){
 busy=on;$('#catalog-namespace').disabled=on;setBusy($('#send'),on);
}
/** Show a turn that was sent before the planner left, and wait for the server to finish it.
    Nothing is re-sent: the thread version moving past the saved one means the answer landed. */
async function resumeTurn(turn){
 const age=()=>Date.now()-turn.startedAt;
 if(age()>RESUME_WINDOW||turn.namespace!==catalogNamespace||thread?.id!==turn.threadId||thread.version>turn.version){remember('turn',null);return;}
 lockComposer(true);
 addBubble('user',turn.text);
 const pending=addBubble('assistant','',false);pending.classList.add('is-pending');
 const tick=()=>setBubbleText(pending,'다른 화면에 다녀오는 동안에도 처리하고 있습니다… '+Math.round(age()/1000)+'초 경과');
 tick();scrollMessages();
 try{
  while(age()<RESUME_WINDOW){
   await sleep(2000);
   // The planner opened another thread or list: the answer will be in that thread's history.
   if(thread?.id!==turn.threadId||catalogNamespace!==turn.namespace){remember('turn',null);return;}
   const current=await api(ns('/threads/'+encodeURIComponent(turn.threadId)));
   if(current.version>turn.version){
    remember('turn',null);
    lockComposer(false);
    await loadThread(turn.threadId);
    await Promise.all([loadThreads(),refreshStatus()]);
    return;
   }
   tick();
  }
  remember('turn',null);
  pending.classList.remove('is-pending');
  setBubbleText(pending,'이전 요청의 결과를 확인하지 못했습니다. 처리 시간이 초과되었거나 실패했을 수 있습니다. 다시 보내주세요.');
 }finally{lockComposer(false);}
}

bind('#new-thread',async()=>{
 if(busy){note('답변을 받는 중입니다. 완료된 뒤 새 대화를 시작해주세요.');return;}
 thread=await api(ns('/threads'),{});
 remember('thread:'+catalogNamespace,thread.id);
 clearSelection();
 $('#messages').replaceChildren();
 addBubble('assistant','새 대화를 시작했습니다. 필요한 알림 상황을 설명해주세요.',false);
 await loadThreads();
 $('#question').focus();
});

/* ------------------------------------------------------------------ catalogue */

async function copyCatalog(c,btn){
 // Copy the current DB row, not the one rendered minutes ago.
 const current=await getCode(c.code);
 if(current.status==='retired')throw new Error('폐기된 코드는 복사할 수 없습니다.');
 await navigator.clipboard.writeText(copyPayload(current));
 markDone(btn,'복사됨');note('원문을 복사했습니다.');
}
function copyButton(c,label){
 const b=button(label,'btn',btn=>copyCatalog(c,btn));
 b.disabled=c.status==='retired';
 return b;
}
async function catalogDetail(code){
 const generation=inspectionGeneration;
 const c=await getCode(code);
 if(generation!==inspectionGeneration)return;
 const f=catalogFields(c);
 $('#catalog-detail-title').textContent=c.code;
 const rows=[['업무구분',f.business],['타입',f.message_type],['메시지코드',c.message_code||c.code],['용도',f.purpose],['title',f.title],['맞춤법검사',f.spelling_check||'미검사'],['영문 title',f.title_en],['영문 contents',f.contents_en],['추가날짜',f.added_date],['메뉴',c.menu],['노출 조건',c.trigger],['비고',c.notes],['출처',[c.source?.filename,c.source?.sheet,c.source?.cells].filter(Boolean).join(' / ')]];
 const choose=button('대화에서 확인','btn btn-solid',()=>{
  $('#catalog-detail').close();
  return selectTab($('#tab-chat')).then(()=>{$('#question').value=c.code+'에 대해 설명해줘';chooseCandidate(c.code);});
 });
 $('#catalog-detail-content').replaceChildren(
  h('div','card-head',statusTag(c.status==='retired'?'retired':'active'),c.source?.synthetic&&el('span','합성 샘플','tag tag-soft')),
  el('p',f.title||c.message,'message'),
  h('dl','meta',rows.map(([label,value])=>metaRow(label,value||'—'))),
  h('div','card-actions',copyButton(c,'복사'),choose));
 if(!$('#catalog-detail').open)$('#catalog-detail').showModal();
}
function catalogRow(c){
 const f=catalogFields(c);
 const detail=el('button',c.code,'catalog-code');detail.type='button';detail.setAttribute('translate','no');
 detail.addEventListener('click',()=>catalogDetail(c.code).catch(error));
 return h('tr',null,
  td(detail,'nowrap'),td(statusTag(c.status==='retired'?'retired':'active')),
  td(f.business||'—','nowrap'),td(f.message_type||'—','nowrap'),td(f.purpose||'—'),
  td(f.title||c.message,'wide'),td(f.spelling_check||'미검사','nowrap'),
  td(f.title_en||'—','wide'),td(f.contents_en||'—','wide'),td(f.notes||'—','wide'),
  td(f.added_date||'—','nowrap stamp'),td(copyButton(c,'복사')));
}
async function catalog(){
 const request=++catalogRequest;
 $('#previous').disabled=true;$('#next').disabled=true;
 const host=$('#catalog-list');
 remember('catalog',{q:catalogQuery,status:catalogStatus,offset:catalogOffset});
 const params=new URLSearchParams({q:catalogQuery,status:catalogStatus,offset:String(catalogOffset),limit:String(CATALOG_PAGE)});
 let r;
 await withSkeleton(host,3,async()=>{r=await api(ns('/codes?'+params));},()=>request===catalogRequest);
 if(request!==catalogRequest)return;
 const total=r.total;
 if(catalogOffset>=total&&catalogOffset>0){catalogOffset=Math.max(0,Math.floor((total-1)/CATALOG_PAGE)*CATALOG_PAGE);return catalog();}
 $('#catalog-count').textContent=total?`${catalogOffset+1}–${Math.min(catalogOffset+CATALOG_PAGE,total)} / 총 ${total}개`:'총 0개';
 const pages=Math.max(1,Math.ceil(total/CATALOG_PAGE));
 $('#catalog-page').textContent=total?`${Math.floor(catalogOffset/CATALOG_PAGE)+1} / ${pages}`:'';
 if(!r.items.length){
  host.replaceChildren(emptyState('조회 결과가 없습니다',catalogQuery||catalogStatus!=='all'?'검색어 또는 사용 상태 조건을 바꿔보세요.':'DB 조회는 정상입니다. 선택한 목록에 데이터가 없습니다.'));
 }else{
  host.replaceChildren(dataTable('전체 코드 표',['메시지코드','상태','업무구분','타입','용도','title','맞춤법검사','영문 title','영문 contents','비고','추가날짜','복사'],r.items.map(catalogRow)));
 }
 $('#previous').disabled=catalogOffset===0;$('#next').disabled=catalogOffset+CATALOG_PAGE>=total;
}
function searchCatalog(){
 catalogQuery=$('#catalog-query').value.trim();catalogStatus=$('#catalog-status').value;catalogOffset=0;
 return catalog();
}
bind('#previous',()=>{catalogOffset=Math.max(0,catalogOffset-CATALOG_PAGE);return catalog();});
bind('#next',()=>{catalogOffset+=CATALOG_PAGE;return catalog();});
$('#catalog-form').addEventListener('submit',event=>{event.preventDefault();searchCatalog().catch(error);});
$('#catalog-status').addEventListener('change',()=>searchCatalog().catch(error));
bind('#export',async()=>{
 const btn=$('#export');setBusy(btn,true);
 try{
  const r=await fetch(base+ns('/export.json'),{headers:authHeaders()});
  if(!r.ok)throw new Error('내보내기에 실패했습니다. 잠시 후 다시 시도해주세요.');
  const url=URL.createObjectURL(await r.blob());
  const a=el('a');a.href=url;a.download=catalogNamespace==='demo'?'sample_catalog_300.json':'code-catalog.json';a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
 }finally{setBusy(btn,false);}
});

bind('#index',async()=>{
 const btn=$('#index');setBusy(btn,true);
 try{await api(ns('/index'),{});}finally{setBusy(btn,false);}
 note('검색 준비 작업을 등록했습니다. 완료되면 상단 상태가 바뀝니다.');
 await refreshStatus();
});

/* ------------------------------------------------------------------ drafts + approval */

async function loadDrafts(){
 const host=$('#draft-list');
 await withSkeleton(host,2,async()=>{
  const drafts=await api('/drafts');
  host.replaceChildren(...(drafts.length?drafts.map(draftRow):[emptyState('저장된 초안이 없습니다','대화에서 신규 문구를 작성하면 이곳에서 검토하고 등록합니다.')]));
 });
}
function draftRow(d){
 const n=draftCard(d,undefined,'card draft-row');
 const open=d.status==='draft';
 const review=button('최신 후보 재검토','btn',async b=>{
  setBusy(b,true);
  try{
   const r=await api('/drafts/'+d.id+'/review',{});
   note('후보 '+r.candidates.length+'개와 비교했습니다.');
   await loadDrafts();
  }finally{setBusy(b,false);}
 });
 review.disabled=!open;
 const actions=[review];
 if(user?.role==='admin'){
  const approve=button('등록 검토','btn btn-solid',()=>openApproval(d));
  approve.disabled=!open;actions.push(approve);
 }
 n.append(h('div','card-actions',actions));
 return n;
}
function openApproval(d){
 pendingApproval=d;
 $('#approve-message').textContent=d.payload.message;
 for(const id of ['#approve-code','#approve-reason'])$(id).value='';
 for(const id of ['#duplicate-ack','#external-ack'])$(id).checked=false;
 $('#approve-error').hidden=true;
 $('#approval').showModal();$('#approve-code').focus();
}
bind('#refresh-drafts',loadDrafts);
for(const id of ['#approve-code','#approve-reason'])$(id).addEventListener('keydown',event=>{
 if(event.key==='Enter'&&!event.isComposing){event.preventDefault();$('#approve-submit').click();}
});
$('#approve-submit').addEventListener('click',async()=>{
 if(!pendingApproval)return;
 const form=$('#approval form'),btn=$('#approve-submit'),problem=$('#approve-error');
 if(!form.reportValidity())return;
 problem.hidden=true;setBusy(btn,true);
 try{
  const result=await api('/drafts/'+pendingApproval.id+'/approve',{
   expected_catalog_version:pendingApproval.catalog_version,
   expected_draft_revision:pendingApproval.revision,
   code:$('#approve-code').value,
   reason:$('#approve-reason').value,
   duplicate_ack:$('#duplicate-ack').checked,
   external_registered:$('#external-ack').checked,
  });
  $('#approval').close();pendingApproval=null;
  note(result.code+'로 등록했습니다. 등록한 초안은 더 이상 수정할 수 없습니다.');
  await Promise.all([loadDrafts(),refreshStatus()]);
 }catch(e){
  // The dialog is modal: an error behind it would be invisible.
  problem.textContent=e&&e.message?e.message:String(e);problem.hidden=false;
 }finally{setBusy(btn,false);}
});

/* ------------------------------------------------------------------ audit */

async function audit(){
 const host=$('#audit-list');
 await withSkeleton(host,3,async()=>{
  const rows=await api('/audit');
  if(!rows.length){host.replaceChildren(emptyState('변경 기록이 없습니다','등록·수정·승인 작업이 발생하면 사용자와 사유가 이곳에 기록됩니다.'));return;}
  host.replaceChildren(dataTable('변경 기록 표',['일시','작업','항목','사용자','기록'],rows.map(r=>h('tr',null,
   td(stamp(r.created_at),'stamp'),
   td([el('strong',AUDIT_ACTION[r.action]||r.action),el('div',r.action,'dim small')],'nowrap'),
   td(auditEntity(r.entity),'nowrap'),
   td(String(r.actor)),
   td([el('p',r.reason||'—'),h('details',null,el('summary','변경 전·후 보기'),el('pre',JSON.stringify({이전:r.before,이후:r.after},null,2)))])))));
 });
}
bind('#audit-refresh',audit);

/* ------------------------------------------------------------------ compare + review */

function inspectionBlock(result){
 const missing=result.missing_codes?.length>0;
 const detail=c=>button('상세 보기','btn',()=>catalogDetail(c.code));
 const summary=h('div','result-summary'+(missing?' has-missing':''),
  h('div','result-chips',INSPECTION_MODE[result.mode]&&el('span',INSPECTION_MODE[result.mode],'tag tag-soft'),result.notice&&el('span',result.notice,'tag tag-soft')),
  el('p',result.summary,'result-text'));
 const cards=result.candidates.length?h('div','cards',result.candidates.map(c=>candidateCard(c,result.comparisons.find(x=>x.code===c.code),[detail(c)]))):null;
 return [summary,cards];
}
function renderInspection(kind,result){
 const host=$('#'+kind+'-results');
 if(kind==='compare'){host.replaceChildren(...inspectionBlock(result).filter(Boolean));return;}
 const missing=result.items.filter(i=>i.missing_codes?.length).length;
 host.replaceChildren(
  el('p',result.items.length+'줄 검토'+(missing?' · 미등록 코드 포함 '+missing+'줄':''),'review-count'),
  ...result.items.map(item=>h('section','review-item',h('h3',null,el('span',item.line+'행','review-line'),item.input),inspectionBlock(item))));
}
const INSPECTION_FIELDS={compare:{message:'#compare-message',menu:'#compare-menu',trigger:'#compare-trigger',mode:'#compare-mode'},review:{text:'#review-text',mode:'#review-mode'}};
/** Refill the forms; show the last result, or re-run a check that was still running (read-only). */
function restoreInspections(){
 for(const kind of ['compare','review']){
  const saved=recall('inspect:'+kind);
  if(!saved||saved.namespace!==catalogNamespace)continue;
  for(const [key,selector] of Object.entries(INSPECTION_FIELDS[kind]))if(typeof saved.payload?.[key]==='string')$(selector).value=saved.payload[key];
  if(saved.result){try{renderInspection(kind,saved.result);}catch{remember('inspect:'+kind,null);}}
  else if(saved.pending&&Date.now()-saved.startedAt<RESUME_WINDOW){
   note(kind==='compare'?'진행 중이던 문구 비교를 이어서 실행합니다.':'진행 중이던 기획서 검토를 이어서 실행합니다.');
   $('#'+kind+'-form').requestSubmit();
  }else remember('inspect:'+kind,null);
 }
}
for(const kind of ['compare','review'])$('#'+kind+'-form').addEventListener('submit',async event=>{
 event.preventDefault();
 const form=event.currentTarget,btn=form.querySelector('[type="submit"]'),host=$('#'+kind+'-results');
 const generation=inspectionGeneration;
 setBusy(btn,true);clearError();host.replaceChildren(el('p','검토 중입니다.','inspection-loading'));
 const payload={namespace:catalogNamespace,mode:$('#'+kind+'-mode').value};
 if(kind==='compare')Object.assign(payload,{message:$('#compare-message').value,menu:$('#compare-menu').value,trigger:$('#compare-trigger').value});
 else payload.text=$('#review-text').value;
 remember('inspect:'+kind,{namespace:catalogNamespace,payload,pending:true,startedAt:Date.now()});
 try{
  const result=await api('/'+kind,payload);
  if(generation!==inspectionGeneration)return;
  remember('inspect:'+kind,{namespace:catalogNamespace,payload,result});
  renderInspection(kind,result);
  // Single-column layout puts results below the form: bring them into view.
  if(host.getBoundingClientRect().top>$('#main').getBoundingClientRect().bottom-120)host.scrollIntoView({block:'start'});
 }catch(e){
  if(leaving)return;
  if(generation===inspectionGeneration){remember('inspect:'+kind,null);host.replaceChildren();error(e);}
 }finally{setBusy(btn,false);}
});

/* ------------------------------------------------------------------ namespace */

function updateCatalogNamespace(reload=true){
 const changed=catalogNamespace!==$('#catalog-namespace').value;
 catalogNamespace=$('#catalog-namespace').value;inspectionGeneration++;catalogRequest++;catalogOffset=0;
 const demo=catalogNamespace==='demo';
 const scopeNote=demo?'합성 DB 샘플 300건을 검색합니다. 샘플 대화와 검색 인덱스는 실제 목록과 분리됩니다.':'연결된 DB의 실제 알림 목록을 조회합니다.';
 $('#catalog-scope-note').textContent=scopeNote;
 if(changed)$('#catalog-scope-live').textContent=scopeNote;
 $('#compare-results').replaceChildren();$('#review-results').replaceChildren();
 if($('#catalog-detail').open)$('#catalog-detail').close();
 // Sample conversations never create registrable drafts.
 $('#action option[value=draft]').disabled=demo;
 if(demo&&$('#action').value==='draft')$('#action').value='auto';
 if(changed){
  thread=null;clearSelection();
  $('#messages').replaceChildren();
  addBubble('assistant',demo?'샘플 300건에서 알림을 찾아보세요.':'실제 등록 목록에서 검색합니다.',false);
  if(user&&reload){
   rememberUi({namespace:catalogNamespace});remember('inspect:compare',null);remember('inspect:review',null);
   loadThreads().catch(error);refreshStatus().catch(error);refreshCatalogHint().catch(error);
  }
 }
 if(reload&&!$('#catalog').hidden)catalog().catch(error);
}
$('#catalog-namespace').addEventListener('change',()=>updateCatalogNamespace());
updateCatalogNamespace();

bind('#error-dismiss',clearError);
/* ------------------------------------------------------------------ popovers + tooltips */

/** Keep a fixed-position box inside the viewport, below the anchor (above if no room). */
function place(box,anchor){
 const a=anchor.getBoundingClientRect(),gap=8,edge=12;
 const w=box.offsetWidth,h=box.offsetHeight;
 const left=Math.min(Math.max(edge,a.left+a.width/2-w/2),innerWidth-w-edge);
 const top=a.bottom+gap+h<=innerHeight-edge?a.bottom+gap:Math.max(edge,a.top-gap-h);
 box.style.left=Math.round(left)+'px';box.style.top=Math.round(top)+'px';
}
/* "?" help: hover (mouse) to peek, click to pin; one open at a time; outside click,
   Escape or scrolling closes it. The whole heading counts as the hover target. */
const helps=$$('details.help');
function closeHelps(except){for(const d of helps)if(d!==except&&d.open){d.open=false;delete d.dataset.peek;}}
for(const d of helps){
 const summary=d.querySelector('summary'),pop=d.querySelector('.help-pop');
 d.addEventListener('toggle',()=>{if(d.open){closeHelps(d);place(pop,summary);}});
 // A click on a peeking popover pins it open instead of toggling it shut.
 summary.addEventListener('click',e=>{if(d.dataset.peek){delete d.dataset.peek;e.preventDefault();}});
 const zone=d.closest('.title-row,.rail-heading,.brand')||d;
 zone.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse'&&!d.open){d.dataset.peek='1';d.open=true;}});
 zone.addEventListener('pointerleave',e=>{if(e.pointerType==='mouse'&&d.dataset.peek){delete d.dataset.peek;d.open=false;}});
}
document.addEventListener('click',event=>{for(const d of helps)if(d.open&&!d.contains(event.target))d.open=false;});
document.addEventListener('keydown',event=>{
 if(event.key!=='Escape')return;
 for(const d of helps)if(d.open){d.open=false;d.querySelector('summary').focus();}
});
addEventListener('resize',()=>closeHelps());
document.addEventListener('scroll',()=>closeHelps(),true);

/* Thread titles are ellipsised in the rail: hovering or focusing one shows it in full. */
const tip=el('div',undefined,'tip');tip.hidden=true;tip.setAttribute('role','tooltip');tip.id='thread-tip';document.body.append(tip);
let tipTimer=0;
function showTip(button){
 clearTimeout(tipTimer);
 tipTimer=setTimeout(()=>{
  if(button.scrollWidth<=button.clientWidth||!button.isConnected)return;
  tip.textContent=button.textContent;tip.hidden=false;place(tip,button);
  button.setAttribute('aria-describedby','thread-tip');
 },250);
}
function hideTip(){clearTimeout(tipTimer);tip.hidden=true;for(const b of $$('#threads [aria-describedby]'))b.removeAttribute('aria-describedby');}
const threadList=$('#threads');
threadList.addEventListener('pointerover',e=>{const b=e.target.closest('button[data-id]');if(b)showTip(b);});
threadList.addEventListener('pointerout',e=>{if(!e.relatedTarget||!threadList.contains(e.relatedTarget))hideTip();else if(!e.relatedTarget.closest('button[data-id]'))hideTip();});
threadList.addEventListener('focusin',e=>{const b=e.target.closest('button[data-id]');if(b)showTip(b);});
threadList.addEventListener('focusout',hideTip);
threadList.addEventListener('scroll',hideTip);
syncTabs();
