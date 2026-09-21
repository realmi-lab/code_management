"""Opt-in live regression for the five original failures; preserves the 68-case run.

Uses the real demo database, model, validators and upstream rubric. This is not
an independent-model evaluation and does not modify production catalog records.
"""
import concurrent.futures
import argparse
import json
import subprocess
from pathlib import Path
import live_catalog_quality_68 as quality

OUT=quality.ROOT/'docs/verification/catalog-quality-fix-2026-09-21'


def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2))


def main():
    global OUT
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args();OUT=args.output
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'results.json').exists():
        raise RuntimeError('Regression evidence already exists; choose a new output directory.')
    cases=[c for c in json.loads((quality.OUT/'dataset.json').read_text()) if c['id'] in (2,5,7,27,67)]
    rows=[]
    for offset in (0,200):
        rows+=quality.api('/code-catalog/codes?namespace=demo&limit=200&offset='+str(offset))['items']
    bycode={r['code']:r for r in rows}
    assert all(bycode[c['expected_code']]['message']==c['expected_message'] for c in cases)
    assert all(r['source'].get('synthetic') for r in rows)
    before={
        'production':quality.api('/code-catalog/codes?namespace=production&limit=1'),
        'settings':quality.api('/settings'),
        'provider':quality.api('/code-catalog/ai-settings'),
        'corpus':rows,
    }
    save('before.json',before);save('dataset.json',cases)
    results=[]
    for round_number in (1,2):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(quality.run_case,c,bycode) for c in cases]
            for future in concurrent.futures.as_completed(futures):
                result=future.result();result['round']=round_number;results.append(result)
                save('results.json',results)
                print({'round':round_number,'case':result['id'],'action':result.get('result',{}).get('action'),
                       'rank':result.get('rank'),'score':result.get('judge',{}).get('score'),
                       'seconds':result.get('answer_seconds'),'error':result.get('error') or result.get('judge_error')},flush=True)
    summary=quality.summarize(results);summary.update(target=10,unique_questions=5,rounds=2)
    summary['all_search']=all(r.get('result',{}).get('action')=='search' for r in results)
    summary['no_drafts']=all(r.get('result',{}).get('draft') is None for r in results)
    after_rows=[]
    for offset in (0,200):
        after_rows+=quality.api('/code-catalog/codes?namespace=demo&limit=200&offset='+str(offset))['items']
    after={
        'production':quality.api('/code-catalog/codes?namespace=production&limit=1'),
        'settings':quality.api('/settings'),
        'provider':quality.api('/code-catalog/ai-settings'),
        'corpus':after_rows,
    }
    save('after.json',after)
    summary['unchanged']={key:before[key]==after[key] for key in before}
    logs=subprocess.run(quality.manage.compose_args()+['logs','--no-color','rag-api'],capture_output=True,text=True,check=True)
    threads={r['thread_id']:(r['round'],r['id']) for r in results};events=[]
    for line in (logs.stdout+'\n'+logs.stderr).splitlines():
        if 'catalog_validation ' not in line:continue
        try:
            outer=json.loads(line[line.index('{'):]);event=json.loads(outer['event'].split('catalog_validation ',1)[1])
        except (ValueError,KeyError):continue
        if event.get('thread_id') in threads:
            rnd,case=threads[event['thread_id']]
            events.append({'round':rnd,'case':case,'timestamp':outer.get('timestamp'),**event})
    save('validation-trace.json',events)
    summary['blocked_validation_events']=sum(e['status']=='blocked' for e in events)
    save('summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
