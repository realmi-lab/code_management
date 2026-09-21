"""Opt-in live evaluation of synthetic demo DB; never seeds production data.
Calls configured search/model APIs and creates three demo conversations.
"""
import json, time, uuid, statistics, urllib.request, urllib.error
from pathlib import Path
BASE='http://localhost:3500/api'
OUT=Path(__file__).resolve().parents[1]/'docs/verification/catalog-quality-v1'
CASES=[
 ('인증 전에 30초 기다리라는 알림 있어?','AT-1923'),
 ('인증번호 전송에 성공했을 때 보여줄 문구','EX-0101'),
 ('입력한 인증번호가 틀렸을 때 안내','EX-0102'),
 ('인증번호 유효시간이 지난 경우','EX-0103'),
 ('인증을 30초 안에 끝내야 한다는 안내','EX-0104'),
 ('인증번호 재발송까지 남은 초를 표시하는 문구','EX-0105'),
 ('기존 회원 전화번호로 다시 가입하려는 경우','EX-0201'),
 ('필수 이용약관에 동의하지 않았을 때','EX-0202'),
 ('이메일 중복 검사 결과 이미 쓰고 있는 주소인 경우','EX-0204'),
 ('수정 내용을 저장하지 않은 채 화면을 나갈 때 확인','EX-0401'),
 ('인터넷 연결에 실패해서 다시 시도해야 하는 경우','EX-0402'),
 ('권한이 없는 메뉴에 들어가려고 할 때','EX-0403'),
]
def api(path,body=None):
 data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
 req=urllib.request.Request(BASE+path,data=data,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=260) as res:return json.load(res)
def save(name,value):
 OUT.mkdir(parents=True,exist_ok=True);(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2))
def main():
 settings=api('/settings');prod_before=api('/code-catalog/codes?namespace=production&limit=1')
 records=[]
 for offset in (0,200):records.extend(api('/code-catalog/codes?namespace=demo&limit=200&offset='+str(offset))['items'])
 by_code={r['code']:r for r in records}
 assert all(code in by_code for _,code in CASES)
 assert all(by_code[c]['source'].get('synthetic') for _,c in CASES)
 save('dataset.json',[{'query':q,'expected_code':c,'expected_message':by_code[c]['message']} for q,c in CASES])
 save('settings.json',settings)
 results=[]
 for q,c in CASES:
  t=time.monotonic();row={'query':q,'expected_code':c}
  try:
   r=api('/code-catalog/search-test',{'namespace':'demo','query':q});codes=[x['code'] for x in r['items']]
   row.update(result=r,rank=codes.index(c)+1 if c in codes else None,originals_match=all(x['message']==by_code[x['code']]['message'] for x in r['items']))
  except urllib.error.HTTPError as e:
   row['error']=str(e);row['error_detail']=e.read().decode('utf-8',errors='replace')
  except Exception as e:row['error']=str(e)
  row['seconds']=round(time.monotonic()-t,3);results.append(row);save('retrieval.json',results)
  print({'query':q,'rank':row.get('rank'),'seconds':row['seconds'],'error':row.get('error')},flush=True)
 answers=[]
 for q,c in [CASES[0],CASES[6],CASES[9]]:
  t=time.monotonic();row={'query':q,'expected_code':c}
  try:
   thread=api('/code-catalog/threads?namespace=demo',{})
   row['thread_id']=thread['id']
   row['result']=api('/code-catalog/threads/'+thread['id']+'/turn?namespace=demo',{'request_id':str(uuid.uuid4()),'expected_version':0,'text':q,'action':'auto'})
  except urllib.error.HTTPError as e:
   row['error']=str(e);row['error_detail']=e.read().decode('utf-8',errors='replace')
  except Exception as e:row['error']=str(e)
  row['seconds']=round(time.monotonic()-t,3);answers.append(row);save('answers.json',answers)
  print({'answer_query':q,'seconds':row['seconds'],'error':row.get('error')},flush=True)
 prod_after=api('/code-catalog/codes?namespace=production&limit=1')
 summary={'cases':len(results),'top1':sum(r.get('rank')==1 for r in results)/len(results),'hit_at_8':sum(bool(r.get('rank') and r['rank']<=8) for r in results)/len(results),'mrr_at_8':sum(1/r['rank'] if r.get('rank') and r['rank']<=8 else 0 for r in results)/len(results),'errors':sum('error' in r for r in results),'median_seconds':statistics.median(r['seconds'] for r in results),'originals_match':all(r.get('originals_match',False) for r in results),'production_unchanged':prod_before==prod_after,'sample_count':len(records),'answer_completed':sum('result' in r for r in answers),'independent_llm_judge':False}
 save('summary.json',summary);print(summary,flush=True)
if __name__=='__main__':main()
