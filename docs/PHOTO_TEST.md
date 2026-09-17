# 사진 데이터 테스트 서버

작성일: 2026-09-17.

## 접속 및 실행

- Docker Local 실행 PC 기준 URL: http://localhost:2999/code-management/
- 앱 내부 주소: http://127.0.0.1:8767/
- 화면 이름: 사진 테스트 목록.
- 전용 데이터: `/shared/code_management/data/photo-test`.
- 입력 JSON/CSV: `/shared/code_management/data/photo-test-input/7360-transcription.json`, `.csv`.
- 인증과 모델 연결은 기존 `.env`를 사용합니다. 키를 문서나 URL에 넣지 않습니다.
- 기존 앱의 8766 포트와 운영 DB는 유지합니다. 사진 데이터는 독립 DB에만 적재했습니다.

```bash
supervisorctl -c /shared/code_management/deploy/photo-test-supervisor.conf status
supervisorctl -c /shared/code_management/deploy/photo-test-supervisor.conf restart code-management-photo-test
```

전체 Docker Local 재부팅 후 전용 Supervisor가 없다면 다음으로 시작합니다.

```bash
supervisord -c /shared/code_management/deploy/photo-test-supervisor.conf
```

라우트: `/shared/nginx/routes.d/40-code-management.conf`. 기존 Nginx include를 사용하고 원래 Host/Origin을 유지합니다. 보호된 인프라 라우트는 변경하지 않았습니다. `nginx -t` 성공 후 reload만 수행했습니다.

## 데이터의 의미

사용자가 대화에서 확인한 `7360.jpg` 판독본 33건을 API 미리보기/확정 흐름으로 적재했습니다. 합성 예시와 원본 엑셀로 확인된 회사 목록 모두와 구분되는 사진 테스트 데이터입니다.

- 사진의 실제 `S-T-*`, `S-A-*`, `S-C-*` 번호를 보존합니다.
- S-C-2의 타입은 사진에 적힌 알럿으로 유지합니다.
- 줄바꿈·버튼·변수·빈 용도·빈 타이틀을 유지합니다.
- 잘린 타이틀의 …는 판독본의 생략 표시이며 원본에 존재한다고 확정하지 않습니다.
- S-A-14 업무구분은 판독하지 못해 비워두었습니다. S-A-18 괄호와 S-A-24 변수 구분자는 확인 필요로 표시합니다.
- 사진 밖 영문 컬럼과 마지막 컬럼의 값은 알 수 없어 `source.unobserved_fields`에 기록합니다. 저장된 빈 문자열을 원본 빈 셀의 증거로 해석하지 않습니다.
- 각 항목에 사진 파일명·SHA-256·판독 메모와 review_required를 기록하고 화면·복사에 표시합니다. CSV의 셀 주소는 판독본 CSV 위치이며 원본 엑셀 주소가 아닙니다.
- `scripts/load_photo_test.py`는 전용 경로에만 적재하며 같은 자료로 재실행해도 중복 삽입하지 않습니다. 다른 기존 자료는 덮어쓰지 않습니다.

## 구현

- 업무구분, 타입, 용도, 타이틀, 영문타이틀, 영문컨텐츠를 별도 필드로 가져와 `source.catalog_fields`에 원문 보존하고 API 최상위 필드로 노출합니다.
- CSV/XLSX 별칭, 여러 시트, 세로 병합된 2단 헤더를 지원합니다. 메뉴·노출 조건은 별도 유지합니다.
- 메타데이터만 달라져도 가져오기 충돌 확인을 요구합니다.
- 카드·상세·목록·복사·CSV 내보내기·검색에서 새 필드를 사용합니다. 초안 API의 여섯 필드 작성/편집 확장은 이번 테스트 범위에 포함하지 않습니다.
- `$심볼명$` 자리표시자와 버튼 순서 차이를 비교·AI 원문 보호 검사에 반영합니다.
- 하위 경로 정적 자산/API/세션 저장을 지원해 직접 앱 포트와 `/code-management/` 모두 동작합니다.

## 검증 결과

- 전체 자동 테스트 **151개 통과** (`photo-tests.xml`). 새 스키마 17개와 통합 5개 회귀 테스트 포함.
- 실제 HTTP/Nginx/Chromium 브라우저 **11개 확인 통과**, JavaScript 오류 0개. 실제 사진 테스트 DB에 대한 읽기 전용 검사, 별도 브라우저 컨텍스트, offline harness 없음 (`photo-browser-check.json`).
- 브라우저는 인증·프록시 API 경로·목록33·타입/제목·사진 경고·줄바꿈·기본 검색·예시 분리·390px 표시·잠금 시 자료 제거를 검사했습니다.
- 실제 Command Code DeepSeek V4.1 Flash / Low 검색 3건 성공 (`photo-agent-check.json`). 요청/관측 모델과 effort 일치, 반환 문구가 판독본과 같은지 대조했습니다.

| 질문 요지 | 첫 번째 코드 | 단일 호출 관측 시간 |
|---|---|---:|
| 네트워크 연결 오류 후 재시도 | S-A-19 | 3.98초 |
| 쿠폰 구매 완료 | S-A-14 | 4.44초 |
| 렌딩 한도 소진 | S-A-23 | 4.36초 |

이 세 사례는 전체 질문의 정확도나 응답시간 보장이 아닙니다. 원본 엑셀 전체의 모든 시트는 아직 받지 않아 검증하지 않았습니다.

JS 구문·vendor 체크섬·Nginx 설정 검사가 통과했고 전용 서버는 Supervisor RUNNING 상태입니다.
