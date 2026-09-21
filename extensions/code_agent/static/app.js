'use strict';
const $=(s,root=document)=>root.querySelector(s);
const $$=(s,root=document)=>Array.from(root.querySelectorAll(s));

let localMode=false;
let catalogNamespace='demo',inspectionGeneration=0;
let token=null,user=null,thread=null,selected=null,pendingApproval=null,offset=0,total=0,busy=false;
const base='/api/code-catalog';
function scopeQuery(){return '?namespace='+catalogNamespace;}
const COUNT_AT=3200;

/* The API speaks in record verbs; the screen speaks to a planner. */
const AUDIT_ACTION={import_create:'코드 신규 등록',import_update:'코드 내용 변경',draft_create:'초안 생성',approve:'초안 등록 승인',revise:'코드 수정'};
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/* Records carry machine ids and UTC timestamps; both are unreadable in a log. */
function auditAction(action){return AUDIT_ACTION[action]||action;}
function auditEntity(entity){
 if(!entity)return '';
 return UUID.test(entity)?'#'+entity.slice(0,8):entity;
}
function stamp(value){
 const d=new Date(value);
 if(isNaN(d.getTime()))return value||'';
 const p=n=>String(n).padStart(2,'0');
 return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes());
}

/* ------------------------------------------------------------------ helpers */

function requestId(){
 if(typeof crypto.randomUUID==='function')return crypto.randomUUID();
 const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
 const h=[...bytes].map(x=>x.toString(16).padStart(2,'0')).join('');return h.slice(0,8)+'-'+h.slice(8,12)+'-'+h.slice(12,16)+'-'+h.slice(16,20)+'-'+h.slice(20);
}
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function error(e){
 const box=$('#error');
 $('.error-message',box).textContent=(e&&e.message)?e.message:String(e);
 box.hidden=false;
}
function clearError(){$('#error').hidden=true;}
function note(t){$('#notice').textContent=t;}

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

async function api(path,body,method){
 if(!token&&!localMode)throw new Error('원본 로그인이 필요합니다.');
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),250000);
 try{
  const headers=token?{Authorization:'Bearer '+token}:{};if(body&&!(body instanceof FormData))headers['Content-Type']='application/json';
  const r=await fetch(base+path,{method:method||(body?'POST':'GET'),headers,body:body instanceof FormData?body:body?JSON.stringify(body):undefined,signal:controller.signal});
  if(r.status===401){if(localMode)throw new Error('공용 작업실에 연결하지 못했습니다. 새로고침해주세요.');token=null;window.parent.postMessage({type:'catalog-refresh'},location.origin);throw new Error('로그인 정보를 갱신하고 있습니다. 갱신 후 다시 보내주세요.');}
  if(!r.ok){let d={};try{d=await r.json();}catch{}throw new Error(typeof d.detail==='string'?d.detail:'요청을 처리하지 못했습니다. ('+r.status+')');}
  return await r.json();
 }catch(e){if(e.name==='AbortError')throw new Error('요청 시간이 초과되었습니다. 대화를 새로 불러와 상태를 확인해주세요.');throw e;}finally{clearTimeout(timer);}
}
function bind(id,fn){$(id).addEventListener('click',()=>Promise.resolve().then(fn).catch(error));}

/* ------------------------------------------------------------------ blocks */

function skeleton(rows){
 const stack=el('div',undefined,'skeleton-stack');
 for(let i=0;i<rows;i++){
  const box=el('div',undefined,'skeleton');
  box.append(el('div',undefined,'skeleton-line'),el('div',undefined,'skeleton-line'),el('div',undefined,'skeleton-line'));
  stack.append(box);
 }
 return stack;
}
/* A skeleton that flashes for 80ms is worse than none: wait past the threshold first. */
function withSkeleton(host,rows,run){
 let waiting=true;
 const timer=setTimeout(()=>{if(waiting)host.replaceChildren(skeleton(rows));},140);
 return Promise.resolve().then(run).finally(()=>{waiting=false;clearTimeout(timer);});
}
function emptyState(title,body,cls,action){
 const box=el('div',undefined,cls||'list-empty');
 box.append(el('strong',title),el('p',body));
 if(action)box.append(action);
 return box;
}
function statusTag(status,code){
 const map={registered:['등록됨','tag-registered'],retired:['폐기','tag-retired'],draft:['미등록 초안','tag-draft']};
 const row=map[status]||map.registered;
 return el('span',code?row[0]+' '+code:row[0],'tag '+row[1]);
}
function metaRow(term,value){
 const d=el('div');d.append(el('dt',term),el('dd',value));return d;
}

