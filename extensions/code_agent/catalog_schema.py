"""Business columns shared by DB, JSON, UI and retrieval; legacy aliases stay internal."""
FIELDS=(('business','업무구분'),('message_type','타입'),('message_code','메시지코드'),
        ('purpose','용도'),('title','title'),('spelling_check','맞춤법검사'),
        ('title_en','영문 title'),('contents_en','영문 contents'),('notes','비고'),('added_date','추가날짜'))
EXTRA_COLUMNS=('business','message_type','purpose','title','spelling_check','title_en','contents_en','added_date')

def business_values(rec):
    old=rec.get('source',{}).get('catalog_fields',{})
    defaults={'business':old.get('business') or rec.get('menu',''),'message_type':old.get('message_type',''),
        'message_code':rec.get('code',''),'purpose':old.get('purpose') or rec.get('trigger',''),
        'title':rec.get('message',''),'spelling_check':'미검사','title_en':old.get('title_en',''),
        'contents_en':old.get('message_en',''),'notes':rec.get('notes',''),'added_date':''}
    return {key:rec.get(key) or defaults[key] for key,_ in FIELDS}

def normalized_record(rec):
    result=dict(rec)
    # New JSON uses message_code/title; older APIs still receive code/message aliases.
    result.setdefault('code',result.get('message_code',''))
    result.setdefault('message',result.get('title',''))
    result.update(business_values(result))
    return result

def export_record(rec):
    result=business_values(rec)
    result['_meta']={key:rec.get(key) for key in ('status','revision','source','menu','trigger')}
    return result
