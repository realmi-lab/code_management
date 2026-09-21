"""Generate 300 explicitly synthetic JSON records; never writes to a database."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'extensions/code_agent/data'

def main():
    original=(DATA/'github_samples.json').read_bytes()
    original_provenance=json.loads((DATA/'github_samples.provenance.json').read_text())
    assert hashlib.sha256(original).hexdigest()==original_provenance['sha256']
    records=json.loads(original)
    # Domain + user action make each synthetic message meaningful and distinct.
    domains=[('회원가입','가입 신청'),('본인인증','본인인증'),('로그인','로그인'),('비밀번호','비밀번호 변경'),
      ('기기관리','기기 등록'),('보안설정','보안 설정 변경'),('계좌관리','계좌 등록'),('원화입금','원화 입금 신청'),
      ('원화출금','원화 출금 신청'),('가상자산입금','입금 주소 발급'),('가상자산출금','가상자산 출금 신청'),
      ('매수주문','매수 주문'),('매도주문','매도 주문'),('주문취소','주문 취소'),('예약주문','예약 주문'),
      ('알림설정','알림 설정 변경'),('고객문의','문의 접수'),('API관리','API 키 발급'),('주소록','출금 주소 등록'),('회원탈퇴','탈퇴 신청')]
    scenarios=[
      ('완료','toast','{action}이 완료되었습니다.','요청이 정상 처리된 경우','처리 결과 안내'),
      ('처리 중','banner','{action}을 처리하고 있습니다. 잠시만 기다려주세요.','처리 요청 후 결과를 기다리는 경우','진행 상태 안내'),
      ('재시도','alert','{action}에 실패했습니다. 잠시 후 다시 시도해주세요.','일시적인 처리 오류가 발생한 경우','오류 안내'),
      ('필수 항목','alert','{action}에 필요한 항목을 모두 입력해주세요.','필수 입력 항목이 비어 있는 경우','입력값 검증'),
      ('입력 확인','inline','{action} 정보를 다시 확인해주세요.','입력 형식 또는 입력값이 유효하지 않은 경우','입력값 검증'),
      ('30초 대기','alert','{action}은 30초 이후에 다시 시도해주세요.','직전 요청 후 30초가 지나지 않은 경우','재요청 대기 안내'),
      ('30초 제한','banner','{action}을 30초 이내에 완료해주세요.','처리 유효시간이 30초인 합성 시나리오','유효시간 안내'),
      ('횟수 초과','alert','{action} 시도 횟수가 5회를 초과했습니다. 10분 후 다시 시도해주세요.','시도 횟수가 5회를 초과한 합성 시나리오','요청 제한 안내'),
      ('중복 요청','toast','이미 {action}을 요청했습니다. 처리 결과를 확인해주세요.','동일한 요청이 이미 접수된 경우','중복 요청 안내'),
      ('로그인 필요','alert','{action}을 진행하려면 먼저 로그인해주세요.','로그인하지 않은 상태에서 요청한 경우','접근 조건 안내'),
      ('확인','confirm','{action}을 진행하시겠습니까?','최종 실행 전 사용자 확인이 필요한 경우','실행 확인'),
      ('취소','confirm','진행 중인 {action}을 취소하시겠습니까?','진행 중 작업의 취소를 선택한 경우','취소 확인'),
      ('남은 시간','banner','{action}은 {seconds}초 후에 다시 요청할 수 있습니다.','재요청 대기시간을 변수로 표시하는 경우','동적 시간 안내'),
      ('구버전','alert','현재 {action}을 이용할 수 없습니다.','폐기된 합성 정책의 문구 확인용','폐기 문구 검토'),
    ]
    def add(business,action,title,kind,message,trigger,purpose,retired=False):
        n=len(records)-15
        consonant=(ord(action[-1])-0xAC00)%28 != 0
        for suffix,alternate in [('이','가'),('을','를'),('은','는')]:
            message=message.replace('{action}'+suffix,action+(suffix if consonant else alternate))
        records.append({'code':f'SM-{1000+n}','message':message.replace('{action}',action),
          'menu':business,'trigger':trigger,'notes':'AI가 만든 합성 테스트 자료입니다. 실제 회사 정책·한도·등록 코드가 아닙니다.',
          'status':'retired' if retired else 'active','revision':1,
          'source':{'kind':'synthetic_json','synthetic':True,'filename':'sample_catalog_300.json',
            'catalog_fields':{'business':business,'message_type':kind,'title':business+' · '+title,'purpose':purpose}}})
    for business,action in domains:
        for title,kind,message,trigger,purpose in scenarios:
            add(business,action,title,kind,message,trigger,purpose,title=='구버전')
    for title,message,trigger in [
        ('최소 금액','출금 금액은 1,000원 이상 입력해주세요.','최소 금액보다 작은 값을 입력한 합성 사례'),
        ('최대 금액','출금 금액은 1,000,000원 이하로 입력해주세요.','최대 금액보다 큰 값을 입력한 합성 사례'),
        ('24시간 제한','보안 설정 변경 후 24시간 동안 출금할 수 없습니다.','보안 설정 변경 후 24시간이 지나지 않은 합성 사례'),
        ('48시간 제한','보안 설정 변경 후 48시간 동안 출금할 수 없습니다.','보안 설정 변경 후 48시간이 지나지 않은 합성 사례')]:
        add('조건비교','출금',title,'alert',message,trigger,'숫자·조건 차이 비교')
    assert len(records)==300 and len({r['code'] for r in records})==300
    english_original=[
      'Please authenticate at least 30 seconds after checking the menu.',
      'A verification code has been sent.','Please check the verification code.',
      'The verification code has expired. Please request a new one.',
      'Please complete authentication within 30 seconds.',
      'You can request another verification code in {seconds} seconds.',
      'This phone number is already registered. Please log in.',
      'Please agree to the required terms.','This email address is available.',
      'This email address is already in use.','Please check your password.',
      'Please log in.','Leave without saving your changes?',
      'Check your network connection and try again.','You do not have permission to access this.',
      'Please authenticate again in 10 seconds.']
    actions_en=['Sign-up','Identity verification','Login','Password change','Device registration',
      'Security settings change','Bank account registration','KRW deposit request','KRW withdrawal request',
      'Deposit address generation','Crypto withdrawal request','Buy order','Sell order','Order cancellation',
      'Scheduled order','Notification settings change','Support inquiry','API key generation','Withdrawal address registration','Account closure']
    templates_en=['{a} is complete.','{a} is being processed. Please wait.',
      '{a} failed. Please try again later.','Please fill in all required fields for {a}.',
      'Please check the information for {a}.','Please wait 30 seconds before retrying {a}.',
      'Please complete {a} within 30 seconds.','You have exceeded 5 attempts for {a}. Please try again in 10 minutes.',
      '{a} has already been requested. Please check the result.','Please log in to proceed with {a}.',
      'Do you want to proceed with {a}?','Do you want to cancel the ongoing {a}?',
      'You can request {a} again in {{seconds}} seconds.','{a} is currently unavailable.']
    final_en=['Please enter a withdrawal amount of at least KRW 1,000.',
      'Please enter a withdrawal amount no greater than KRW 1,000,000.',
      'Withdrawals are unavailable for 24 hours after changing security settings.',
      'Withdrawals are unavailable for 48 hours after changing security settings.']
    converted=[]
    for i,r in enumerate(records):
        f=r['source'].get('catalog_fields',{})
        en=english_original[i] if i<16 else templates_en[(i-16)%14].format(a=actions_en[(i-16)//14]) if i<296 else final_en[i-296]
        converted.append({'business':f.get('business') or r['menu'],'message_type':f.get('message_type') or 'alert',
          'message_code':r['code'],'purpose':f.get('purpose') or r['trigger'],'title':r['message'],
          'spelling_check':'미검사','title_en':en,'contents_en':en,'notes':r['notes'],
          'added_date':'2026-09-21','_meta':{k:r[k] for k in ('status','revision','source','menu','trigger')}})
    records=converted
    raw=(json.dumps(records,ensure_ascii=False,indent=2)+'\n').encode()
    (DATA/'sample_catalog_300.json').write_bytes(raw)
    provenance={'schema_version':2,'count':len(records),'synthetic':True,'original_github_samples':16,
      'new_synthetic_samples':284,'generator':'scripts/generate_catalog_samples.py',
      'original_provenance':'github_samples.provenance.json','sha256':hashlib.sha256(raw).hexdigest(),
      'active':sum(r['_meta']['status']=='active' for r in records),'retired':sum(r['_meta']['status']=='retired' for r in records)}
    (DATA/'sample_catalog_300.provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(provenance,ensure_ascii=False))
if __name__=='__main__':main()
