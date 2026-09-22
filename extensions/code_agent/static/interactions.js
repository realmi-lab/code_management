'use strict';
/* apple.com-style interaction layer for the workspace. Purely presentational: every
   control works without this file, and it stands down under prefers-reduced-motion.
   CSP allows only same-origin scripts and CSSOM styles, which is all it uses. */
(()=>{
 const reduce=matchMedia('(prefers-reduced-motion: reduce)');
 const main=document.getElementById('main');
 const nav=document.querySelector('.localnav');
 const tabs=document.querySelector('.tabs');

 /* Local nav turns denser once content scrolls beneath it. */
 main.addEventListener('scroll',()=>nav.classList.toggle('is-stuck',main.scrollTop>4),{passive:true});

 /* One underline that glides between tabs instead of jumping. */
 const bar=document.createElement('span');bar.className='tabs-indicator';bar.setAttribute('aria-hidden','true');tabs.append(bar);
 function moveBar(){
  const tab=tabs.querySelector('[role=tab][aria-selected=true]');
  if(!tab||tab.hidden||!tab.offsetWidth){bar.style.opacity='0';return;}
  bar.style.opacity='1';bar.style.width=tab.offsetWidth+'px';bar.style.transform='translateX('+tab.offsetLeft+'px)';
  // Keep the chosen tab in view on narrow screens where the links scroll sideways.
  if(tab.offsetLeft<tabs.scrollLeft||tab.offsetLeft+tab.offsetWidth>tabs.scrollLeft+tabs.clientWidth)
   tabs.scrollTo({left:tab.offsetLeft-24,behavior:reduce.matches?'auto':'smooth'});
 }
 new MutationObserver(moveBar).observe(tabs,{subtree:true,attributes:true,attributeFilter:['aria-selected','hidden']});
 new MutationObserver(moveBar).observe(document.getElementById('app'),{attributes:true,attributeFilter:['hidden']});
 addEventListener('resize',moveBar);
 document.fonts?.ready.then(moveBar);
 moveBar();

 /* Headline words arrive one after another the first time the welcome is shown. */
 const headline=document.querySelector('.welcome h2');
 if(headline&&!reduce.matches){
  const words=headline.textContent.trim().split(/\s+/);
  headline.setAttribute('aria-label',headline.textContent.trim());
  headline.replaceChildren(...words.flatMap((word,i)=>{
   const span=document.createElement('span');span.className='word';span.textContent=word;span.setAttribute('aria-hidden','true');
   span.style.animationDelay=80+i*90+'ms';
   return i?[' ',span]:[span];
  }));
 }

 /* Hero tiles lean toward the pointer with a soft spotlight, like apple.com cards. */
 const MAX_TILT=5;
 function tilt(event){
  const tile=event.currentTarget,box=tile.getBoundingClientRect();
  const x=(event.clientX-box.left)/box.width,y=(event.clientY-box.top)/box.height;
  tile.style.setProperty('--ry',((x-.5)*MAX_TILT*2).toFixed(2)+'deg');
  tile.style.setProperty('--rx',((.5-y)*MAX_TILT*2).toFixed(2)+'deg');
  tile.style.setProperty('--mx',(x*100).toFixed(1)+'%');
  tile.style.setProperty('--my',(y*100).toFixed(1)+'%');
 }
 function settle(event){for(const p of ['--rx','--ry','--mx','--my'])event.currentTarget.style.removeProperty(p);}
 for(const tile of document.querySelectorAll('.example')){
  tile.addEventListener('pointermove',e=>{if(e.pointerType==='mouse'&&!reduce.matches)tilt(e);});
  tile.addEventListener('pointerleave',settle);
 }
})();
