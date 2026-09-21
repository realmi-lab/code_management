"""Offline browser test adapter, used when browser HTTP navigation is restricted.

No browser policies are disabled. Asset bytes are loaded from project files and fetch
requests are dispatched to the actual FastAPI application through TestClient. Clipboard
permissions and browser HTTP/CSP enforcement are NOT tested by this adapter.
"""
from __future__ import annotations
import base64
import json
import re
from pathlib import Path
from fastapi.testclient import TestClient
from catalog.main import create_app
from catalog.config import Settings

ROOT=Path(__file__).resolve().parent.parent

BRIDGE_JS=r'''
window.__copiedText='';
Object.defineProperty(navigator,'clipboard',{configurable:true,value:{
 writeText:async text=>{window.__copiedText=text;},readText:async()=>window.__copiedText
}});
window.fetch=async function(url,options={}){
 const payload={path:String(url),method:options.method||'GET',headers:options.headers||{},body:options.body||null};
 if(options.body instanceof FormData){
  payload.body=null;payload.form=[];
  for(const [key,value] of options.body.entries()){
   if(value instanceof File){
    const bytes=new Uint8Array(await value.arrayBuffer());let s='';for(const b of bytes)s+=String.fromCharCode(b);
    payload.form.push({key,filename:value.name,content_type:value.type,data:btoa(s)});
   }else payload.form.push({key,value});
  }
 }
 const result=await window.__catalog_api__(payload);
 const bytes=Uint8Array.from(atob(result.body),c=>c.charCodeAt(0));
 return new Response(bytes,{status:result.status,headers:result.headers});
};
'''

class Harness:
    def __init__(self,data_dir,token):
        self.client=TestClient(create_app(Settings(data_dir=data_dir,access_token=token)))
        self.client.__enter__()
    def install(self,context):
        def bridge(source,payload):
            if payload.get('form') is not None:
                fields={};files={}
                for entry in payload['form']:
                    if 'filename' in entry:
                        files[entry['key']]=(entry['filename'],base64.b64decode(entry['data']),entry['content_type'])
                    else: fields[entry['key']]=entry['value']
                response=self.client.request(payload['method'],payload['path'],headers=payload['headers'],data=fields,files=files)
            else:
                response=self.client.request(payload['method'],payload['path'],headers=payload['headers'],content=payload.get('body'))
            return {'status':response.status_code,'headers':dict(response.headers),'body':base64.b64encode(response.content).decode()}
        context.expose_binding('__catalog_api__',bridge)
    def open(self,page,token='',namespace='live'):
        page.goto('about:blank')
        page.evaluate('''([token,namespace])=>{
          const storage=new Map();if(token)storage.set('cm_token',token);storage.set('cm_namespace',namespace);
          Object.defineProperty(window,'sessionStorage',{configurable:true,value:{
            getItem:key=>storage.has(key)?storage.get(key):null,
            setItem:(key,value)=>storage.set(key,String(value)), removeItem:key=>storage.delete(key)
          }});
        }''',[token,namespace])
        html=(ROOT/'static'/'index.html').read_text()
        html=re.sub(r'<link[^>]*>', '',html)
        html=re.sub(r'<script[^>]*>.*?</script>', '',html,flags=re.S)
        page.set_content(html)
        page.add_style_tag(path=str(ROOT/'static'/'styles.css'))
        page.add_script_tag(content=BRIDGE_JS)
        page.add_script_tag(path=str(ROOT/'static'/'app.js'))
    def close(self):self.client.__exit__(None,None,None)
