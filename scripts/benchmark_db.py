"""Reproducible DB-layer benchmark; synthetic data only, no live DB access."""
import json, statistics, tempfile, time, uuid
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from catalog.db import DB, now

def measure(fn):
    samples=[]
    for _ in range(7):
        started=time.perf_counter();fn();samples.append((time.perf_counter()-started)*1000)
    return round(statistics.median(samples),3)

with tempfile.TemporaryDirectory(prefix='cm-db-benchmark-') as directory:
    db=DB(Path(directory)/'benchmark.sqlite3')
    stamp=now()
    source=json.dumps({'filename':'synthetic.xlsx','sheet':'Test','context':'x'*1200})
    with db.connect(write=True) as con:
        con.executemany("""INSERT INTO codes(id,namespace,code,message,menu,trigger_text,source_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            [(str(uuid.uuid4()),'live',f'AT-{i:05d}','합성 안내 문구 '+str(i)+' 예시'*50,'합성 메뉴','합성 조건',source,stamp,stamp)
             for i in range(10000)])
    def old_stats():
        rows=db.all_codes('live')
        return {'total':len(rows),'active':sum(r['status']=='active' for r in rows),
                'retired':sum(r['status']=='retired' for r in rows),'drafts':0}
    def old_page():
        rows=db.all_codes('live')
        return {'items':rows[5000:5030],'total':len(rows),'offset':5000,'limit':30,'catalog_version':db.version('live')}
    new_stats=lambda:db.catalog_stats('live')
    new_page=lambda:db.page_codes('live',offset=5000,limit=30)
    assert old_stats()==new_stats()
    assert old_page()==new_page()
    result={'scope':'DB-layer only, 10000 synthetic records; median of 7 runs',
            'stats':{'before_ms':measure(old_stats),'after_ms':measure(new_stats)},
            'page_30':{'before_ms':measure(old_page),'after_ms':measure(new_page)}}
    for item in [result['stats'],result['page_30']]:
        item['speedup']=round(item['before_ms']/item['after_ms'],1)
    target=Path(__file__).resolve().parents[1]/'docs/optimization-benchmark.json'
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
