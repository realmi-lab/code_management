'use strict';
const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const appScript = document.currentScript || document.querySelector('script[src$="/static/app.js"]');
const appBase = appScript?.src ? new URL('../', appScript.src).pathname : new URL('.', document.baseURI).pathname;
function icon(name) {return `<svg class="ui-icon" width="18" height="18" viewBox="0 0 256 256" aria-hidden="true" focusable="false"><use href="${appBase}static/assets/icons.svg#${escape(name)}"></use></svg>`;}
const sessionKey = key => appBase==='/' ? key : key+':'+appBase;
const state = {aiSearch:true,searchSequence:0,metaSequence:0,previewSequence:0,dialogSequence:0,compareSequence:0,view:'search',namespace:sessionStorage.getItem(sessionKey('cm_namespace'))==='demo'?'demo':'live',token:sessionStorage.getItem(sessionKey('cm_token')) || '',meta:null,result:null,draftInput:null,externalReview:null,preview:null,file:null,mapping:{},generation:0,offset:0,catalogQuery:'',catalogStatus:'all',adminPassword:''};
const titles = {search:'코드 찾기',compare:'문구 비교',review:'기획서 검토',new:'새 문구 작성',drafts:'초안함',catalog:'전체 코드',import:'엑셀 가져오기',audit:'변경 기록'};
function formMemoryKey(view=state.view){return sessionKey(`cm_form:${state.namespace}:${view}`);}
function saveFormMemory(view=state.view){
 const root=$('#content');if(!root || !view)return;const saved={};
 $$('form',root).forEach((form,index)=>{const fields={};
  $$('input[name],textarea[name],select[name]',form).forEach(el=>{if(el.type==='file'||el.type==='password'||el.dataset.noMemory==='true')return;
   if(el.type==='radio'){if(el.checked)fields[el.name]=el.value;}else if(el.type==='checkbox')fields[el.name]=el.checked;else fields[el.name]=el.value;});
  if(Object.keys(fields).length)saved[form.id||`form-${index}`]=fields;});
 if(Object.keys(saved).length)sessionStorage.setItem(formMemoryKey(view),JSON.stringify(saved));
}
function restoreFormMemory(view=state.view){
 let saved;try{saved=JSON.parse(sessionStorage.getItem(formMemoryKey(view))||'{}');}catch{return;}
 const root=$('#content');if(!root)return;$$('form',root).forEach((form,index)=>{const fields=saved[form.id||`form-${index}`];if(!fields)return;
  $$('input[name],textarea[name],select[name]',form).forEach(el=>{if(el.type==='file'||el.type==='password'||el.dataset.noMemory==='true'||!Object.prototype.hasOwnProperty.call(fields,el.name))return;
   if(el.type==='checkbox')el.checked=!!fields[el.name];else if(el.type==='radio')el.checked=fields[el.name]===el.value;else el.value=fields[el.name];});});
}
function clearFormMemory(view){sessionStorage.removeItem(formMemoryKey(view));}
let toastTimer;
function toast(text) {const node=$('#toast');node.textContent=text;node.classList.remove('hidden');clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.add('hidden'),4300);}
function showAuth() {const d=$('#auth-dialog'); if(!d.open)d.showModal();$('#auth-token').focus();}
// Every response belongs to the screen, namespace and credentials that requested it.
function context() {return {generation:state.generation,namespace:state.namespace,token:state.token,dialog:state.dialogSequence};}
function isCurrent(ctx,dialog=false) {return ctx.generation===state.generation && ctx.namespace===state.namespace && ctx.token===state.token && (!dialog || ctx.dialog===state.dialogSequence);}
function closeDialog() {state.dialogSequence++;state.externalReview=null;state.adminPassword='';$('#detail-dialog').close();$('#detail-content').replaceChildren();}
function lockWorkspace() {
 state.generation++;state.previewSequence++;state.meta=null;state.result=null;state.draftInput=null;state.preview=null;state.file=null;state.mapping={};
 state.token='';sessionStorage.removeItem(sessionKey('cm_token'));closeDialog();
 $('#content').innerHTML=empty('작업 공간이 잠겼습니다.','접속 키를 입력하면 계속할 수 있습니다.');
 $('#catalog-banner').textContent='';$('#catalog-banner').classList.add('hidden');
 $('#draft-count').textContent='';$('#footer-version').textContent='';$('#engine-label').textContent='접속 대기';$('#auth-label').textContent='잠긴 작업 공간';
 clearTimeout(toastTimer);$('#toast').textContent='';$('#toast').classList.add('hidden');showAuth();
}
async function api(path, options={}) {
 const ctx=context();
 const headers={...(options.headers || {})}; if(state.token)headers.Authorization=`Bearer ${state.token}`;
 if(options.body && !(options.body instanceof FormData))headers['Content-Type']='application/json';
 const response=await fetch(appBase+path.replace(/^\//,''),{...options,headers});
 if(response.status===401){if(isCurrent(ctx))lockWorkspace();throw new Error('접속 키를 확인해주세요.');}
 if(!response.ok){let data;try{data=await response.json();}catch{data={detail:'요청을 처리하지 못했습니다.'};}
 const detail=data.detail;let message=typeof detail==='string'?detail:(Array.isArray(detail)?detail.map(e=>e.msg).join(' / '):detail?.message || '요청을 처리하지 못했습니다.');throw new Error(message);}
 if(options.blob)return response.blob();return response.json();
}
async function post(path, body) {return api(path,{method:'POST',body:JSON.stringify(body)});}
async function loadMeta() {
 const ctx=context();const sequence=++state.metaSequence;
 const meta=await api(`/api/meta?namespace=${ctx.namespace}`);
 if(!isCurrent(ctx) || sequence!==state.metaSequence)return false;
 state.meta=meta;
 $('#draft-count').textContent=state.meta.counts.drafts;
 $('#engine-label').textContent=state.meta.ai.embedding_enabled?'AI 검색':state.meta.ai.chat_enabled?'AI 연결됨':'기본 검색';
 $('#namespace-button').innerHTML=`${state.namespace==='demo'?'예시 목록':escape(state.meta.catalog_label || '실제 목록')} ${icon('arrows-left-right')}`;
 $('#demo-banner').classList.toggle('hidden',state.namespace!=='demo');
 const notice=$('#catalog-banner');const noticeText=state.namespace==='live'?(meta.catalog_notice || ''):'';notice.innerHTML=noticeText?`<details><summary>사진 데이터 · 원본 확인 필요</summary><p>${escape(noticeText)}</p></details>`:'';notice.classList.toggle('hidden',!noticeText);
 const returnButton=$('#demo-banner button');returnButton.textContent='돌아가기';
 $('#auth-label').textContent=state.meta.authenticated?'접속됨':'';const lock=$('[data-action="lock"]');if(lock)lock.classList.toggle('hidden',!state.meta.authenticated);
 $('#footer-version').textContent=`v${state.meta.version} · ${state.meta.authority==='excel'?'엑셀 기준':'시스템 기준'}`;
 return true;
}
function heading(title,desc='',action='') {return `<div class="page-heading"><div><h1>${escape(title)}</h1>${desc?`<p>${escape(desc)}</p>`:''}</div>${action}</div>`;}
function loading(text='불러오는 중') {return `<div class="loading" role="status"><div class="loading-lines" aria-hidden="true"><span></span><span></span><span></span></div><span class="loading-label">${escape(text)}</span></div>`;}
function errorBox(text) {return `<div class="alert error" role="alert">${escape(text)}</div>`;}
function empty(title,desc,button='') {return `<div class="empty"><h3>${escape(title)}</h3>${desc?`<p>${escape(desc)}</p>`:''}${button}</div>`;}
function catalogLabel() {return state.namespace==='demo'?'예시 데이터':state.meta?.catalog_label || '실제 목록';}
function sourceWarning(row) {
 const s=row.source || {};const photo=s.kind==='photo_transcription' || !!s.original_image;
 if(!photo && !s.review_required && !s.ocr_review)return '';
 const notes=s.review_notes || s.ocr_review;const detail=Array.isArray(notes)?notes.join(' '):typeof notes==='string'?notes:'';
 return `<details class="source-review"><summary>원본 확인 필요</summary><p>${escape(detail || (photo?'사진에서 옮긴 테스트 자료입니다.':'원본을 확인해주세요.'))}</p></details>`;
}
function recordFields(row) {return [['business','업무구분'],['message_type','타입'],['purpose','용도'],['title','타이틀'],['title_en','영문타이틀'],['message_en','영문컨텐츠']].map(([key,label])=>`<dt>${label}</dt><dd>${escape(row[key] || '—')}</dd>`).join('');}
function cardFields(row) {const fields=[row.business,row.message_type,row.purpose].filter(Boolean);return fields.length?`<div class="card-fields">${fields.map(value=>`<span>${escape(value)}</span>`).join('<span aria-hidden="true">·</span>')}</div>`:'';}
function sourceText(row) {const s=row.source || {};if(s.kind==='demo')return '예시 데이터 · 실제 회사 목록 아님';if(s.kind==='photo_transcription')return ['사진 인식 테스트',s.original_image || s.filename,s.sheet,s.cells].filter(Boolean).join(' · ');if(s.filename)return [s.filename,s.sheet,s.cells].filter(Boolean).join(' · ');return s.kind==='approved_revision'?'승인된 문구 변경':s.kind==='approved'?'승인 후 등록':'원본 위치 미확인';}
function tagFor(match) {if(!match)return '';const tone=match.verdict==='retired'?'bad':match.verdict==='different_conditions'?'warn':['exact_code','reuse_candidate'].includes(match.verdict)?'good':'purple';const label={exact_code:'번호 일치',related:'관련 문구',same_wording:'같은 문구',different_conditions:'조건 다름',reuse_candidate:'문구·조건 일치',retired:'폐기',similar:'유사 문구'}[match.verdict] || match.label;return `<span class="tag ${tone}">${escape(label)}</span>`;}
function codeCard(row,index=0) {
 const match=row.match || {verdict:row.status==='retired'?'retired':'similar',label:'등록 문구',differences:[]};
 const context=[row.menu,row.trigger].filter(Boolean);const source=row.source || {};
 const differences=(match.differences || []).map(text=>text.startsWith('문구 유사성만으로')?'사용 조건 확인 필요':text);
 return `<article class="code-card ${index===0?'featured':''}"><div class="card-identity"><div class="card-top"><button class="code-id" data-action="detail" data-code="${escape(row.code)}">${escape(row.code)}</button>${tagFor(match)}</div>${cardFields(row)}</div><div class="card-content">${row.title?`<div class="card-title"><strong>${escape(row.title)}</strong></div>`:''}<p class="card-message">${escape(row.message)}</p>${context.length?`<div class="card-context">${context.map(escape).join(' · ')}</div>`:''}${differences.length?`<div class="difference ${match.verdict==='different_conditions'?'':'neutral'}">${escape(differences.join(' '))}</div>`:''}${sourceWarning(row)}</div><div class="card-bottom"><span class="source" title="${escape(sourceText(row))}">${escape(source.original_image || source.filename || (source.kind==='demo'?'예시 데이터':''))}</span><button data-action="copy" data-code="${escape(row.code)}" ${row.status==='retired'?'disabled':''}>${icon('copy')}복사</button></div></article>`;
}
function resultsHTML(data) {
 const mode={exact:'번호 직접 조회',basic:'기본 검색',ai_query:'AI 검색어 보완',embedding:'AI 의미 검색',embedding_partial:'AI + 기본 검색'}[data.mode] || '검색 결과';
 return `<div class="result-header"><h2>검색 결과 <span class="muted small">${data.results.length}</span></h2><small>${mode}</small></div>${data.missing_codes?.length?`<p class="result-summary">${escape(data.summary)}</p>`:''}${data.notice?`<div class="alert info">${escape(data.notice)}</div>`:''}${data.ai_queries?.length?`<details class="result-details"><summary>AI 검색어</summary><p>${data.ai_queries.map(escape).join(' · ')}</p></details>`:''}${data.results.length?`<div class="result-grid">${data.results.map(codeCard).join('')}</div>`:empty('검색 결과가 없습니다.','다른 표현으로 검색해보세요.',`<button class="button soft" data-action="view" data-view="new">새 문구 작성</button>`)}`;
}
function guideHTML() {
 if(state.meta.counts.total)return '';
 return empty('등록된 코드가 없습니다.','',`<button class="button primary" data-action="view" data-view="import">엑셀 가져오기</button> <button class="button" data-action="namespace">예시 보기</button>`);
}
function renderSearch(compare=false) {
 const photo=state.namespace==='live' && !!state.meta.catalog_notice;
 const prompts=photo?[['자산이 부족해서 신청할 수 없을 때 안내','자산 부족'],['쿠폰 구매가 완료됐다는 안내','구매 완료'],['S-C-2','S-C-2']]:[['인증 전에 30초 기다리라는 알림','인증 대기'],['이미 가입된 전화번호 안내','중복 가입'],['AT-1923','AT-1923']];
 return `${heading(compare?'문구 비교':'코드 찾기','',`<button class="button" data-action="view" data-view="new">${icon('plus')}새 문구</button>`)}<div class="search-workspace"><section class="panel search-panel"><form id="search-form" data-mode="${compare?'compare':'search'}"><label class="sr-only-label" for="query">${compare?'비교할 문구':'상황 또는 코드번호'}</label><div class="search-input-wrap"><span class="search-input-icon">${icon(compare?'arrows-left-right':'magnifying-glass')}</span><textarea id="query" name="query" class="query-area" placeholder="${compare?'비교할 문구를 입력하세요':'상황이나 코드번호를 입력하세요'}" required maxlength="3000">${escape(state.result?.query || '')}</textarea></div>${compare?`<details class="help-details"><summary>메뉴·조건 추가</summary><div class="field-pair"><label>메뉴<input name="menu" maxlength="200"></label><label>노출 조건<input name="trigger" maxlength="1000"></label></div></details>`:''}<div class="form-actions"><div class="search-options">${!compare && state.meta.ai.chat_enabled?`<label class="check" title="검색 질문을 연결된 AI에 전송합니다."><input type="checkbox" name="use_ai" ${state.aiSearch?'checked':''}>AI 검색</label>`:''}<label class="check"><input type="checkbox" name="include_retired">폐기 포함</label></div><button class="button primary" type="submit">${compare?'비교':'검색'} ${icon('arrow-right')}</button></div></form>${!compare?`<div class="search-examples">${prompts.map(([query,label])=>`<button class="chip" data-query="${escape(query)}">${escape(label)}</button>`).join('')}</div>`:''}</section><div class="search-overview"><span>${state.meta.counts.total.toLocaleString()}개 코드</span>${!compare && state.meta.ai.chat_enabled?'<details class="help-details"><summary>AI 안내</summary><p>검색 질문을 연결된 AI에 전송합니다. 결과는 등록 문구로 표시됩니다.</p></details>':''}</div><section id="results" aria-live="polite">${state.result?.data?resultsHTML(state.result.data):guideHTML()}</section></div>`;
}
function renderNew() {
 const d=state.draftInput || {};
 return `${heading(d.editing?'초안 수정':d.kind==='revision'?'문구 변경안':'새 문구','초안 · 정식 등록 전')}<div class="workspace"><section class="panel">${d.target_code?`<p class="mono">${escape(d.target_code)}</p>`:''}<form id="draft-form" class="field-group"><label>문구<textarea name="message" id="draft-message" maxlength="4000" required placeholder="문구를 입력하세요">${escape(d.message || '')}</textarea></label><div class="field-pair"><label>메뉴<input name="menu" maxlength="200" value="${escape(d.menu || '')}"></label><label>노출 조건<input name="trigger" maxlength="1000" value="${escape(d.trigger || '')}"></label></div><label>비고<input name="notes" maxlength="2000" value="${escape(d.notes || '')}"></label>${d.editing?`<label>수정 이유<input name="edit_reason" required maxlength="1000"></label><p class="section-note">수정 후 등록 요청을 다시 확인해주세요.</p>`:`<label class="check"><input type="checkbox" name="use_ai" ${state.meta.ai.chat_enabled?'':'disabled'}>AI 문구 다듬기${state.meta.ai.chat_enabled?'':' · 미연결'}</label>`}<div class="form-actions"><button type="button" class="button" data-action="draft-compare">유사 문구</button><button type="submit" class="button primary">${d.editing?'수정 저장':'초안 저장'}</button></div><div id="draft-notice"></div></form><details class="help-details"><summary>등록 안내</summary><p>${state.meta.authority==='excel'?'정식 번호는 엑셀 담당자가 확정합니다.':'초안 검토 후 승인하면 등록됩니다.'}</p><p>AI 다듬기 선택 시 문구·조건과 관련 후보를 연결된 AI에 전송합니다.</p></details></section><section id="draft-results" aria-live="polite">${empty('유사 문구 확인','저장 전 기존 문구를 비교해보세요.')}</section></div>`;
}
async function renderDrafts() {
 const d=await api(`/api/drafts?namespace=${state.namespace}`);
 return `${heading('초안함','',`<button class="button" data-action="export-drafts">${icon('arrow-down')}초안 내보내기</button>`)}${d.items.length?d.items.map(r=>`<article class="draft-card"><div><span class="tag ${r.state==='registered'?'good':r.state==='pending_external'?'warn':'purple'}">${({draft:'작성 중',registered:'정식 등록',pending_external:'엑셀 등록 요청'})[r.state] || escape(r.state)}</span> <span class="small muted">${r.kind==='revision'?escape(r.target_code)+' 변경':'신규 문구'} · ${new Date(r.created_at).toLocaleDateString('ko-KR')}</span><h3>${escape(r.message)}</h3><p>${escape(r.menu || '메뉴 미입력')} · ${escape(r.trigger || '노출 조건 미입력')}</p>${r.registered_code?`<p class="mono">${escape(r.registered_code)}</p>`:''}</div><div class="draft-actions"><button class="button compact ${r.state==='registered'?'':'soft'}" data-action="review-draft" data-id="${escape(r.id)}">${r.state==='registered'?'등록 내용 보기':'검토하기 →'}</button></div></article>`).join(''):empty('초안이 없습니다.','',`<button class="button soft" data-action="view" data-view="new">${icon('plus')}새 문구 작성</button>`)}`;
}
async function renderCatalog() {
 const params=new URLSearchParams({namespace:state.namespace,q:state.catalogQuery,status:state.catalogStatus,offset:String(state.offset),limit:'30'});
 const d=await api('/api/codes?'+params);
 return `${heading('전체 코드',`${d.total.toLocaleString()}개`,`<button class="button primary" data-action="view" data-view="import">${icon('upload-simple')}엑셀 가져오기</button>`)}<form class="toolbar" id="catalog-form"><input name="q" aria-label="목록 검색" placeholder="코드번호, 타이틀, 컨텐츠, 업무구분 검색" value="${escape(state.catalogQuery)}"><select name="status" aria-label="사용 상태"><option value="all" ${state.catalogStatus==='all'?'selected':''}>모든 상태</option><option value="active" ${state.catalogStatus==='active'?'selected':''}>사용 중</option><option value="retired" ${state.catalogStatus==='retired'?'selected':''}>폐기</option></select><button class="button" type="submit">검색</button><div class="right"><button class="button" type="button" data-action="export-codes">${icon('arrow-down')}목록 내보내기</button></div></form>${d.items.length?`<div class="table-wrap"><table><thead><tr><th>메시지코드</th><th>업무구분 · 타입</th><th>타이틀 · 컨텐츠</th><th>용도</th><th>상태</th><th></th></tr></thead><tbody>${d.items.map(r=>`<tr><td><button class="code-id" data-action="detail" data-code="${escape(r.code)}">${escape(r.code)}</button></td><td class="small"><div>${escape(r.business || '—')}</div><span class="tag">${escape(r.message_type || '타입 미입력')}</span></td><td class="message-cell">${r.title?`<strong class="table-title">${escape(r.title)}</strong>`:''}<div>${escape(r.message)}</div>${sourceWarning(r)}</td><td class="small muted">${escape(r.purpose || '—')}</td><td><span class="tag ${r.status==='active'?'good':'bad'}">${r.status==='active'?'사용 중':'폐기'}</span></td><td><button class="button compact" data-action="copy" data-code="${escape(r.code)}" ${r.status==='retired'?'disabled':''}>${icon('copy')}복사</button></td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>${state.offset+1}–${Math.min(state.offset+30,d.total)} / ${d.total}</span><div><button class="button compact" data-action="prev-page" ${state.offset===0?'disabled':''}>이전</button><button class="button compact" data-action="next-page" ${state.offset+30>=d.total?'disabled':''}>다음</button></div></div>`:empty('표시할 코드가 없습니다.','검색 조건을 확인해주세요.')}`;
}
function renderImport() {
 return `${heading('엑셀 가져오기','',`<button class="button" data-action="template">양식 다운로드</button>`)}<section class="panel"><form id="import-form"><label class="upload-box">파일 선택<small>XLSX · CSV / 최대 8MB</small><input id="upload-file" type="file" name="file" accept=".xlsx,.csv" required></label><div class="form-actions"><span id="file-note" class="muted small">${state.file?escape(state.file.name)+' · 선택 유지됨':'미리보기 후 반영'}</span><button class="button primary" type="submit">미리보기 →</button></div></form><details class="help-details"><summary>가져오기 안내</summary><p>필수: 메시지코드·컨텐츠. 여러 시트, 최대 10,000건.</p><p>원문이 다른 항목은 확인 후 반영합니다.</p></details></section><section id="import-preview" aria-live="polite">${state.preview?previewHTML(state.preview):''}</section>`;
}
function mappingHTML(p) {
 const fields=[['business','업무구분'],['message_type','타입'],['code','메시지코드'],['purpose','용도'],['title','타이틀'],['message','컨텐츠'],['title_en','영문타이틀'],['message_en','영문컨텐츠'],['notes','비고'],['menu','사용 메뉴'],['trigger','노출 조건'],['status','상태']];
 return `<details class="mapping-panel"><summary>열 연결</summary><p class="small muted">각 항목에 해당하는 열을 선택하세요.</p>${p.sheets.map((s,idx)=>`<div class="sheet-mapping" data-sheet="${escape(s.name)}"><h3>${escape(s.name)}</h3><div class="mapping-fields"><label>헤더 행<input type="number" data-map="header_row" min="1" max="20000" value="${Number(s.header_row)||1}"></label>${fields.map(([f,label])=>`<label>${label}<select data-map="${f}"><option value="">선택 안 함</option>${Array.from({length:100},(_,i)=>{let n=i+1,s='';while(n>0){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;}).map(col=>`<option value="${col}" ${s.detected_columns?.[f]===col?'selected':''}>${col}열${s.headers.find(h=>h.column===col)?' · '+escape(s.headers.find(h=>h.column===col).label):''}</option>`).join('')}</select></label>`).join('')}</div><details><summary class="small muted">처음 ${s.sample_rows.length}개 행 확인</summary><pre>${escape(s.sample_rows.map(r=>`${r.row}행: `+Object.entries(r.values).map(([k,v])=>`${k}=${v}`).join(' | ')).join('\n'))}</pre></details></div>`).join('')}<button class="button soft" data-action="remap">다시 미리보기</button></details>`;
}
function previewHTML(p) {
 return `${mappingHTML(p)}<div class="counts-row"><span class="count-pill">추가 예정<strong>${p.counts.new}</strong></span><span class="count-pill">기존과 동일<strong>${p.counts.unchanged}</strong></span><span class="count-pill">번호 충돌<strong>${p.counts.conflict}</strong></span><span class="count-pill">오류<strong>${p.errors.length}</strong></span></div>${p.errors.length?`<div class="alert error">${p.errors.map(escape).join('<br>')}</div>`:''}${p.warnings.length?`<div class="alert">${p.warnings.map(escape).join('<br>')}</div>`:''}${p.records.length?`<div class="table-wrap"><table><thead><tr><th>처리</th><th>코드번호</th><th>문구</th><th>원본 위치</th></tr></thead><tbody>${p.records.slice(0,80).map(r=>`<tr><td><span class="tag ${r.action==='conflict'?'bad':r.action==='new'?'good':''}">${({new:'추가',conflict:'충돌',unchanged:'동일'})[r.action]}</span></td><td class="mono">${escape(r.code)}</td><td class="message-cell">${escape(r.message)}<details class="field-preview"><summary>엑셀 세부 항목</summary><dl class="details-grid">${recordFields(r)}</dl></details>${r.existing?`<label class="check"><input type="checkbox" class="approve-update" data-code="${escape(r.code)}">이 원문으로 갱신</label><div class="alert">기존 문구: ${escape(r.existing.message)}<br>기존 메뉴/조건: ${escape(r.existing.menu)} / ${escape(r.existing.trigger)}<details><summary>기존 엑셀 세부 항목</summary><dl class="details-grid">${recordFields(r.existing)}</dl></details></div>`:''}${r.same_message_codes?.length?`<p class="small error-text">같은 문구: ${escape(r.same_message_codes.join(', '))}${r.same_message_count>r.same_message_codes.length?' 외 '+(r.same_message_count-r.same_message_codes.length)+'개':''}</p>`:''}</td><td class="small muted">${escape(r.source.sheet)} · ${escape(r.source.cells)}</td></tr>`).join('')}</tbody></table></div>${p.records.length>80?'<p class="section-note">처음 80건 표시 · 집계는 전체 기준</p>':''}`:''}${p.counts.conflict?'<label class="section-note">선택한 항목의 원문 갱신 이유<input id="update-reason" maxlength="1000" placeholder="승인된 엑셀 개정 내용 확인 등"></label>':''}<div class="form-actions">${p.counts.conflict?'<label class="check"><input id="skip-conflicts" type="checkbox">미선택 충돌 제외</label>':'<span class="small muted">새 항목만 추가</span>'}<button class="button primary" data-action="commit-import" data-import-id="${escape(p.import_id)}" ${p.errors.length || !p.records.length?'disabled':''}>${p.counts.conflict?'선택한 내용 반영':p.counts.new?p.counts.new+'개 새 항목 가져오기':'기존 목록 확인 완료'}</button></div>`;
}
function renderReview() {
 return `${heading('기획서 검토')}<div class="workspace"><section class="panel"><form id="review-form" class="field-group"><label>문구 · 코드번호<textarea name="text" class="max-field" required maxlength="16000" placeholder="한 줄에 하나씩 입력하세요"></textarea></label><p class="small muted">최대 30줄</p><button class="button primary" type="submit">검토</button></form></section><section id="review-results" aria-live="polite"></section></div>`;
}
async function renderAudit() {
 const d=await api(`/api/audit?namespace=${state.namespace}`);
 const actions={'code.imported':'코드 가져오기','code.approved':'신규 등록 승인','code.revised':'문구 변경 승인','code.status':'사용 상태 변경','code.source_updated':'확인 후 엑셀 원문 갱신','draft.created':'초안 작성','draft.updated':'초안 수정','draft.external_linked':'엑셀 등록 완료 연결','draft.handoff':'엑셀 등록 요청','import.committed':'가져오기 완료'};
 return `${heading('변경 기록')}<div class="table-wrap"><table><thead><tr><th>일시</th><th>작업</th><th>항목</th><th>기록</th></tr></thead><tbody>${d.items.map(r=>`<tr><td class="small muted">${escape(new Date(r.created_at).toLocaleString('ko-KR'))}</td><td>${escape(actions[r.action] || r.action)}</td><td class="small mono">${escape(r.entity)}</td><td class="small">${escape(r.reason)}<details><summary class="muted">변경 전·후 보기</summary><pre>${escape(JSON.stringify({이전:r.before_json?JSON.parse(r.before_json):null,이후:r.after_json?JSON.parse(r.after_json):null},null,2))}</pre></details></td></tr>`).join('') || '<tr><td colspan="4" class="muted">아직 변경 기록이 없습니다.</td></tr>'}</tbody></table></div>`;
}
async function navigate(view,{keepResult=false}={}) {
 if(!titles[view])return;
 saveFormMemory(state.view);state.view=view;if(!keepResult)state.result=null;
 const gen=++state.generation;closeDialog();
 $$('.nav-item').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.setAttribute('aria-current',b.dataset.view===view?'page':'false');});
 $('#breadcrumb').textContent=titles[view];const content=$('#content');content.innerHTML=loading('불러오는 중');
  try {if(!await loadMeta() || gen!==state.generation)return;let html;
 if(view==='search'||view==='compare')html=renderSearch(view==='compare');
 else if(view==='new')html=renderNew();else if(view==='drafts')html=await renderDrafts();
 else if(view==='catalog')html=await renderCatalog();else if(view==='import')html=renderImport();
 else if(view==='review')html=renderReview();else html=await renderAudit();
 if(gen===state.generation){content.innerHTML=html;restoreFormMemory(view);}
 }catch(error){if(gen===state.generation)content.innerHTML=errorBox(error.message);}
}
async function download(path,filename) {const ctx=context();const blob=await api(path,{blob:true});if(!isCurrent(ctx))return;const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);}
async function copy(text) {try{await navigator.clipboard.writeText(text);}catch{const t=document.createElement('textarea');t.value=text;document.body.append(t);t.select();const ok=document.execCommand('copy');t.remove();if(!ok)throw new Error('복사 권한이 없습니다. 상세 화면에서 문구를 직접 선택해주세요.');}toast('복사했습니다.');}
function openDialog(html) {state.dialogSequence++;$('#detail-content').innerHTML=`<div class="dialog-body">${html}</div>`;if(!$('#detail-dialog').open)$('#detail-dialog').showModal();}
async function dialogData(path) {
 const ctx=context();const sequence=++state.dialogSequence;
 try {const data=await api(path);return isCurrent(ctx) && sequence===state.dialogSequence?data:null;}
 catch(error){if(isCurrent(ctx) && sequence===state.dialogSequence)toast(error.message);return null;}
}
function dialogHeader(title) {return `<div class="dialog-header"><h2 id="detail-title">${escape(title)}</h2><button class="close-button" data-action="close-dialog" aria-label="닫기">${icon('x')}</button></div>`;}
async function detail(code) {
 const r=await dialogData(`/api/codes/${encodeURIComponent(code)}?namespace=${state.namespace}`);if(!r)return;
 openDialog(`${dialogHeader(r.code)}<span class="tag ${r.status==='active'?'good':'bad'}">${r.status==='active'?'사용 중':'폐기'}</span><p class="small muted">등록 원문 · 버전 ${r.revision}</p><p class="detail-field-label">컨텐츠</p><div class="dialog-message">${escape(r.message)}</div>${sourceWarning(r)}<dl class="details-grid">${recordFields(r)}<dt>등록 메뉴</dt><dd>${escape(r.menu || '미확인')}</dd><dt>노출 조건</dt><dd>${escape(r.trigger || '등록된 정보 없음')}</dd><dt>비고</dt><dd>${escape(r.notes || '—')}</dd><dt>원본 근거</dt><dd>${escape(sourceText(r))}</dd><dt>기준</dt><dd>${state.namespace==='demo'?'합성 예시. 실제 회사 코드가 아닙니다.':'등록된 자료 기준'}</dd></dl><div class="dialog-actions"><button class="button primary" data-action="copy" data-code="${escape(r.code)}" ${r.status==='retired'?'disabled':''}>${icon('copy')}복사</button><button class="button" data-action="revision" data-code="${escape(r.code)}">문구 변경 초안</button>${state.meta.authority==='system'?`<button class="button ${r.status==='active'?'danger':''}" data-action="status-prompt" data-code="${escape(r.code)}" data-status="${r.status==='active'?'retired':'active'}" data-revision="${r.revision}">${r.status==='active'?'폐기 처리':'다시 사용'}</button>`:''}</div>`);
}
async function reviewDraft(id) {
 const d=await dialogData(`/api/drafts/${id}/review?namespace=${state.namespace}`);if(!d)return;const r=d.draft;
 openDialog(`${dialogHeader(r.state==='registered'?'등록된 초안':'초안 검토')}<div class="dialog-message">${escape(r.message)}</div><p class="small muted">${escape(r.menu || '메뉴 미입력')} · ${escape(r.trigger || '조건 미입력')}</p>${r.state!=='registered'?`<button class="button" data-action="edit-draft" data-id="${escape(r.id)}">초안 수정</button>`:''}<details><summary class="small">현재 목록의 관련 후보 ${d.comparison.results.length}개 확인</summary><div class="section-note">${d.comparison.results.map(codeCard).join('')}</div></details>${r.state==='registered'?`<div class="alert info">등록된 코드: ${escape(r.registered_code)}</div>`:state.meta.authority==='excel'?`<div class="alert">엑셀 담당자 확인 후 정식 등록됩니다.</div><div class="dialog-actions"><button class="button primary" data-action="handoff" data-id="${escape(r.id)}" data-revision="${r.revision}">엑셀 등록 요청</button><button class="button" data-action="export-drafts">${icon('arrow-down')}초안 내보내기</button>${r.state==='pending_external'?`<button class="button soft" data-action="external-matches" data-id="${escape(r.id)}">엑셀 등록 확인 →</button>`:''}</div>`:`<form id="approve-form" data-id="${escape(r.id)}" data-revision="${r.revision}" data-version="${d.comparison.catalog_version}" class="field-group"><div class="alert info">${r.kind==='revision'?'동일 코드의 문구가 바뀝니다. 사용처 영향은 기획자가 별도 검토해야 합니다.':'코드번호는 입력한 번호 또는 관리자가 설정한 규칙으로만 발급합니다.'}</div>${r.kind==='revision'?`<input type="hidden" name="code" value="${escape(r.target_code)}">`:`<div class="field-pair"><label>확정한 코드번호<input name="code" placeholder="예: AT-1924" maxlength="40"></label><label>또는 번호 발급 규칙<select name="prefix"><option value="">번호 직접 입력</option>${Object.keys(state.meta.code_rules).map(p=>`<option value="${escape(p)}">${escape(p)} · 설정된 순번 발급</option>`).join('')}</select></label></div>`}<label>등록·변경 이유<input name="reason" required maxlength="1000" placeholder="기존 코드와 다른 점 또는 변경 승인 이유"></label><label class="check"><input type="checkbox" name="duplicate_ack">동일·유사 문구와 사용 조건을 확인했습니다.</label><button class="button primary" type="submit">검토 완료 · ${r.kind==='revision'?'문구 변경 승인':'정식 등록'}</button><div id="approve-error"></div></form>`}`);
}
function providerLabel(provider){return {'claude-code':'Claude Code','command-code':'Command Code','openai-compatible':'OpenAI-compatible'}[provider]||provider;}
function settingsDialog() {
 const m=state.meta;if(!m)return;
 openDialog(`${dialogHeader('설정')}<dl class="details-grid"><dt>공식 목록</dt><dd>${m.authority==='excel'?'엑셀':'시스템'}</dd><dt>AI</dt><dd>${m.ai.chat_enabled?escape(providerLabel(m.ai.provider))+' · '+escape(m.ai.chat_model):'미연결'}${m.ai.reasoning_effort?' · '+escape(m.ai.reasoning_effort.toUpperCase()):''}</dd><dt>검색</dt><dd>${m.ai.embedding_enabled?'의미 검색':m.ai.chat_enabled?'AI 검색어 보완':'기본 검색'}</dd></dl><div class="dialog-actions"><button class="button primary" data-action="admin-ai">관리자 LLM 설정</button>${m.ai.embedding_enabled?'<button class="button soft" data-action="reindex">검색 데이터 준비</button>':''}</div><details class="help-details"><summary>AI 전송 안내</summary><p>AI 검색은 질문을 전송합니다. 문구 다듬기는 입력 문구·조건과 관련 후보를 전송합니다.</p></details>`);
}
function adminUnlockDialog(){
 openDialog(`${dialogHeader('관리자 확인')}<form id="admin-auth-form" class="field-group"><label>관리자 비밀번호<input type="password" name="password" autocomplete="current-password" required maxlength="128"></label><div id="admin-auth-error"></div><button class="button primary" type="submit">확인</button></form>`);
}
function adminAIConfigDialog(c){
 const models='<datalist id="claude-models"><option value="claude-sonnet-5"><option value="claude-opus-5"><option value="claude-opus-4-8"><option value="claude-fable-5"></datalist>';
 openDialog(`${dialogHeader('LLM 설정')}<form id="admin-ai-form" class="field-group"><label class="check"><input type="checkbox" name="enabled" ${c.enabled?'checked':''}>LLM 사용</label><label>Provider<select name="provider"><option value="claude-code" ${c.provider==='claude-code'?'selected':''}>Claude Code</option><option value="openai-compatible" ${c.provider==='openai-compatible'?'selected':''}>OpenAI-compatible API</option><option value="command-code" ${c.provider==='command-code'?'selected':''}>Command Code (기존)</option></select></label><label>모델<input name="model" list="claude-models" value="${escape(c.model||'claude-sonnet-5')}" required maxlength="160">${models}</label><label>API key<input type="password" name="api_key" autocomplete="new-password" maxlength="1024" placeholder="${c.key_configured?'등록된 key 유지 · 변경할 때만 입력':'API key 입력'}"><span class="small muted">key는 화면에 다시 표시하지 않으며 서버의 Git 제외 파일에만 저장합니다.</span></label><label>OpenAI-compatible Base URL<input name="base_url" value="${escape(c.base_url||'')}" maxlength="500" placeholder="https://.../v1"></label><label>추론 강도<select name="reasoning_effort"><option value="low" ${c.reasoning_effort==='low'?'selected':''}>Low</option><option value="high" ${c.reasoning_effort==='high'?'selected':''}>High</option><option value="max" ${c.reasoning_effort==='max'?'selected':''}>Max</option></select></label><div class="alert info">Claude Code: ${c.claude_code_available?'설치됨':'실행 파일 없음'} · API key 전용 · bare/restricted · 세션 저장 안 함</div><div id="admin-ai-error"></div><button class="button primary" type="submit">저장하고 적용</button></form>`);
}

async function previewFile() {
 if(!state.file)throw new Error('파일을 선택해주세요.');
 const ctx=context();const sequence=++state.previewSequence;const file=state.file;state.preview=null;
 const data=new FormData();data.append('file',file);data.append('namespace',ctx.namespace);data.append('mapping',JSON.stringify(state.mapping));
 const container=$('#import-preview');container.innerHTML=loading('파일 확인 중');
 try{const preview=await api('/api/imports/preview',{method:'POST',body:data});if(!isCurrent(ctx) || sequence!==state.previewSequence || file!==state.file || !container.isConnected)return;state.preview=preview;container.innerHTML=previewHTML(preview);}
 catch(e){if(isCurrent(ctx) && sequence===state.previewSequence && container.isConnected)container.innerHTML=errorBox(e.message);}
}
async function doSearch(form) {
 const f=new FormData(form);const query=f.get('query');const gen=state.generation;const sequence=++state.searchSequence;const target=$('#results');
 const mode=form.dataset.mode;const useAI=mode!=='compare' && !!f.get('use_ai');if(mode!=='compare')state.aiSearch=useAI;
 target.innerHTML=loading(useAI?'AI 검색 중':'검색 중');
 const req={query,namespace:state.namespace,limit:8,include_retired:!!f.get('include_retired'),menu:f.get('menu')||'',trigger:f.get('trigger')||'',use_ai:useAI};
 try{const data=await post(mode==='compare'?'/api/compare':'/api/search',mode==='compare'?{...req,message:query}:req);if(gen===state.generation && sequence===state.searchSequence){state.result={query,data};target.innerHTML=resultsHTML(data);}}catch(e){if(gen===state.generation && sequence===state.searchSequence)target.innerHTML=errorBox(e.message);}
}
document.addEventListener('submit',async event=>{
 const form=event.target;if(!(form instanceof HTMLFormElement))return;event.preventDefault();
 if(form.dataset.pending==='true')return;
 form.dataset.pending='true';
 const ctx=context();const inDialog=!!form.closest('#detail-dialog');
 const current=()=>isCurrent(ctx,inDialog) && form.isConnected;
 const submit=form.querySelector('button[type=submit]');if(submit)submit.disabled=true;
 try {
 if(form.id==='auth-form') {state.token=new FormData(form).get('token').trim();sessionStorage.setItem(sessionKey('cm_token'),state.token);if(!await loadMeta())return;$('#auth-dialog').close();$('#auth-token').value='';$('#auth-error').textContent='';await navigate(state.view);}
 else if(form.id==='admin-auth-form'){const password=String(new FormData(form).get('password')||'');const c=await post('/api/admin/ai/state',{password});if(!current())return;state.adminPassword=password;adminAIConfigDialog(c);}
 else if(form.id==='admin-ai-form'){const f=new FormData(form);const payload={password:state.adminPassword,enabled:!!f.get('enabled'),provider:f.get('provider'),model:String(f.get('model')||'').trim(),api_key:String(f.get('api_key')||'').trim()||null,base_url:String(f.get('base_url')||'').trim(),reasoning_effort:f.get('reasoning_effort')};await post('/api/admin/ai/config',payload);if(!current())return;state.adminPassword='';if(await loadMeta()&&current()){toast('LLM 설정을 적용했습니다.');settingsDialog();}}
 else if(form.id==='search-form')await doSearch(form);
 else if(form.id==='catalog-form'){const f=new FormData(form);state.catalogQuery=f.get('q');state.catalogStatus=f.get('status');state.offset=0;await navigate('catalog');}
 else if(form.id==='import-form'){state.file=$('#upload-file').files[0] || state.file;state.mapping={};await previewFile();}
 else if(form.id==='draft-form') {const f=new FormData(form);const d={namespace:state.namespace,message:f.get('message'),menu:f.get('menu'),trigger:f.get('trigger'),notes:f.get('notes'),use_ai:!!f.get('use_ai'),kind:state.draftInput?.kind||'new',target_code:state.draftInput?.target_code||null};
 if(state.draftInput?.editing){const original=state.draftInput;await api(`/api/drafts/${original.id}`,{method:'PATCH',body:JSON.stringify({namespace:ctx.namespace,expected_revision:original.revision,message:d.message,menu:d.menu,trigger:d.trigger,notes:d.notes,reason:f.get('edit_reason')})});if(!current())return;state.draftInput=null;toast('초안을 수정했습니다. 등록 요청 전 다시 검토해주세요.');await navigate('drafts');}
 else {const r=await post('/api/drafts',d);if(!current())return;clearFormMemory('new');state.compareSequence++;$('#draft-results').innerHTML=resultsHTML(r.candidates);$('#draft-notice').innerHTML=`<div class="alert info">초안이 저장되었습니다.<br>${escape(r.notice)}</div><button class="button soft" type="button" data-action="view" data-view="drafts">초안함 보기</button>`;if(await loadMeta() && current())toast('초안을 저장했습니다.');}}
 else if(form.id==='review-form') {const gen=state.generation;const target=$('#review-results');target.innerHTML=loading('검토 중');const r=await post('/api/review',{namespace:state.namespace,text:new FormData(form).get('text')});if(gen===state.generation)target.innerHTML=r.items.map(i=>`<section class="review-item"><p class="review-input"><span>${String(i.line).padStart(2,'0')}</span>${escape(i.input)}</p><div class="review-cards">${i.missing_codes.length?errorBox(i.summary):''}${i.results.length?i.results.map(codeCard).join(''):`<p class="alert">${escape(i.summary)}</p>`}</div></section>`).join('');}
 else if(form.id==='external-lookup-form'){const review=state.externalReview;if(!review)return;const code=new FormData(form).get('code').trim();const row=await api(`/api/codes/${encodeURIComponent(code)}?namespace=${review.draft.namespace}`);if(current() && state.externalReview===review)showExternalLink(row);}
 else if(form.id==='external-link-form'){const f=new FormData(form);const data=state.externalReview;if(!data)return;await post(`/api/drafts/${data.draft.id}/link-external`,{namespace:data.draft.namespace,expected_revision:data.draft.revision,expected_catalog_version:data.catalog_version,code:form.dataset.code,reason:f.get('reason'),differences_ack:!!f.get('differences_ack')});if(!current())return;closeDialog();toast('확정 코드와 연결해 등록 완료로 표시했습니다.');await navigate('drafts');}
 else if(form.id==='approve-form'){const f=new FormData(form);await post(`/api/drafts/${form.dataset.id}/approve`,{namespace:ctx.namespace,expected_revision:Number(form.dataset.revision),expected_catalog_version:Number(form.dataset.version),code:f.get('code')?.trim() || null,prefix:f.get('prefix')||null,reason:f.get('reason'),duplicate_ack:!!f.get('duplicate_ack')});if(!current())return;closeDialog();toast('검토한 내용으로 등록했습니다.');await navigate('drafts');}
 else if(form.id==='status-form'){const f=new FormData(form);await api(`/api/codes/${encodeURIComponent(form.dataset.code)}/status`,{method:'PATCH',body:JSON.stringify({namespace:ctx.namespace,expected_revision:Number(form.dataset.revision),status:form.dataset.status,reason:f.get('reason')})});if(!current())return;closeDialog();toast('사용 상태를 변경했습니다.');await navigate('catalog');}
 }catch(e){if(form.id==='auth-form')$('#auth-error').textContent=e.message;else if(form.id==='admin-auth-form'&&current())$('#admin-auth-error').innerHTML=errorBox(e.message);else if(form.id==='admin-ai-form'&&current())$('#admin-ai-error').innerHTML=errorBox(e.message);else if(current()){if(form.id==='approve-form')$('#approve-error').innerHTML=errorBox(e.message);else toast(e.message);}}finally{delete form.dataset.pending;if(submit)submit.disabled=false;}
});
document.addEventListener('click',async event=>{
 const btn=event.target.closest('button');if(!btn || btn.disabled || btn.closest('form')?.dataset.pending==='true')return;
 if(btn.dataset.view && !btn.dataset.action){state.draftInput=null;await navigate(btn.dataset.view);return;}
 if(btn.dataset.query){const input=$('#query');if(input){input.value=btn.dataset.query;$('#search-form').requestSubmit();}return;}
 const action=btn.dataset.action;if(!action)return;
 const ctx=context();const inDialog=!!btn.closest('#detail-dialog');
 const current=()=>isCurrent(ctx,inDialog);
 const originalText=btn.textContent;
 // Busy action buttons are disabled immediately, before their first await.
 const pendingAction=['copy','revision','draft-compare','edit-draft','external-matches','copy-draft-marker','handoff','export-codes','export-drafts','template','remap','commit-import','reindex'].includes(action);
 if(pendingAction)btn.disabled=true;
 try {
 if(action==='view'){if(btn.dataset.view==='new')state.draftInput=null;await navigate(btn.dataset.view);}
 else if(action==='namespace'){state.namespace=state.namespace==='live'?'demo':'live';sessionStorage.setItem(sessionKey('cm_namespace'),state.namespace);state.result=null;state.meta=null;state.preview=null;state.previewSequence++;state.file=null;state.mapping={};state.draftInput=null;state.offset=0;await navigate(state.view);}
 else if(action==='settings')settingsDialog();
 else if(action==='admin-ai')adminUnlockDialog();
 else if(action==='lock')lockWorkspace();
 else if(action==='close-dialog')closeDialog();
 else if(action==='detail')await detail(btn.dataset.code);
 else if(action==='copy'){const d=await api(`/api/codes/${encodeURIComponent(btn.dataset.code)}/copy?namespace=${ctx.namespace}`);if(current())await copy(d.text);}
 else if(action==='revision'){const d=await api(`/api/codes/${encodeURIComponent(btn.dataset.code)}?namespace=${ctx.namespace}`);if(!current())return;clearFormMemory('new');state.draftInput={...d,kind:'revision',target_code:d.code};closeDialog();await navigate('new');}
 else if(action==='draft-compare'){const f=new FormData($('#draft-form'));if(!String(f.get('message')).trim())throw new Error('먼저 문구를 입력해주세요.');const target=$('#draft-results');const sequence=++state.compareSequence;target.innerHTML=loading();const data=await post('/api/compare',{namespace:ctx.namespace,query:f.get('message'),message:f.get('message'),menu:f.get('menu'),trigger:f.get('trigger'),include_retired:true});if(current() && sequence===state.compareSequence && target.isConnected)target.innerHTML=resultsHTML(data);}
 else if(action==='edit-draft'){const d=await api(`/api/drafts/${btn.dataset.id}/review?namespace=${ctx.namespace}`);if(!current())return;clearFormMemory('new');state.draftInput={...d.draft,editing:true};closeDialog();await navigate('new');}
 else if(action==='external-matches')await externalMatches(btn.dataset.id);
 else if(action==='pick-external'){const row=state.externalReview?.items.find(r=>r.code===btn.dataset.code);if(row)showExternalLink(row);}
 else if(action==='copy-draft-marker'){if(state.externalReview)await copy(state.externalReview.marker);}
 else if(action==='review-draft')await reviewDraft(btn.dataset.id);
 else if(action==='handoff'){await post(`/api/drafts/${btn.dataset.id}/handoff?namespace=${ctx.namespace}&expected_revision=${btn.dataset.revision}`,{});if(!current())return;closeDialog();toast('등록 요청으로 표시했습니다. 정식 등록 완료가 아닙니다.');await navigate('drafts');}
 else if(action==='export-codes')await download(`/api/export/codes.csv?namespace=${state.namespace}`,'알림_코드_목록.csv');
 else if(action==='export-drafts')await download(`/api/export/drafts.csv?namespace=${state.namespace}`,'알림_문구_초안.csv');
 else if(action==='template')await download('/api/template.xlsx','code_catalog_template.xlsx');
 else if(action==='prev-page'){state.offset=Math.max(0,state.offset-30);await navigate('catalog');}
 else if(action==='next-page'){state.offset+=30;await navigate('catalog');}
 else if(action==='remap'){state.mapping={};$$('.sheet-mapping').forEach(el=>{const columns={};$$('select[data-map]',el).forEach(s=>{if(s.value)columns[s.dataset.map]=s.value;});if(columns.code && columns.message)state.mapping[el.dataset.sheet]={header_row:Number($('input[data-map=header_row]',el).value),columns};});await previewFile();}
 else if(action==='commit-import'){const preview=state.preview;if(!preview || preview.import_id!==btn.dataset.importId)throw new Error('선택한 파일을 다시 미리보기 해주세요.');const approved=$$('.approve-update:checked').map(c=>c.dataset.code);if(preview.counts.conflict>approved.length && !$('#skip-conflicts')?.checked)throw new Error('반영하지 않은 충돌 항목을 제외할지 확인해주세요.');if(approved.length && !$('#update-reason')?.value.trim())throw new Error('원문 갱신 이유를 입력해주세요.');const r=await post(`/api/imports/${preview.import_id}/commit`,{expected_catalog_version:preview.catalog_version,skip_conflicts:!!$('#skip-conflicts')?.checked,approved_updates:approved,update_reason:$('#update-reason')?.value||''});if(!current() || state.preview!==preview)return;state.preview=null;state.file=null;toast(`${r.added}개 추가, ${r.updated}개 원문 갱신${r.linked_drafts?.length?`, 초안 ${r.linked_drafts.length}개 등록 완료 연결`: ''}을 반영했습니다.`);await navigate('catalog');}
 else if(action==='reindex'){btn.textContent='모델에서 검색 데이터를 준비하고 있습니다.';const r=await post(`/api/ai/reindex?namespace=${ctx.namespace}`,{});if(!current())return;toast(`${r.indexed}개 항목의 AI 검색 데이터를 준비했습니다.`);if(await loadMeta() && current())settingsDialog();}
 else if(action==='status-prompt'){openDialog(`${dialogHeader(btn.dataset.status==='retired'?'폐기 처리 확인':'사용 상태 복원')}<p class="muted small">번호는 삭제하거나 재발급하지 않습니다. 상태 변경 이유를 기록합니다.</p><form id="status-form" class="field-group" data-code="${escape(btn.dataset.code)}" data-status="${escape(btn.dataset.status)}" data-revision="${btn.dataset.revision}"><label>변경 이유<input name="reason" required maxlength="1000"></label><button class="button primary" type="submit">상태 변경</button></form>`);}
 }catch(e){if(current())toast(e.message);}finally{if(btn.isConnected && pendingAction){btn.disabled=false;if(action==='reindex')btn.textContent=originalText;}}
});
document.addEventListener('input',event=>{if(event.target.closest?.('#content form'))saveFormMemory(state.view);});
document.addEventListener('change',event=>{
 if(event.target.closest?.('#content form'))saveFormMemory(state.view);
 if(event.target.id!=='upload-file')return;
 state.file=event.target.files[0] || null;state.mapping={};state.preview=null;state.previewSequence++;
 $('#import-preview')?.replaceChildren();
 const note=$('#file-note');if(note)note.textContent=state.file?`${state.file.name} · 미리보기 후 반영해주세요.`:'미리보기 후 반영';
});
document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&!$('#detail-dialog').open&&!$('#auth-dialog').open){e.preventDefault();$('#query')?.focus();}});
$('#auth-dialog').addEventListener('cancel',e=>e.preventDefault());
$('#detail-dialog').addEventListener('cancel',e=>{e.preventDefault();closeDialog();});
navigate('search');

async function externalMatches(id) {
 const d=await dialogData(`/api/drafts/${id}/external-matches?namespace=${state.namespace}`);if(!d)return;
 state.externalReview=d;
 openDialog(`${dialogHeader('엑셀 등록 연결')}<p class="small muted">초안: ${escape(d.draft.message)}<br>확정된 코드와 연결하세요.</p><details class="help-details"><summary>자동 연결 방법</summary><p>엑셀 비고에 아래 표시를 넣으세요. 문구·메뉴·조건이 일치하면 가져올 때 연결됩니다.</p><code>${escape(d.marker)}</code> <button class="button compact" data-action="copy-draft-marker">표시 복사</button></details>${d.items.length?d.items.map(r=>`<article class="draft-card"><div><strong>${escape(r.code)}</strong><p>${escape(r.message)}</p><p class="small muted">${escape(r.menu || '메뉴 미입력')} · ${escape(r.trigger || '조건 미입력')}</p><p>${r.differences.length?'초안과 다른 항목: '+r.differences.map(escape).join(', '):'문구·메뉴·조건 일치'}</p></div><button class="button" data-action="pick-external" data-code="${escape(r.code)}">등록 내용 확인</button></article>`).join(''):'<p class="alert">연결 후보가 없습니다. 확정 엑셀을 가져오거나 코드번호로 확인해주세요.</p>'}<form id="external-lookup-form" class="field-group"><label>확정 코드번호 직접 확인<input name="code" required maxlength="40" placeholder="예: AT-1924"></label><button class="button" type="submit">코드 내용 확인</button></form>`);
}
function showExternalLink(row) {
 const d=state.externalReview;if(!d)return;const fields=[['message','문구'],['menu','메뉴'],['trigger','노출 조건']];const differences=fields.filter(([k])=>d.draft[k]!==row[k]);
 openDialog(`${dialogHeader('등록 내용 확인')}<p class="mono">${escape(row.code)}</p><div class="table-wrap"><table><thead><tr><th>항목</th><th>작성 초안</th><th>엑셀 등록 내용</th></tr></thead><tbody>${fields.map(([k,label])=>`<tr><th>${label}</th><td>${escape(d.draft[k]||'미입력')}</td><td>${escape(row[k]||'미입력')}</td></tr>`).join('')}</tbody></table></div><p class="section-note">${escape(sourceText(row))} · 등록 원문은 유지됩니다.</p><form id="external-link-form" data-code="${escape(row.code)}" class="field-group"><label>등록 확인 이유<input name="reason" required maxlength="1000" placeholder="담당자가 확정한 코드와 문구를 확인했습니다."></label>${differences.length?'<label class="check"><input type="checkbox" name="differences_ack" required>초안과 다른 문구·메뉴·조건을 확인했습니다.</label>':''}<button class="button primary" type="submit">등록 완료로 연결</button></form>`);
}