/* ------------------------------------------------------------------ auth + boot */

async function init(){
 const s=await api('/status'+scopeQuery());
 user=s.user;
 $('#who').textContent=user.name||('사용자 '+user.id);
 $$('.admin').forEach(x=>{x.hidden=user.role!=='admin';});
 $('#auth').hidden=true;$('#app').hidden=false;
 $('#external-ack').closest('label').hidden=s.authority!=='excel';
 showIndex(s);syncTabs();
 await loadThreads();
 await refreshCatalogHint();
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

async function refreshCatalogHint(){
 const namespace=catalogNamespace;
 const result=await api('/codes?namespace='+namespace+'&limit=1');
 if(namespace!==catalogNamespace)return;
 document.querySelector('#catalog-empty-hint')?.remove();
 const welcome=$('.welcome');
 if(welcome)welcome.hidden=result.total===0;
 if(result.total!==0)return;
 const action=el('button','전체 코드 확인','btn');action.type='button';
 action.onclick=()=>selectTab($('#tab-catalog')).catch(error);
 const hint=emptyState(namespace==='production'?'연결된 DB에 알림 코드가 없습니다':'샘플 목록이 비어 있습니다',namespace==='production'?'DB 조회는 정상입니다. 연결된 실제 목록에 데이터가 없습니다. DB 데이터 연동 상태를 확인해주세요.':'현재 선택한 샘플 목록에 검색할 항목이 없습니다.','list-empty',action);
 hint.id='catalog-empty-hint';$('#messages').before(hint);
}

function showIndex(s){
 const pill=$('#index-state');
 const state=s.index_error?'error':(s.index_ready!==false&&s.version===s.indexed_version?'ready':'pending');
 pill.dataset.state=state;
 pill.textContent=(s.embedding==='none'?'키워드 검색 · ':'')+(state==='error'?'검색 준비 오류':state==='ready'?'검색 준비됨':'변경분 준비 필요');
}

/* ------------------------------------------------------------------ tabs */

const tabs=$$('[role=tab]');
let tabFocus=0;
function visibleTabs(){return tabs.filter(t=>!t.hidden);}
function syncTabs(){
 const vis=visibleTabs();
 if(!vis.length)return;
 if(!vis.includes(tabs[tabFocus]))tabFocus=tabs.indexOf(vis[0]);
 tabs.forEach(t=>{t.tabIndex=t===vis[tabFocus]?0:-1;});
}
function selectTab(btn){
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

async function view(name){
 $('#catalog-scope').hidden=!['chat','catalog','compare','review'].includes(name);
 $$('.view').forEach(v=>{
  if(v.id===name){v.hidden=false;v.classList.add('enter');}
  else v.hidden=true;
 });
 clearError();
 if(name==='chat')await refreshCatalogHint();
 if(name==='catalog')await catalog();
 if(name==='drafts')await loadDrafts();
 if(name==='audit')await audit();
 if(name==='ai-settings')await loadAISettings();
}

let aiSettings=null;
function showAILocalStatus(){
 const messages={ready:'로컬 임베딩 모델이 준비되어 있습니다.',unconfigured:'로컬 임베딩 서비스가 구성되지 않았습니다. 지금은 키워드 검색 또는 OpenAI 임베딩을 선택할 수 있습니다.',unavailable:'로컬 임베딩 서비스가 응답하지 않거나 모델을 준비 중입니다. 준비가 끝난 뒤 설정을 다시 열어주세요.',model_mismatch:'로컬 임베딩 모델이 설치 설정과 일치하지 않습니다. 서비스 설정을 확인해주세요.'};
 $('#ai-local-status').textContent=messages[aiSettings.local_state]||'로컬 임베딩 상태를 확인할 수 없습니다.';
 $('#ai-embedding option[value="local"]').disabled=!aiSettings.local_available;
}
function aiProvider(){return $('#ai-provider').value==='deepseek'?$('#ai-deepseek-connection').value:$('#ai-provider').value;}
function showAIEmbedding(){
 if(!aiSettings)return;
 const separateKey=$('#ai-embedding').value==='openai'&&aiProvider()!=='openai';
 $('#ai-embedding-key-field').hidden=!separateKey;
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
async function loadAISettings(){
 $('#ai-save').disabled=true;
 for(const field of $('#ai-settings-form').querySelectorAll('input,select'))field.disabled=true;
 aiSettings=await api('/ai-settings');
 $('#ai-provider').value=aiSettings.provider==='commandcode'?'deepseek':aiSettings.provider;
 $('#ai-deepseek-connection').value=aiSettings.provider==='commandcode'?'commandcode':'deepseek';
 $('#ai-model').value=aiSettings.model;$('#ai-embedding').value=aiSettings.embedding;
 showAILocalStatus();
 showAIProvider(false);
 for(const field of $('#ai-settings-form').querySelectorAll('input,select'))field.disabled=false;
 $('#ai-save').disabled=false;
}
$('#ai-provider').addEventListener('change',()=>showAIProvider());
$('#ai-deepseek-connection').addEventListener('change',()=>showAIProvider());
$('#ai-embedding').addEventListener('change',showAIEmbedding);
$('#ai-settings-form').addEventListener('submit',async event=>{
 event.preventDefault();const button=$('#ai-save');button.disabled=true;
 if(!aiSettings){button.disabled=false;return;}
 try{
  aiSettings=await api('/ai-settings',{version:aiSettings.version,provider:aiProvider(),model:$('#ai-model').value,embedding:$('#ai-embedding').value,api_key:$('#ai-key').value,embedding_api_key:$('#ai-embedding-key').value},'PUT');
  $('#ai-key').value='';$('#ai-settings-result').textContent=aiSettings.notice;showAIProvider(false);showAILocalStatus();
  showIndex(await api('/status'+scopeQuery()));
 }catch(e){error(e);}finally{$('#ai-key').value='';$('#ai-embedding-key').value='';button.disabled=false;}
});

/* ------------------------------------------------------------------ chat */

async function loadThreads(){
 const rows=await api('/threads'+scopeQuery());
 const list=$('#threads');
 list.replaceChildren();
 if(!rows.length){
  list.append(emptyState('아직 대화가 없습니다','상황을 설명하면 이곳에 대화가 쌓입니다.','threads-empty'));
  return;
 }
 for(const r of rows){
  const b=el('button',r.title||'(제목 없음)');
  b.type='button';
  if(thread&&thread.id===r.id)b.setAttribute('aria-current','true');
  b.onclick=()=>loadThread(r.id).catch(error);
  list.append(b);
 }
}

function readableAnswer(text){
 // Existing saved prose gets visual line breaks; stored text stays unchanged.
 if(text.length<180||text.includes('\n')||typeof Intl.Segmenter!=='function')return text;
 return [...new Intl.Segmenter('ko',{granularity:'sentence'}).segment(text)].map(s=>s.segment.trim()).join('\n\n');
}
function addBubble(role,text,tag){
 const n=el('div',undefined,'bubble '+role);
 const shouldTag=(tag===undefined?role==='assistant':tag);
 if(shouldTag)n.append(el('span','AI 설명','tag tag-ai'));
 n.append(el('div',role==='assistant'?readableAnswer(text):text,'bubble-body'));
 $('#messages').append(n);
 return n;
}
function setBubbleText(node,text){$('.bubble-body',node).textContent=node.classList.contains('assistant')?readableAnswer(text):text;}

async function loadThread(id){
 thread=await api('/threads/'+id+scopeQuery());
 clearSelection();
 const box=$('#messages');
 box.replaceChildren();
 for(const m of thread.history)addBubble(m.role,m.content,m.role==='assistant'&&m.ai_used!==false);
 if(thread.candidates.length){
  const candidates=await Promise.all(thread.candidates.map(c=>api('/codes/'+encodeURIComponent(c.code)+scopeQuery())));
  showResults({candidates,comparisons:[],draft:thread.draft});
 }else if(thread.draft){
  showResults({candidates:[],comparisons:[],draft:thread.draft});
 }else if(!thread.history.length){
  box.append(emptyState('비어 있는 대화입니다','아래에 상황을 적으면 기존 코드를 찾아 드립니다.'));
 }
 await loadThreads();
}

function card(c,comparison){
 const n=el('article',undefined,'card');
 const head=el('div',undefined,'card-head');
 const code=el('span',c.code,'code-chip');
 code.setAttribute('translate','no');
 head.append(code,statusTag(c.status));
 n.append(head,el('p',c.message,'message'));

 const meta=el('dl',undefined,'meta');
 meta.append(metaRow('메뉴',c.menu||'미기재'));
 meta.append(metaRow('노출 조건',c.trigger||'미기재 · 재사용 전 확인'));
 const src=c.source||{};
 if(src.filename)meta.append(metaRow('출처',[src.filename,src.sheet,src.cells||src.row].filter(Boolean).join(' / ')));
 n.append(meta);

 if(comparison)n.append(el('div',comparison.label+'\n'+comparison.differences.join('\n'),'difference'));

 const actions=el('div',undefined,'card-actions');
 const copy=el('button','기획서에 복사','btn');
 copy.type='button';
 copy.onclick=()=>navigator.clipboard
  .writeText((c.source?.synthetic?'[합성 샘플 · 실제 등록 코드 아님]\n':'')+'알림 코드: '+c.code+'\n표시 문구: '+c.message+'\n기존 노출 조건: '+(c.trigger||'미기재')+'\n이번 기획의 조건: [별도 작성]')
  .then(()=>{markDone(copy,'복사됨');note('원문을 복사했습니다.');})
  .catch(error);
 const choose=el('button','이 후보 선택','btn');
 choose.type='button';
 choose.onclick=()=>{
  selected=c.code;
  if(!$('#question').value.trim())$('#question').value=c.code+'에 대해 설명해줘';
  setSelection(c.code);
  $('#question').focus();
 };
 actions.append(copy,choose);
 n.append(actions);
 return n;
}

function draftCard(d,detail,cls){
 const n=el('article',undefined,cls||'card draft-card');
 const head=el('div',undefined,'card-head');
 head.append(el('span',d.status==='registered'?'등록됨 '+d.registered_code:'미등록 초안','tag '+(d.status==='registered'?'tag-registered':'tag-draft')));
 n.append(head,el('p',d.payload.message,'message'));
 const meta=el('dl',undefined,'meta');
 if(d.owner!==undefined)meta.append(metaRow('작성자',String(d.owner)));
 if(d.catalog_version!==undefined)meta.append(metaRow('검토 기준','목록 버전 '+d.catalog_version));
 const candidates=d.payload.candidates||[];
 if(candidates.length)meta.append(metaRow('관련 후보',candidates.map(c=>c.code).join(', ')));
 if(detail)meta.append(metaRow('상태',detail));
 if(meta.childElementCount)n.append(meta);
 return n;
}

function showResults(result){
 const group=el('div',undefined,'result-group');
 const cards=el('div',undefined,'cards stagger');
 for(const c of result.candidates||[])cards.append(card(c,(result.comparisons||[]).find(x=>x.code===c.code)));
 if(cards.childElementCount)group.append(cards);
 if(result.draft){
  const slot=el('div',undefined,'draft-slot');
  slot.append(draftCard(result.draft,result.draft.status==='registered'
   ?'등록된 코드입니다. 추가 변경은 별도로 검토해주세요.'
   :'초안함에서 유사 항목 재검토 후 등록을 진행합니다.'));
  group.append(slot);
 }
 const box=$('#messages');
 box.append(group);
 box.scrollTop=box.scrollHeight;
}

/* ------------------------------------------------------------------ selection */

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

/* ------------------------------------------------------------------ compose */

$('#ask-form').addEventListener('submit',async event=>{
 event.preventDefault();
 if(busy)return;
 clearError();
 const text=$('#question').value;
 if(!text.trim())return;
 busy=true;$('#catalog-namespace').disabled=true;
 const send=$('#send');
 setBusy(send,true);
 let pending;
 try{
  if(!thread){thread=await api('/threads'+scopeQuery(),{});$('#messages').replaceChildren();}
  addBubble('user',text);
  pending=addBubble('assistant','기존 코드와 사용 조건을 확인하고 있습니다…',false);
  const payload={request_id:requestId(),expected_version:thread.version,text,action:$('#action').value,selected_code:selected,proposed_message:$('#proposed').value,menu:$('#menu').value,trigger:$('#trigger').value};
  const result=await api('/threads/'+thread.id+'/turn'+scopeQuery(),payload);
  setBubbleText(pending,result.answer);
  if(result.ai_used===true)pending.prepend(el('span','AI 설명','tag tag-ai'));
  showResults(result);
  thread.version=result.version;
  $('#question').value='';
  updateCount();
  clearSelection();
  await loadThreads();
  showIndex(await api('/status'+scopeQuery()));
 }catch(e){
  if(pending)setBubbleText(pending,'요청이 완료되지 않았습니다. 아래 오류를 확인해주세요.');
  error(e);
 }finally{
  busy=false;$('#catalog-namespace').disabled=false;setBusy(send,false);
 }
});

$('#question').addEventListener('keydown',e=>{
 if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#ask-form').requestSubmit();}
});
$('#question').addEventListener('input',updateCount);
function updateCount(){
 const n=$('#question').value.length;
 $('#compose-count').textContent=n>COUNT_AT?n+' / 4000':'';
}
$$('.example').forEach(b=>{
 b.addEventListener('click',()=>{
  const q=$('#question');
  q.value=b.dataset.query||b.textContent;
  updateCount();q.focus();
 });
});

bind('#new-thread',async()=>{
 thread=await api('/threads'+scopeQuery(),{});
 clearSelection();
 const box=$('#messages');
 box.replaceChildren();
 box.append(addBubble('assistant','새 대화를 시작했습니다. 필요한 알림 상황을 설명해주세요.',false));
 await loadThreads();
});

/* ------------------------------------------------------------------ catalogue */

let catalogQuery='',catalogStatus='all',catalogRequest=0;
const catalogPageSize=30;
function catalogFields(c){return {...(c.source?.catalog_fields||{}),...c};}
function copyCatalog(c,button){
 return api('/codes/'+encodeURIComponent(c.code)+'?namespace='+catalogNamespace).then(current=>{
  if(current.status==='retired')throw new Error('폐기된 코드는 복사할 수 없습니다.');
  return navigator.clipboard.writeText('알림 코드: '+current.code+'\n표시 문구: '+current.message+'\n기존 노출 조건: '+(current.trigger||'미기재')+'\n이번 기획의 조건: [별도 작성]');
 }).then(()=>{markDone(button,'복사됨');note('원문을 복사했습니다.');}).catch(error);
}
async function catalogDetail(code){
 const generation=inspectionGeneration;
 const c=await api('/codes/'+encodeURIComponent(code)+'?namespace='+catalogNamespace),f=catalogFields(c);
 $('#catalog-detail-title').textContent=c.code;
 if(generation!==inspectionGeneration)return;
 const host=$('#catalog-detail-content'),details=el('dl',undefined,'meta');
 host.replaceChildren(statusTag(c.status));
 host.append(el('p',f.title||c.message,'message'));
 for(const [label,value] of [['업무구분',f.business],['타입',f.message_type],['메시지코드',c.message_code||c.code],['용도',f.purpose],['title',f.title],['맞춤법검사',f.spelling_check||'미검사'],['영문 title',f.title_en],['영문 contents',f.contents_en],['추가날짜',f.added_date],['메뉴',c.menu],['노출 조건',c.trigger],['비고',c.notes],['출처',[c.source?.filename,c.source?.sheet,c.source?.cells].filter(Boolean).join(' / ')]])details.append(metaRow(label,value||'—'));
 host.append(details);
 const copy=el('button','복사','btn');copy.type='button';copy.disabled=c.status==='retired';copy.onclick=()=>copyCatalog(c,copy);
 const choose=el('button','대화에서 확인','btn');choose.type='button';choose.onclick=()=>{
  selected=c.code;setSelection(c.code);$('#question').value=c.code+'에 대해 설명해줘';$('#catalog-detail').close();selectTab($('#tab-chat')).then(()=>$('#question').focus()).catch(error);
 };
 const actions=el('div',undefined,'card-actions');actions.append(copy);actions.append(choose);host.append(actions);
 if(!$('#catalog-detail').open)$('#catalog-detail').showModal();
}
async function catalog(){
 const request=++catalogRequest;
 $('#previous').disabled=true;$('#next').disabled=true;
 const params=new URLSearchParams({namespace:catalogNamespace,q:catalogQuery,status:catalogStatus,offset:String(offset),limit:String(catalogPageSize)});
 const r=await api('/codes?'+params);
 if(request!==catalogRequest)return;
 total=r.total;
 if(offset>=total&&offset>0){offset=Math.max(0,Math.floor((total-1)/catalogPageSize)*catalogPageSize);return catalog();}
 $('#catalog-count').textContent=total?`${offset+1}–${Math.min(offset+catalogPageSize,total)} / 총 ${total}개`:'총 0개';
 const host=$('#catalog-list');host.replaceChildren();
 if(!r.items.length)host.append(emptyState('조회 결과가 없습니다',catalogQuery||catalogStatus!=='all'?'검색어 또는 사용 상태 조건을 바꿔보세요.':'DB 조회는 정상입니다. 선택한 목록에 데이터가 없습니다.'));
 else{
  const wrap=el('div',undefined,'catalog-table-wrap');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','전체 코드 표');
  const table=el('table',undefined,'catalog-table'),head=el('thead'),hr=el('tr'),body=el('tbody');
  for(const label of ['업무구분','타입','메시지코드','용도','title','맞춤법검사','영문 title','영문 contents','비고','추가날짜','상태','복사']){const th=el('th',label);th.scope='col';hr.append(th);}
  head.append(hr);table.append(head,body);
  for(const c of r.items){
   const f=catalogFields(c),row=el('tr'),id=el('td'),business=el('td'),message=el('td',undefined,'catalog-message'),purpose=el('td',f.purpose||'—'),status=el('td'),actions=el('td');
   const detail=el('button',c.code,'catalog-code');detail.type='button';detail.onclick=()=>catalogDetail(c.code).catch(error);id.append(detail);
   business.append(el('div',f.business||'—'),el('span',f.message_type||'타입 미입력','tag'));
   message.append(el('div',f.title||c.message));
   status.append(statusTag(c.status));const copy=el('button','복사','btn');copy.type='button';copy.disabled=c.status==='retired';copy.onclick=()=>copyCatalog(c,copy);actions.append(copy);
   row.append(el('td',f.business||'—'),el('td',f.message_type||'—'),id,purpose,message,el('td',f.spelling_check||'미검사'),el('td',f.title_en||'—'),el('td',f.contents_en||'—'),el('td',f.notes||'—'),el('td',f.added_date||'—'),status,actions);body.append(row);
  }
  wrap.append(table);host.append(wrap);
 }
 $('#previous').disabled=offset===0;$('#next').disabled=offset+catalogPageSize>=total;
}
bind('#previous',async()=>{offset=Math.max(0,offset-catalogPageSize);await catalog();});
bind('#next',async()=>{offset+=catalogPageSize;await catalog();});
$('#catalog-form').addEventListener('submit',event=>{event.preventDefault();catalogQuery=$('#catalog-query').value.trim();catalogStatus=$('#catalog-status').value;offset=0;catalog().catch(error);});
bind('#export',async()=>{
 const r=await fetch(base+'/export.json?namespace='+catalogNamespace,{headers:token?{Authorization:'Bearer '+token}:{}});
 if(!r.ok)throw new Error('내보내기에 실패했습니다. 잠시 후 다시 시도해주세요.');
 const url=URL.createObjectURL(await r.blob());
 const a=el('a');a.href=url;a.download=catalogNamespace==='demo'?'sample_catalog_300.json':'code-catalog.json';a.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
});

bind('#index',async()=>{
 const button=$('#index');
 setBusy(button,true);
 try{await api('/index'+scopeQuery(),{});}finally{setBusy(button,false);}
 note('검색 준비 작업을 등록했습니다. 완료 상태는 새로고침하면 확인할 수 있습니다.');
});

/* ------------------------------------------------------------------ drafts + approval */

async function loadDrafts(){
 await withSkeleton($('#draft-list'),2,async()=>{
  const drafts=await api('/drafts');
  const host=$('#draft-list');
  host.replaceChildren();
  if(!drafts.length){
   host.append(emptyState('저장된 초안이 없습니다','대화에서 신규 문구를 작성하면 이곳에서 검토하고 등록합니다.'));
   return;
  }
  for(const d of drafts)host.append(draftRow(d));
 });
}

function draftRow(d){
 const n=draftCard(d,undefined,'card draft-row');
 const actions=el('div',undefined,'card-actions');
 const review=el('button','최신 후보 재검토','btn');
 review.type='button';
 review.disabled=d.status!=='draft';
 review.onclick=async()=>{
  setBusy(review,true);
  try{
   const r=await api('/drafts/'+d.id+'/review',{});
   note('후보 '+r.candidates.length+'개와 비교했습니다.');
   await loadDrafts();
  }catch(e){error(e);}finally{setBusy(review,false);}
 };
 actions.append(review);
 if(user&&user.role==='admin'){
  const approve=el('button','등록 검토','btn');
  approve.type='button';
  approve.disabled=d.status!=='draft';
  approve.onclick=()=>{
   pendingApproval=d;
   $('#approve-message').textContent=d.payload.message;
   $('#approve-code').value='';
   $('#approve-reason').value='';
   $('#duplicate-ack').checked=false;
   $('#external-ack').checked=false;
   $('#approval').showModal();
  };
  actions.append(approve);
 }
 n.append(actions);
 return n;
}

bind('#refresh-drafts',loadDrafts);
bind('#approve-submit',async()=>{
 if(!pendingApproval)return;
 const button=$('#approve-submit');
 setBusy(button,true);
 let result;
 try{
  result=await api('/drafts/'+pendingApproval.id+'/approve',{
   expected_catalog_version:pendingApproval.catalog_version,
   expected_draft_revision:pendingApproval.revision,
   code:$('#approve-code').value,
   reason:$('#approve-reason').value,
   duplicate_ack:$('#duplicate-ack').checked,
   external_registered:$('#external-ack').checked,
  });
 }finally{setBusy(button,false);}
 $('#approval').close();
 note(result.code+'로 등록했습니다. 등록한 초안은 더 이상 수정할 수 없습니다.');
 await loadDrafts();
});

/* ------------------------------------------------------------------ audit */

async function audit(){
 const rows=await api('/audit'),host=$('#audit-list');host.replaceChildren();
 if(!rows.length){host.append(emptyState('변경 기록이 없습니다','등록·수정·승인 작업이 발생하면 사용자와 사유가 이곳에 기록됩니다.'));return;}
 const wrap=el('div',undefined,'catalog-table-wrap'),table=el('table',undefined,'catalog-table'),head=el('thead'),hr=el('tr'),body=el('tbody');
 wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','변경 기록 표');
 for(const label of ['일시','작업','항목','사용자','기록']){const th=el('th',label);th.scope='col';hr.append(th);}head.append(hr);table.append(head,body);
 for(const r of rows){
  const row=el('tr'),action=el('td'),record=el('td');action.append(el('strong',auditAction(r.action)),el('div',r.action,'muted small'));
  record.append(el('p',r.reason||'—'));
  const details=el('details');details.append(el('summary','변경 전·후 보기'),el('pre',JSON.stringify({이전:r.before,이후:r.after},null,2)));record.append(details);
  row.append(el('td',stamp(r.created_at)),action,el('td',auditEntity(r.entity)),el('td',String(r.actor)),record);body.append(row);
 }
 wrap.append(table);host.append(wrap);
}
bind('#audit-refresh',audit);

function inspectionResults(result,host){
 host.append(el('p',result.notice||'', 'muted small'));
 host.append(el('p',result.summary,result.missing_codes?.length?'difference':''));
 host.append(el('p',({'exact_lookup':'코드번호 직접 조회','catalog_rules':'원문·규칙 비교 결과 · AI 호출 없음','semantic':'의미 검색 후보 · 조건은 규칙 비교'})[result.mode]||'', 'muted small'));
 const group=el('div',undefined,'cards');
 for(const c of result.candidates){
  const comparison=result.comparisons.find(x=>x.code===c.code),item=el('article',undefined,'card');
  const head=el('div',undefined,'card-head');head.append(el('strong',c.code),statusTag(c.status));item.append(head,el('p',c.message,'message'));
  const meta=el('dl',undefined,'meta');meta.append(metaRow('메뉴',c.menu||'—'),metaRow('노출 조건',c.trigger||'미기재'));item.append(meta);
  if(comparison)item.append(el('div',comparison.label+'\n'+comparison.differences.join('\n'),'difference'));
  const detail=el('button','상세 보기','btn');detail.type='button';detail.onclick=()=>catalogDetail(c.code).catch(error);item.append(detail);group.append(item);
 }
 host.append(group);
}
function updateCatalogNamespace(){
 const changed=catalogNamespace!==$('#catalog-namespace').value;
 catalogNamespace=$('#catalog-namespace').value;inspectionGeneration++;catalogRequest++;offset=0;
 $('#catalog-scope-note').textContent=catalogNamespace==='demo'?'합성 DB 샘플 300건을 검색합니다. 샘플 대화와 검색 인덱스는 실제 목록과 분리됩니다.':'연결된 DB의 실제 알림 목록을 조회합니다.';
 for(const id of ['compare-mode','review-mode']){const select=$('#'+id);select.querySelector('[value="semantic"]').disabled=false;}
 $('#compare-results').replaceChildren();$('#review-results').replaceChildren();$('#catalog-detail').close();
 $('#action option[value=draft]').disabled=catalogNamespace==='demo';
 if(catalogNamespace==='demo'&&$('#action').value==='draft')$('#action').value='auto';
 if(changed){thread=null;clearSelection();$('#messages').replaceChildren();$('#messages').append(addBubble('assistant',catalogNamespace==='demo'?'샘플 300건에서 알림을 찾아보세요.':'실제 등록 목록에서 검색합니다.',false));if(user){loadThreads().catch(error);api('/status'+scopeQuery()).then(showIndex).catch(error);refreshCatalogHint().catch(error);}}
 if(!$('#catalog').hidden)catalog().catch(error);
}
$('#catalog-namespace').addEventListener('change',updateCatalogNamespace);
updateCatalogNamespace();
for(const kind of ['compare','review'])$('#'+kind+'-form').addEventListener('submit',async event=>{
 event.preventDefault();const form=event.currentTarget,button=form.querySelector('[type="submit"]'),host=$('#'+kind+'-results');
 const generation=inspectionGeneration;setBusy(button,true);clearError();host.replaceChildren(el('p','검토 중입니다.','muted'));
 const payload={namespace:catalogNamespace,mode:$('#'+kind+'-mode').value};
 if(kind==='compare')Object.assign(payload,{message:$('#compare-message').value,menu:$('#compare-menu').value,trigger:$('#compare-trigger').value});
 else payload.text=$('#review-text').value;
 try{
  const result=await api('/'+kind,payload);if(generation!==inspectionGeneration)return;host.replaceChildren();
  if(kind==='compare')inspectionResults(result,host);
  else for(const item of result.items){const section=el('section',undefined,'review-item');section.append(el('h3',item.line+'행 · '+item.input));inspectionResults(item,section);host.append(section);}
 }catch(e){if(generation===inspectionGeneration){host.replaceChildren();error(e);}}finally{setBusy(button,false);}
});

bind('#error-dismiss',clearError);
syncTabs();
