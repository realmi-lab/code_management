# DB 합성 샘플 300건 · JSON 초기 자료

현재 정본은 PostgreSQL `cm_sample_codes`입니다. 아래 JSON은 최초 이전 자료이며 최초 1회 이후 읽기·검색은 DB에서 수행합니다. JSON 파일 재생성은 이미 이전한 DB를 변경하지 않습니다.


화면의 엑셀/CSV 가져오기 메뉴·버튼·파일 선택 폼·드래그 영역은 제거했다. 전체 코드는 기본으로 JSON 샘플을 보여준다. 실제 목록은 선택창에서 전환할 수 있다.

- 원본 파일: `extensions/code_agent/data/sample_catalog_300.json`
- 총 300건: 기존 GitHub 예시 16건 + 새 합성 예시 284건
- 사용 중 279건 / 폐기 21건
- 회원가입·본인인증·로그인·비밀번호·기기관리·보안설정·계좌관리·원화입출금·가상자산입출금·매수/매도·주문취소·예약주문·알림설정·고객문의·API관리·주소록·회원탈퇴
- 원본 기록은 JSON 배열이며 모든 항목에 `_meta.source.synthetic: true`를 표시한다. 실제 운영 DB를 채우거나 기존 자료를 덮어쓰지 않는다.

## 항목 구조

아래는 실제 생성 파일의 예시다. 샘플 문구와 시간·금액·횟수는 테스트용이며 회사 정책을 나타내지 않는다.

```json
{
  "business": "회원가입",
  "message_type": "toast",
  "message_code": "SM-1001",
  "purpose": "처리 결과 안내",
  "title": "가입 신청이 완료되었습니다.",
  "spelling_check": "미검사",
  "title_en": "Sign-up is complete.",
  "contents_en": "Sign-up is complete.",
  "notes": "AI가 만든 합성 테스트 자료입니다. 실제 회사 정책·한도·등록 코드가 아닙니다.",
  "added_date": "2026-09-21",
  "_meta": {
    "status": "active",
    "revision": 1,
    "source": {
      "kind": "synthetic_json",
      "synthetic": true,
      "filename": "sample_catalog_300.json",
      "catalog_fields": {
        "business": "회원가입",
        "message_type": "toast",
        "title": "회원가입 · 완료",
        "purpose": "처리 결과 안내"
      }
    },
    "menu": "회원가입",
    "trigger": "요청이 정상 처리된 경우"
  }
}
```

`GET /api/code-catalog/export.json?namespace=demo`와 화면의 **JSON 내보내기**는 `schema_version`, `namespace`, `synthetic`, `catalog_version`, `total`, `items`를 가진 객체를 반환한다. 전체 300건을 `items`에 담으며 로그인 신원 검사를 유지한다. 실제 목록 내보내기는 `namespace=production`이다.

문구 비교와 기획서 검토의 원문·규칙 모드에서 사용할 수 있다. 샘플은 운영 검색 인덱스와 분리된 전용 인덱스로 대화 검색에 연결한다. 샘플 대화 기록은 실제 목록 대화 기록과 구분한다. 원본 16건의 파일·Git blob 출처는 별도로 보존했고, 현재 파일은 로드할 때 SHA-256을 검증한다.

다음 명령은 합성 JSON 파일과 무결성 정보를 재생성한다. DB를 변경하지 않는다.

```bash
python3 scripts/generate_catalog_samples.py
```

## 업무 DB 구조 (schema_version 2)

업무구분 business, 타입 message_type, 메시지코드 message_code, 용도 purpose, title, 맞춤법검사 spelling_check, 영문 title title_en, 영문 contents contents_en, 비고 notes, 추가날짜 added_date 순서다. 기존 알림 원문은 title에 보존한다. 추가날짜는 YYYY-MM-DD이며 기존 자료의 날짜를 알 수 없으면 빈 값으로 둔다. 합성 샘플의 추가날짜는 재구성일 2026-09-21이다. 맞춤법 검사 결과를 만들지 않고 미검사로 둔다. 영문 예시는 합성 테스트 번역이다.

cm_codes에 업무 필드를 실제 컬럼으로 추가하고 message_code는 기존 code에서 생성하는 컬럼으로 동일성을 보장한다. 기존 code/message API는 호환용으로 유지하며 title 변경 시 message도 함께 갱신한다. 상태·개정·출처·메뉴·노출 조건은 JSON의 _meta에 보존한다. 원문 DB, 승인·감사 기록은 삭제하지 않는다. 새 데이터로 Elasticsearch와 로컬 multilingual-e5-base PGVector를 함께 재색인한다.