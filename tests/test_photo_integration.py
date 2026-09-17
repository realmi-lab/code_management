import csv
import io
from catalog.compare import signature,compare_message
from catalog.ai import embedding_text
from .conftest import upload,commit


def test_photo_fields_copy_export_roundtrip(client):
    rows=[['업무구분','타입','메시지코드','용도','Title','Contents','영문Title','영문Contents'],
          ['기타업무','알럿','S-C-02','재확인','확인 제목','원문\n[확인]','Check','Original\n[OK]']]
    preview=upload(client,rows).json()
    assert not preview['errors']
    assert commit(client,preview).status_code==200
    copied=client.get('/api/codes/S-C-02/copy').json()['text']
    for literal in ['업무구분: 기타업무','타입: 알럿','용도: 재확인','타이틀: 확인 제목',
                    '표시 문구: 원문\n[확인]','영문타이틀: Check','영문컨텐츠: Original\n[OK]']:
        assert literal in copied
    exported=client.get('/api/export/codes.csv')
    data=list(csv.DictReader(io.StringIO(exported.text.lstrip('\ufeff'))))
    assert data[0]['타입']=='알럿'
    assert data[0]['영문컨텐츠']=='Original\n[OK]'
    repeat=client.post('/api/imports/preview',files={'file':('export.csv',exported.content)}).json()
    assert repeat['counts']['unchanged']==1
    assert repeat['records'][0]['title']=='확인 제목'


def test_photo_title_and_type_are_search_features(client):
    p=upload(client,[['메시지코드','타입','Title','Contents'],
                     ['S-A-1','컨펌','독특한테스트제목','내용입니다.']]).json()
    assert commit(client,p).status_code==200
    row=client.get('/api/codes/S-A-1').json()
    text=embedding_text(row)
    assert '독특한테스트제목' in text and '컨펌' in text
    found=client.post('/api/search',json={'query':'독특한테스트제목'}).json()
    assert found['results'][0]['code']=='S-A-1'
    assert row['message']=='내용입니다.'


def test_dollar_placeholder_change_is_reported():
    assert signature('$심볼명$ 렌딩')['placeholders']==['$심볼명$']
    existing={'message':'$심볼명$ 렌딩\n[확인]','status':'active'}
    result=compare_message('렌딩\n[확인]',existing)
    assert any('변수' in warning for warning in result['differences'])


def test_button_label_and_order_are_preserved():
    original='계좌를 연결해 주세요.\n[취소][계좌연결]'
    assert signature(original)['buttons']==['[취소]','[계좌연결]']
    result=compare_message('계좌를 연결해 주세요.\n[계좌연결][취소]',{'message':original,'status':'active'})
    assert any('버튼' in warning for warning in result['differences'])


def test_empty_new_fields_keep_old_embedding_text():
    assert embedding_text({'message':'기존문구','menu':'기존메뉴','trigger':'기존조건','title':''})=='기존문구\n기존메뉴\n기존조건'
