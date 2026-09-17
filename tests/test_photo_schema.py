"""Actual workbook shape with synthetic cell values, isolated temporary databases."""
import io
import zipfile
from xml.sax.saxutils import escape

import pytest

from catalog.importer import parse_upload, col_letter
from catalog.models import CATALOG_FIELDS, CODE_IN_TEXT, canonical_code
from .conftest import upload, commit, csv_file

HEADERS=['업무구분','타입','메시지코드','용도','타이틀','컨텐츠','영문타이틀','영문컨텐츠','비고']
VALUES=['합성업무','알럿','S-C-002','재사용 검토',' 합성 제목 ','합성 본문\n[확인]','ÉCOLE title','Sample\n[Confirm]','합성 비고']
EXPECTED=dict(zip(('business','message_type','code','purpose','title','message','title_en','message_en','notes'),VALUES))


@pytest.mark.parametrize('value,expected',[
    ('s-t-1','S-T-1'),(' S-A-00024 ','S-A-00024'),('S-C-2','S-C-2'),('AT-001','AT-001'),
])
def test_real_code_shapes_preserve_leading_zeros(value,expected):
    assert canonical_code(value)==expected
    assert CODE_IN_TEXT.findall(value.strip()+'이 뭐야?')==[value.strip()]


@pytest.mark.parametrize('value',['S--T-1','S-T-1-extra','1-S-T-1','S-T-1234567890123','S-T-1_'])
def test_code_scanner_never_extracts_suffix_from_invalid_token(value):
    with pytest.raises(ValueError):canonical_code(value)
    assert CODE_IN_TEXT.findall(value)==[]


@pytest.mark.parametrize('message_header',['컨텐츠','콘텐츠','Contents','content'])
def test_photo_csv_fields_are_distinct_and_literal(message_header):
    headers=HEADERS.copy();headers[5]=message_header
    result=parse_upload(csv_file([headers,VALUES]),'synthetic.csv')
    assert not result['errors']
    record=result['records'][0]
    assert all(record[key]==value for key,value in EXPECTED.items())
    assert record['menu']==record['trigger']==''
    assert record['source']['catalog_fields']=={f:EXPECTED[f] for f in CATALOG_FIELDS}
    assert record['source']['cell_map']['title']=='E2'


def two_sheet_workbook():
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    relns='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    def cell(col,row,text):
        return '<c r="'+col_letter(col)+str(row)+'" t="inlineStr"><is><t xml:space="preserve">'+escape(text)+'</t></is></c>'
    # Photo-shaped grouped header: first two columns vertically merged, message
    # columns under a horizontal group on the first header row.
    top='<row r="3">'+cell(0,3,'업무 구분')+cell(1,3,'타입')+cell(2,3,'메시지')+'</row>'
    titles=['메시지 코드','용도','Title','Contents','영문 Title','영문 Contents','비고']
    bottom='<row r="4">'+''.join(cell(i+2,4,title) for i,title in enumerate(titles))+'</row>'
    merges='<mergeCells><mergeCell ref="A3:A4"/><mergeCell ref="B3:B4"/><mergeCell ref="C3:I3"/><mergeCell ref="A5:A6"/></mergeCells>'
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('xl/workbook.xml','<workbook xmlns="'+ns+'" xmlns:r="'+relns+'"><sheets><sheet name="합성상품" sheetId="1" r:id="r1"/><sheet name="합성회원" sheetId="2" r:id="r2"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/><Relationship Id="r2" Target="worksheets/sheet2.xml"/></Relationships>')
        for sheet in (1,2):
            data=top+bottom
            for rn in (5,6):
                vals=VALUES.copy();vals[2]=f'S-{("T" if sheet==1 else "A")}-{rn}'
                if rn==6:vals[0]=''
                data+='<row r="'+str(rn)+'">'+''.join(cell(i,rn,value) for i,value in enumerate(vals))+'</row>'
            z.writestr(f'xl/worksheets/sheet{sheet}.xml','<worksheet xmlns="'+ns+'"><sheetData>'+data+'</sheetData>'+merges+'</worksheet>')
    return out.getvalue()


def test_multisheet_two_row_headers_and_merged_business_preserve_provenance():
    result=parse_upload(two_sheet_workbook(),'synthetic.xlsx')
    assert not result['errors'] and not result['warnings']
    assert len(result['records'])==4
    assert [s['header_row'] for s in result['sheets']]==[4,4]
    assert result['sheets'][0]['detected_columns']['business']=='A'
    assert {r['source']['sheet'] for r in result['records']}=={'합성상품','합성회원'}
    assert all(r['business']=='합성업무' and r['message_type']=='알럿' for r in result['records'])
    assert result['records'][1]['source']['cell_map']['business']=='A5'
    assert all(r['source']['catalog_fields']['title']==' 합성 제목 ' for r in result['records'])


def test_import_roundtrip_search_and_metadata_conflicts(client):
    preview=upload(client,[HEADERS,VALUES]).json()
    assert not preview['errors']
    assert commit(client,preview).status_code==200
    item=client.get('/api/codes/S-C-002').json()
    assert all(item[key]==value for key,value in EXPECTED.items())
    assert item['source']['catalog_fields']=={f:EXPECTED[f] for f in CATALOG_FIELDS}
    # Contents, title, business, English, and type are searchable without decoding
    # every source JSON in Python; Unicode case and literal substring semantics hold.
    for text in ['합성업무','알럿','재사용 검토','합성 제목','école','sample']:
        page=client.get('/api/codes',params={'q':text}).json()
        assert page['total']==1 and page['items'][0]['code']=='S-C-002'
    same=upload(client,[HEADERS,VALUES]).json()
    assert same['counts']=={'new':0,'unchanged':1,'conflict':0}
    values=VALUES.copy();values[4]='변경 제목'
    changed=upload(client,[HEADERS,values]).json()
    assert changed['counts']=={'new':0,'unchanged':0,'conflict':1}
    assert commit(client,changed).status_code==409
    assert client.get('/api/codes/S-C-002').json()['title']==VALUES[4]
    accepted=commit(client,changed,approved_updates=['S-C-002'],update_reason='합성 제목 변경 확인')
    assert accepted.status_code==200 and accepted.json()['updated']==1
    assert client.get('/api/codes/S-C-002').json()['title']=='변경 제목'


def test_explicit_empty_metadata_is_preserved_and_removal_requires_approval(client):
    p=upload(client,[HEADERS,VALUES]).json();assert commit(client,p).status_code==200
    p=upload(client,[['메시지코드','컨텐츠'],['S-C-002',VALUES[5]]]).json()
    assert p['records'][0]['source']['catalog_fields']=={f:'' for f in CATALOG_FIELDS}
    assert p['records'][0]['action']=='conflict'
    assert commit(client,p).status_code==409


def test_db_direct_insert_keeps_metadata_from_source_and_row(client):
    db=client.app.state.db
    row={'code':'S-A-7','message':'합성','title':'행의 제목'}
    source={'kind':'synthetic','catalog_fields':{'business':'원본 업무','title':'원본 제목'}}
    with db.connect(write=True) as con:
        db.insert_code(con,'live',row,source)
    item=db.get_code('live','S-A-7')
    assert item['title']=='행의 제목' and item['business']=='원본 업무'
    assert item['purpose']==item['title_en']==item['message_en']==''
    # Caller objects are not mutated.
    assert source['catalog_fields']=={'business':'원본 업무','title':'원본 제목'}
