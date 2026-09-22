"""Live demo-only assessment; HTTP success is separate from useful grounded output."""
import argparse,json,time,uuid,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
API='http://127.0.0.1:8010/api/code-catalog'
def call(method,path,body=None):
    request=urllib.request.Request(API+path,method=method,headers={'Content-Type':'application/json'},data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(request,timeout=240) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
def cases():
    data=json.loads((ROOT/'docs/verification/catalog-quality-68/dataset.json').read_text())
    result=[{'name':str(r['id']),'text':r['query'],'expected_code':r['expected_code']} for r in data if r['id'] in (1,2,5,7,27,67,3,9,12)]
    result += [{'name':'broad','text':'30초 관련메시지찾아줘','expected_quantity':'30초'},
               {'name':'unrelated','text':'오늘 서울 날씨 어때?','unrelated':True},
               {'name':'comparison','text':'AT-1923과 EX-0104의 시간 조건 차이를 설명해줘.','action':'explain','required':['30초 이후','30초 이내']}]
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output');parser.add_argument('--runs',type=int,default=2);parser.add_argument('--limit',type=int,default=0);args=parser.parse_args()
    dataset=cases()[:args.limit or None];report={'provider':call('GET','/status?namespace=demo')[1].get('llm'),'scope':'demo synthetic only','cases':[]}
    for repeat in range(args.runs):
        for case in dataset:
            _,thread=call('POST','/threads?namespace=demo',{})
            start=time.monotonic();status,result=call('POST',f"/threads/{thread['id']}/turn?namespace=demo",{'request_id':str(uuid.uuid4()),'expected_version':thread['version'],'text':case['text'],'action':case.get('action','auto')})
            row={**case,'repeat':repeat,'status':status,'seconds':round(time.monotonic()-start,2),'thread_id':thread['id'],'result':result}
            answer=result.get('answer','');checks={}
            if case.get('expected_code'):
                _,expected=call('GET','/codes/'+case['expected_code']+'?namespace=demo')
                checks['expected_candidate']=case['expected_code'] in [c['code'] for c in result.get('candidates',[])]
                checks['expected_original_in_answer']=expected.get('message','\0') in answer
            if case.get('unrelated'):checks['no_unrelated_candidates']=status==200 and not result.get('candidates')
            if case.get('required'):checks['both_directions_explained']=all(s in answer for s in case['required'])
            if case.get('expected_quantity'):checks['quantity_present']=case['expected_quantity'] in answer
            row['checks']=checks;row['useful']=status==200 and not result.get('ai_error') and all(checks.values())
            report['cases'].append(row);Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps({k:row[k] for k in ('name','repeat','status','seconds','checks','useful')},ensure_ascii=False),flush=True)
