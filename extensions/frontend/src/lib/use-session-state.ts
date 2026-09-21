"use client";
import {useCallback,useEffect,useRef,useState,type SetStateAction} from 'react';
import {useAuth} from '@/lib/auth-context';
/** Per-tab, per-user UI state. Never store credentials. */
export function useSessionState<T>(name:string,initial:T):[T,(next:SetStateAction<T>)=>void]{
 const {user}=useAuth();
 const key=user?`catalog-ui:v1:${user.id}:${name}`:null;
 const first=useRef(initial),current=useRef(initial);
 const [value,setValue]=useState(initial);
 useEffect(()=>{
  let restored=first.current;
  if(key){try{const raw=sessionStorage.getItem(key);if(raw!==null)restored=JSON.parse(raw) as T;}catch{/* Unavailable storage does not break the screen. */}}
  current.current=restored;setValue(restored);
  const sync=(event:Event)=>{const change=(event as CustomEvent<{key:string;value:T}>).detail;
   if(key&&change?.key===key){current.current=change.value;setValue(change.value);}
  };
  window.addEventListener('catalog-ui-state',sync);
  return()=>window.removeEventListener('catalog-ui-state',sync);
 },[key]);
 const update=useCallback((next:SetStateAction<T>)=>{
  const resolved=typeof next==='function'?(next as (previous:T)=>T)(current.current):next;
  current.current=resolved;setValue(resolved);
  if(key){
   try{sessionStorage.setItem(key,JSON.stringify(resolved));}catch{/* Full/disabled storage: retain in-memory state. */}
   window.dispatchEvent(new CustomEvent('catalog-ui-state',{detail:{key,value:resolved}}));
  }
 },[key]);
 return [value,update];
}
