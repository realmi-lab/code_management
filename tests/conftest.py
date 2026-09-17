from __future__ import annotations
import io
import zipfile
import pytest
from fastapi.testclient import TestClient
from catalog.config import Settings
from catalog.main import create_app

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path/'test_data'))) as c: yield c

@pytest.fixture
def secured(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path/'secure_data',access_token='test-only-secret'))) as c: yield c

@pytest.fixture
def system_client(tmp_path):
    settings=Settings(data_dir=tmp_path/'system_data',authority='system',code_rules={'AT':{'start':2000,'width':4}})
    with TestClient(create_app(settings)) as c: yield c


def csv_file(rows):
    import csv
    out=io.StringIO(newline='');csv.writer(out).writerows(rows)
    return out.getvalue().encode('utf-8-sig')

def upload(client,rows,namespace='live',filename='목록.csv',mapping=None):
    import json
    data=csv_file(rows) if not isinstance(rows,bytes) else rows
    return client.post('/api/imports/preview',files={'file':(filename,data)},data={'namespace':namespace,'mapping':json.dumps(mapping or {})})

def commit(client,preview,**kwargs):
    return client.post('/api/imports/'+preview['import_id']+'/commit',json={'expected_catalog_version':preview['catalog_version'],**kwargs})

def add(client,code='AT-1923',message='메뉴확인 30초 이후에 인증해주세요.',namespace='live',menu='',trigger=''):
    result=upload(client,[['코드번호','등록문구','사용메뉴','노출조건'],[code,message,menu,trigger]],namespace).json()
    assert not result['errors'],result
    assert commit(client,result).status_code==200
    return result


def xlsx_fixture(*,formula=False,merged=False,doctype=False,headers=('코드번호','등록문구'),values=('AT-001','  원문\n둘째 줄 {seconds}  ')):
    """Minimal ZIP/XML fixture, not a production workbook generator."""
    from xml.sax.saxutils import escape
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    def cell(ref,value): return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'
    data=f'<row r="1">{cell("A1",headers[0])}{cell("B1",headers[1])}</row>'
    data+=f'<row r="2">{cell("A2",values[0])}'
    data+=('<c r="B2"><f>1+1</f><v>2</v></c>' if formula else cell('B2',values[1]))+'</row>'
    if merged: data+='<row r="3">'+cell('B3','다른 문구')+'</row>'
    sheet=f'<worksheet xmlns="{ns}"><sheetData>{data}</sheetData>'+('<mergeCells><mergeCell ref="A2:A3"/></mergeCells>' if merged else '')+'</worksheet>'
    if doctype: sheet='<!DOCTYPE worksheet [<!ENTITY x "bad">]>'+sheet
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="알림 목록" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',sheet)
    return out.getvalue()
