"""Bounded XLSX/CSV reader for code tables. No macros, formula execution, or rewriting.

XLSX is read as ZIP/XML with defusedxml. This intentionally does not implement Excel's
calculation engine, formatting-based numeric identifiers, charts, or legacy XLS.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import posixpath
import re
import zipfile
from pathlib import PurePath
from defusedxml import ElementTree as ET
from .models import canonical_code

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
ALIASES={
 'code':['코드번호','알림코드','메시지코드','메세지코드','코드','code','messagecode','id'],
 'message':['등록문구','표시문구','알림문구','메시지','메세지','문구','내용','message','text'],
 'menu':['사용메뉴','적용메뉴','메뉴','화면','menu','screen'],
 'trigger':['노출조건','사용조건','발생조건','조건','trigger','condition'],
 'notes':['비고','설명','참고','notes','description'],
 'status':['사용상태','상태','status'],
}
ACTIVE={'','active','사용중','사용','정상','활성','y'}
RETIRED={'retired','폐기','미사용','비활성','삭제','n','사용안함'}

class ImportError(ValueError):
    pass

def col_letter(index):
    result=''; index+=1
    while index:
        index,rem=divmod(index-1,26); result=chr(65+rem)+result
    return result

def col_index(address):
    match=re.match(r'^([A-Z]+)',address)
    if not match:
        raise ImportError('셀 주소가 올바르지 않습니다.')
    n=0
    for ch in match.group(1): n=n*26+ord(ch)-64
    return n-1

def plain_header(s):
    return re.sub(r'[\s_\-()]+','',s).lower()

def safe_filename(s):
    s=s.replace('\\','/').split('/')[-1]
    return re.sub(r'[\x00-\x1f]','',s)[:180] or 'upload.xlsx'

def read_xlsx(blob):
    try:
        z=zipfile.ZipFile(io.BytesIO(blob))
    except (zipfile.BadZipFile,ValueError) as exc:
        raise ImportError('올바른 .xlsx 파일이 아닙니다. 암호화 파일은 지원하지 않습니다.') from exc
    with z:
        infos=z.infolist()
        if len(infos)>2048 or sum(x.file_size for x in infos)>48*1024*1024:
            raise ImportError('압축 해제 크기 또는 내부 파일 수 제한을 초과했습니다.')
        names={x.filename for x in infos}
        if len(names)!=len(infos):
            raise ImportError('중복된 내부 경로가 있는 파일입니다.')
        if any('vbaproject' in n.lower() or n.startswith('xl/externalLinks/') for n in names):
            raise ImportError('매크로 또는 외부 연결이 포함된 파일은 지원하지 않습니다.')
        def xml(name):
            if name not in names: raise ImportError('필수 엑셀 구성요소가 없습니다: '+name)
            return ET.fromstring(z.read(name))
        strings=[]
        if 'xl/sharedStrings.xml' in names:
            for si in xml('xl/sharedStrings.xml').findall('m:si',NS):
                val=''.join(t.text or '' for t in si.findall('.//m:t',NS))
                if len(val)>20000 or len(strings)>100000:
                    raise ImportError('셀 텍스트 또는 공유 문자열 수가 너무 큽니다.')
                strings.append(val)
        wb=xml('xl/workbook.xml'); rels=xml('xl/_rels/workbook.xml.rels')
        targets={}
        for rel in rels:
            if rel.attrib.get('TargetMode')=='External': continue
            target=rel.attrib.get('Target','')
            target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            if not target.startswith('xl/') or '..' in target.split('/'): continue
            targets[rel.attrib.get('Id')]=target
        sheets=[]; total=0
        for sheet in wb.findall('m:sheets/m:sheet',NS):
            if len(sheets)>=30: raise ImportError('시트는 최대 30개까지 지원합니다.')
            target=targets.get(sheet.attrib.get('{'+NS['r']+'}id'))
            if not target: continue
            root=xml(target); rows={}; formulas=set(); count=0
            for row in root.findall('m:sheetData/m:row',NS):
                rnum=int(row.attrib.get('r','0'))
                if rnum<1 or rnum>20000: raise ImportError('행 번호가 허용 범위를 벗어났습니다.')
                vals={}
                for cell in row.findall('m:c',NS):
                    address=cell.attrib.get('r','')
                    cidx=col_index(address)
                    if cidx>=100: raise ImportError('시트당 최대 100개 열을 지원합니다.')
                    typ=cell.attrib.get('t',''); v=cell.find('m:v',NS)
                    val=v.text if v is not None and v.text is not None else ''
                    if typ=='s':
                        try: val=strings[int(val)]
                        except (ValueError,IndexError) as exc: raise ImportError('공유 문자열 참조가 잘못되었습니다.') from exc
                    elif typ=='inlineStr': val=''.join(t.text or '' for t in cell.findall('.//m:t',NS))
                    if cell.find('m:f',NS) is not None: formulas.add(address)
                    if len(val)>20000: raise ImportError('셀 텍스트가 너무 깁니다.')
                    vals[cidx]=val; count+=1
                    if count>250000: raise ImportError('셀 수 제한을 초과했습니다.')
                if any(str(v).strip() for v in vals.values()) or any(col_letter(c)+str(rnum) in formulas for c in vals):
                    rows[rnum]=vals; total+=1
                if total>12000: raise ImportError('전체 비어 있지 않은 행은 12,000개 이하로 나눠주세요.')
            merged=[]
            for cell in root.findall('m:mergeCells/m:mergeCell',NS):
                ref=cell.attrib.get('ref','')
                if ':' in ref: merged.append(ref)
            sheets.append({'name':sheet.attrib.get('name','Sheet'), 'rows':rows,'formulas':formulas,'merged':merged})
        return sheets

def read_csv(blob):
    try: text=blob.decode('utf-8-sig')
    except UnicodeDecodeError:
        try: text=blob.decode('cp949')
        except UnicodeDecodeError as exc: raise ImportError('CSV는 UTF-8 또는 CP949 인코딩이어야 합니다.') from exc
    if '\x00' in text: raise ImportError('CSV에 허용되지 않는 문자가 있습니다.')
    try: dialect=csv.Sniffer().sniff(text[:4096],delimiters=',;\t')
    except csv.Error: dialect=csv.excel
    rows={}; csv.field_size_limit(20000)
    for n,row in enumerate(csv.reader(io.StringIO(text),dialect),1):
        if n>12000: raise ImportError('CSV는 12,000행 이하로 나눠주세요.')
        if len(row)>100: raise ImportError('최대 100개 열을 지원합니다.')
        if any(v.strip() for v in row): rows[n]=dict(enumerate(row))
    return [{'name':'CSV','rows':rows,'formulas':set(),'merged':[]}]

def parse_upload(blob, filename, mapping=None):
    filename=safe_filename(filename); ext=PurePath(filename).suffix.lower()
    if ext=='.xlsx': sheets=read_xlsx(blob)
    elif ext=='.csv': sheets=read_csv(blob)
    else: raise ImportError('.xlsx 또는 .csv 파일만 지원합니다. .xls는 .xlsx로 저장해주세요.')
    records=[]; errors=[]; warnings=[]; sheet_info=[]
    mapping=mapping or {}
    for sheet in sheets:
        rows=sheet['rows']; manual=mapping.get(sheet['name'],{})
        header_row=manual.get('header_row'); columns={}; headers={}
        if header_row is not None and (not isinstance(header_row,int) or header_row<1):
            raise ImportError('헤더 행은 1 이상의 정수여야 합니다.')
        candidates=[header_row] if header_row else sorted(rows)[:30]
        for rn in candidates:
            raw=rows.get(rn,{})
            found={}
            for i,text in raw.items():
                for field, aliases in ALIASES.items():
                    if plain_header(str(text)) in aliases and field not in found: found[field]=i
            if 'columns' in manual:
                found={}
                for field,column in manual['columns'].items():
                    if field not in ALIASES or column in (None,''): continue
                    if not re.fullmatch(r'[A-Z]{1,2}',str(column).upper()): raise ImportError('열은 A, B, C 형식으로 지정해주세요.')
                    found[field]=col_index(str(column).upper())
            if 'code' in found and 'message' in found:
                header_row=rn; columns=found; headers=raw; break
        sheet_info.append({'name':sheet['name'],'header_row':header_row,'detected_columns':{k:col_letter(v) for k,v in columns.items()},
          'headers':[{'column':col_letter(i),'label':str(v)} for i,v in headers.items()],
          'sample_rows':[{'row':rn,'values':{col_letter(i):str(v) for i,v in rows[rn].items()}} for rn in sorted(rows)[:6]]})
        if not columns:
            warnings.append(f'{sheet["name"]}: 코드번호/문구 헤더를 찾지 못해 제외했습니다. 열 연결을 지정할 수 있습니다.'); continue
        context_fill={}
        for area in sheet['merged']:
            start,end=area.split(':'); c1,c2=col_index(start),col_index(end)
            r1=int(re.search(r'\d+$',start).group()); r2=int(re.search(r'\d+$',end).group())
            if r2-r1>12000: raise ImportError('병합 영역이 너무 큽니다.')
            # Fill contextual metadata only; NEVER silently fan out a merged code/message.
            for field in ('menu','trigger','notes','status'):
                c=columns.get(field)
                if c is not None and c1<=c<=c2:
                    for r in range(r1,r2+1): context_fill[(r,c)]=rows.get(r1,{}).get(c1,'')
            if r1>header_row and r2>r1 and any(c1<=columns[f]<=c2 for f in ('code','message')):
                errors.append(f'{sheet["name"]}!{area}: 코드번호/문구의 세로 병합을 해제하고 항목별로 작성해주세요.')
        for rn,raw in sorted(rows.items()):
            if rn<=header_row: continue
            values={f:str(raw.get(c,context_fill.get((rn,c),''))) for f,c in columns.items()}
            if not any(v.strip() for v in values.values()): continue
            loc=f'{sheet["name"]}!{rn}행'
            if any(col_letter(c)+str(rn) in sheet['formulas'] for c in columns.values()):
                errors.append(f'{loc}: 수식 셀이 있습니다. 값을 확정한 후 값으로 붙여넣어주세요.'); continue
            try: code=canonical_code(values.get('code',''))
            except ValueError as exc: errors.append(f'{loc}: {exc}'); continue
            message=values.get('message','')
            if not message.strip() or len(message)>4000:
                errors.append(f'{loc}: 문구는 공백이 아닌 1~4,000자여야 합니다.'); continue
            if any('\x00' in v for v in values.values()): errors.append(f'{loc}: NUL 문자는 지원하지 않습니다.'); continue
            state=plain_header(values.get('status',''))
            if state in ACTIVE: status='active'
            elif state in RETIRED: status='retired'
            else: errors.append(f'{loc}: 알 수 없는 상태 {values["status"]!r}. 사용 중/폐기로 지정해주세요.'); continue
            if len(values.get('menu',''))>200 or len(values.get('trigger',''))>1000 or len(values.get('notes',''))>2000:
                errors.append(f'{loc}: 메뉴/조건/비고 길이 제한을 초과했습니다.'); continue
            cell_map={f:col_letter(c)+str(rn) for f,c in columns.items()}
            records.append({'code':code,'message':message,'menu':values.get('menu',''),
                'trigger':values.get('trigger',''),'notes':values.get('notes',''),'status':status,
                'source':{'filename':filename,'sheet':sheet['name'],'row':rn,
                          'cells':', '.join(cell_map.values()),'cell_map':cell_map,'kind':'import',
                          'sha256':hashlib.sha256(blob).hexdigest()}})
    if not records and not errors: errors.append('가져올 항목이 없습니다. 코드번호/문구 열 연결을 확인해주세요.')
    if len(records)>10000: errors.append('최대 10,000개 항목까지만 가져올 수 있습니다.')
    seen=set()
    for record in records:
        if record['code'] in seen: errors.append(f'{record["code"]}: 파일 안에 같은 코드번호가 두 번 이상 있습니다.')
        seen.add(record['code'])
    return {'records':records,'errors':errors[:150],'warnings':warnings[:100],'sheets':sheet_info,'filename':filename}

def annotate_preview(parsed, db, ns):
    with db.connect() as con:
        con.execute('BEGIN')
        existing={c['code']:c for c in db.all_codes(ns,True,con)}
        version=db.version(ns,con)
        con.execute('COMMIT')
    texts={}
    for c in existing.values(): texts.setdefault(c['message'],[]).append(c['code'])
    counters={'new':0,'unchanged':0,'conflict':0}
    for rec in parsed['records']:
        old=existing.get(rec['code'])
        if not old: rec['action']='new'
        elif all(rec.get(k,'')==old.get(k,'') for k in ('message','menu','trigger','notes','status')): rec['action']='unchanged'
        else: rec['action']='conflict'; rec['existing']=old
        counters[rec['action']]+=1
        rec['same_message_codes']=[c for c in texts.get(rec['message'],[]) if c!=rec['code']]
        texts.setdefault(rec['message'],[]).append(rec['code'])
    parsed['counts']=counters; parsed['catalog_version']=version
    return parsed
