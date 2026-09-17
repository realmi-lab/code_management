"""Load the user-confirmed photo transcription into a dedicated test DB only.
Never modifies the operational catalog. Safe to rerun for an identical dataset.
"""
from pathlib import Path
import csv
import io
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from catalog.config import Settings,ROOT
from catalog.main import create_app
from catalog.db import dumps

DATASET=ROOT/'data/photo-test-input/7360-transcription.json'
TARGET=ROOT/'data/photo-test'
FIELDS=('business','message_type','code','purpose','title','message','title_en','message_en')
HEADERS=('업무구분','타입','메시지코드','용도','Title','Contents','영문Title','영문Contents')

def load():
    dataset=json.loads(DATASET.read_text())
    records=dataset['records']
    assert len(records)==33 and len({row['code'] for row in records})==33
    app=create_app(Settings(data_dir=TARGET,access_token='photo-seed-local-only',ai_enabled=False,
        catalog_label='사진 테스트 목록',catalog_notice='사진에서 읽은 테스트 자료입니다. 원본 엑셀 확인이 필요합니다.'))
    db=app.state.db
    existing=db.all_codes('live')
    if existing:
        assert {r['code'] for r in existing}=={r['code'] for r in records},'Test database already contains a different dataset'
        bycode={r['code']:r for r in records}
        for old in existing:
            wanted=bycode[old['code']]
            assert old['source'].get('dataset_id')==dataset['dataset_id'],'Unexpected source in test database'
            assert all(old.get(key,'')==wanted.get(key,'') for key in FIELDS),'Existing test data differs; no overwrite performed'
        return {'loaded':0,'existing':len(existing),'dataset_id':dataset['dataset_id']}
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(HEADERS)
    writer.writerows([[r.get(field,'') for field in FIELDS] for r in records])
    blob=('\ufeff'+out.getvalue()).encode('utf-8')
    csv_path=DATASET.with_suffix('.csv');csv_path.write_bytes(blob);csv_path.chmod(0o600)
    with TestClient(app) as client:
        client.headers['Authorization']='Bearer photo-seed-local-only'
        preview=client.post('/api/imports/preview',files={'file':('photo_7360_transcription.csv',blob,'text/csv')})
        assert preview.status_code==200,'Photo preview failed'
        p=preview.json()
        assert not p['errors'],p['errors']
        assert p['counts']['new']==33
        response=client.post('/api/imports/'+p['import_id']+'/commit',json={'expected_catalog_version':p['catalog_version']})
        assert response.status_code==200,'Photo import failed'
        assert response.json()['added']==33
    # Preserve the CSV import trail while explicitly marking photographed cells
    # as an unverified transcription rather than an authoritative Excel original.
    with db.connect(write=True) as con:
        for record in records:
            current=db.get_code('live',record['code'],con)
            source={**current['source'],'kind':'photo_transcription','dataset_id':dataset['dataset_id'],
                'original_image':dataset['original_image'],'original_sha256':dataset['original_sha256'],
                'source_sheet_label':dataset['source_sheet_label'],'review_required':True,
                'review_notes':record['review_notes'],'unobserved_fields':dataset['unobserved_fields']}
            con.execute('UPDATE codes SET source_json=? WHERE id=?',(dumps(source),current['id']))
        db.bump(con,'live')
        db.audit(con,'live','photo.transcription_loaded',dataset['dataset_id'],None,
            {'count':len(records),'original_image':dataset['original_image']},
            '사용자가 대화에서 확인한 사진 판독본을 독립 테스트 목록에 적재. 원본 엑셀 미대조.')
    return {'loaded':33,'dataset_id':dataset['dataset_id'],'review_required':True,'operational_database_untouched':True}

if __name__=='__main__':
    print(json.dumps(load(),ensure_ascii=False))
