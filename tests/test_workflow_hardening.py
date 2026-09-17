"""Regression checks use isolated fixtures; no production catalog or model calls."""
import hashlib
import io
import zipfile

import pytest

from catalog import importer
from .conftest import add, commit, csv_file, upload, xlsx_fixture
from .test_completion import draft, handoff, imported, status


def modified_xlsx(*, replace=(), extra=None):
    source=xlsx_fixture()
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as src, zipfile.ZipFile(out,'w') as dst:
        for name in src.namelist():
            payload=src.read(name)
            if name=='xl/worksheets/sheet1.xml':
                for old,new in replace:
                    assert old.encode() in payload
                    payload=payload.replace(old.encode(),new.encode())
            dst.writestr(name,payload)
        for name,text in (extra or {}).items(): dst.writestr(name,text)
    return out.getvalue()


def test_handoff_current_pending_revision_does_not_write_again(client):
    d=handoff(client,draft(client))
    before=client.get('/api/audit').json()['items']
    after=handoff(client,d)
    assert after==d
    assert client.get('/api/audit').json()['items']==before
    # An edited/stale request must still be refused.
    assert client.post(f"/api/drafts/{d['id']}/handoff?expected_revision=1").status_code==409


def test_reconcile_reused_marker_across_imports_requires_manual_review(client):
    d=handoff(client,draft(client,message='검토 완료 문구'))
    assert imported(client,d,marker=True,message='앞서 등록된 다른 문구')['linked_drafts']==[]
    result=imported(client,d,code='AT-8001',marker=True)
    assert result['linked_drafts']==[]
    assert status(client,d)['state']=='pending_external'


def test_reconcile_differing_marked_candidate_in_same_import_is_ambiguous(client):
    d=handoff(client,draft(client,message='검토 완료 문구'))
    marker='[draft:'+d['id']+']'
    p=upload(client,[['코드번호','등록문구','비고'],
                    ['AT-8000',d['message'],marker],
                    ['AT-8001','다른 확정 문구',marker]]).json()
    assert commit(client,p).json()['linked_drafts']==[]
    assert status(client,d)['state']=='pending_external'


def test_reconcile_multiple_markers_never_auto_links(client):
    d=handoff(client,draft(client))
    p=upload(client,[['코드번호','등록문구','비고'],
                    ['AT-8000',d['message'],'[draft:'+d['id']+'] [draft:unknown]']]).json()
    assert commit(client,p).json()['linked_drafts']==[]


def test_external_matches_version_covers_same_snapshot(client,monkeypatch):
    d=handoff(client,draft(client))
    imported(client,d)
    db=client.app.state.db
    original=db.all_codes
    version=db.version('live')
    changed=False
    def concurrent_update(ns,include_retired=True,con=None):
        nonlocal changed
        rows=original(ns,include_retired,con)
        if ns=='live' and not changed:
            changed=True
            with db.connect(write=True) as writer:
                writer.execute("UPDATE codes SET message='변경된 등록 문구',revision=revision+1 WHERE namespace='live'")
                db.bump(writer,'live')
        return rows
    monkeypatch.setattr(db,'all_codes',concurrent_update)
    result=client.get('/api/drafts/'+d['id']+'/external-matches').json()
    assert result['catalog_version']==version
    assert result['items'][0]['message']==d['message']
    body={'expected_revision':d['revision'],'expected_catalog_version':result['catalog_version'],
          'code':'AT-8000','reason':'화면에서 확인'}
    assert client.post('/api/drafts/'+d['id']+'/link-external',json=body).status_code==409


@pytest.mark.parametrize('replace',[
    [('r="A2"','r="A9"')],
    [('r="A2"','r="A2extra"')],
    [('r="2"','r="1"'),('r="A2"','r="A1"'),('r="B2"','r="B1"')],
    [('<c r="B2"', '<c r="A2"')],
])
def test_malformed_or_duplicate_cell_coordinates_are_rejected(client,replace):
    result=upload(client,modified_xlsx(replace=replace),filename='coordinates.xlsx')
    assert result.status_code==422
    assert client.get('/api/codes').json()['total']==0


def test_negative_shared_string_index_is_not_python_negative_index(client):
    blob=modified_xlsx(replace=[
        ('<c r="A2" t="inlineStr"><is><t xml:space="preserve">AT-001</t></is></c>',
         '<c r="A2" t="s"><v>-1</v></c>')],
        extra={'xl/sharedStrings.xml':'<sst xmlns="'+importer.NS['m']+'"><si><t>AT-999</t></si></sst>'})
    result=upload(client,blob,filename='negative-index.xlsx')
    assert result.status_code==422


def merged_context_xlsx(formula=False):
    value='<f>1+1</f><v>2</v>' if formula else '<is><t>가입 메뉴</t></is>'
    typ='' if formula else ' t="inlineStr"'
    return modified_xlsx(replace=[
        ('</sheetData>','<row r="3"><c r="A3" t="inlineStr"><is><t>AT-002</t></is></c>'
         '<c r="B3" t="inlineStr"><is><t>다른 문구</t></is></c><c r="C3"/></row></sheetData>'),
        ('</worksheet>','<mergeCells><mergeCell ref="C2:C3"/></mergeCells></worksheet>'),
        ('</row><row r="2">','<c r="C1" t="inlineStr"><is><t>메뉴</t></is></c></row><row r="2">'),
        ('</row><row r="3">',f'<c r="C2"{typ}>{value}</c></row><row r="3">')])


def test_merged_context_preserves_anchor_text_and_source(client):
    p=upload(client,merged_context_xlsx(),filename='merged-context.xlsx').json()
    assert not p['errors']
    assert len(p['records'])==2
    assert all(r['menu']=='가입 메뉴' for r in p['records'])
    assert p['records'][1]['source']['cell_map']['menu']=='C2'


def test_merged_formula_context_never_imports_cached_result(client):
    p=upload(client,merged_context_xlsx(formula=True),filename='formula-context.xlsx').json()
    assert len(p['errors'])==2 and all('수식' in e for e in p['errors'])
    assert p['records']==[]
    assert commit(client,p).status_code==422


def test_upload_fingerprint_computed_once_and_preserved(monkeypatch):
    rows=[['코드번호','등록문구']]+[[f'AT-{n:04d}','합성 문구'] for n in range(1000)]
    blob=csv_file(rows)
    expected=hashlib.sha256(blob).hexdigest()
    original=hashlib.sha256
    calls=[]
    def tracked(value):
        calls.append(len(value))
        return original(value)
    monkeypatch.setattr(importer.hashlib,'sha256',tracked)
    parsed=importer.parse_upload(blob,'synthetic.csv')
    assert not parsed['errors'] and len(parsed['records'])==1000
    assert calls==[len(blob)]
    assert {r['source']['sha256'] for r in parsed['records']}=={expected}


def test_duplicate_warnings_are_unique_bounded_and_keep_total(client):
    add(client,code='AT-0000',message='동일 문구')
    rows=[['코드번호','등록문구']]+[[f'AT-{n:04d}','동일 문구'] for n in range(50)]
    parsed=upload(client,rows).json()
    records=parsed['records']
    assert records[1]['same_message_codes']==['AT-0000']
    assert records[1]['same_message_count']==1
    assert records[-1]['same_message_count']==49
    assert len(records[-1]['same_message_codes'])==20
    assert all(len(r['same_message_codes'])<=20 for r in records)
