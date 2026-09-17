# 구현 검증 기록

작성일: 2026-09-17

## 최신: Taste 설정8 / 6 / 4 적용

- 사용자 지정 `DESIGN_VARIANCE: 8`, `MOTION_INTENSITY: 6`, `VISUAL_DENSITY: 4`를 CSS와 디자인 기준에 기록하고 실제 화면에 반영.
- 데스크톱 검색 입력·옵션을 비대칭 배치. 첫 결과는 코드·본문 영역으로 분할하고 전체 폭에 표시, 후속 결과2열. 모바일1열, 검색 순위와 원문 유지.
- 페이지·결과 순차 등장, 상세창 전환, hover/active 효과 추가. 동작 줄이기에서는 애니메이션·이동 효과 없음.
- 자동 테스트151개·JS 구문·vendor 검사 통과 (`taste-dials-tests.xml`).
- 실제 HTTP 사진목록12개 및 설정·레이아웃·정상 모션5개 확인 통과.1440/1024/850/390px에서 순서·본문14px·원문·가로 넘침 검사 (`taste-dials-browser.json`).
- 좁은 초안 비교 영역은1열 유지. 긴 코드·업무명 잘림을 수정하고1440/1024/850/390/320px에서 재확인. 펼친 출처·줄바꿈·reduced-motion 검사 통과 (`dials-review.json`).
- JavaScript 오류0. offline harness·실제 모델 호출·카탈로그 수정 없음. 긴 문자열은 브라우저 DOM에만 넣은 합성 검증.

## 이전: Taste Skill 기반 UI 개선

- 지정 저장소의 `redesign-skill`과 `minimalist-skill`을 읽고 적용. 기존 HTML/JavaScript/CSS 구조 유지. 출처·디자인 기준: `UI_DESIGN.md`.
- 중립색과 차콜 버튼, 절제된 녹색 상태, 통일된 Phosphor 아이콘 및 자체 제공 Pretendard 적용. 검색·목록·상세·폼·모바일 간격과 계층 정돈.
- 기본14px 및 대괄호 포함 원문 표시 유지. 데이터·모델 설정·업무 동작 변경 없음.
- 자동 테스트 **151개**, JS 구문·vendor 검사 통과 (`taste-ui-tests.xml`).
- 실제 HTTP 브라우저 업무 검사 **19개 통과**: 사진 목록12개와 임시 DB/모의 모델 업무 흐름7개. offline harness 없음. 실제 목록이나 운영 DB에 테스트 쓰기 없음.
- 추가 화면 검사 **5개 통과** (`taste-ui-browser.json`): 8개 화면을1440/390/320px로 확인, 가로 넘침 없음. 주요 글자 대비 표본5.49:1 이상, 키보드 포커스 확인.
- JavaScript 오류0, 자산 로딩 실패0, 브라우저 외부 CDN 요청0. 데스크톱 검색·목록·상세 및 모바일 스크린샷 확인.
- 기존 주소와 서버 유지. 정적 파일에 즉시 반영되며 새로고침으로 확인 가능.

## 이전: 메시지 버튼 표시 원복

- 사용자 요청으로 버튼 미리보기 변환을 취소. 검색·목록·상세·초안에 `[나가기]`, `[확인]` 등 원문 표기를 복원.
- 관련 파서·버튼 스타일·중복 원문 펼쳐보기 제거. 간결한 UI와 기본14px 유지. DB 변경 없음.
- 자동 테스트 **151개**, JS 구문·vendor 검사 통과 (`raw-message-restore-tests.xml`).
- 실제 HTTP/Nginx 브라우저 **12개 통과**, JS 오류0. 원문 표시·복사·편집·줄바꿈·변수·모바일14px 및 가로 넘침 확인. offline harness·모델 호출·카탈로그 수정 없음 (`photo-browser-check.json`).

## 이전: 메시지 버튼 미리보기

- 끝부분의 `[확인]`, `[나가기]`, `[닫기][로그인]`을 본문 아래 버튼으로 표시. 검색 결과·전체 목록·상세·초안에 공통 적용.
- 미리보기 버튼은 동작하지 않으며, 순서·본문 줄바꿈·변수 유지. 상세에서 원문 펼쳐보기 제공. 저장·복사·편집·내보내기 데이터 경로 변경 없음.
- 본문 중간 대괄호·등록 연결 표식·빈/잘못된 대괄호는 버튼으로 변환하지 않음. 본문과 라벨 HTML 이스케이프 유지.
- 자동 테스트 **151개**, JS 구문·vendor 무결성 통과 (`button-preview-tests.xml`).
- 실제 HTTP/Nginx Chromium 확인 **13개 통과**, JS 오류0 (`photo-browser-check.json`). 사진 자료로 버튼 순서·줄바꿈·변수·복사 및 편집 원문·목록·14px·390px 모바일 가로 넘침 확인. 별도 합성 문자열로 파서 경계와 HTML 이스케이프 확인.
- offline harness·모델 호출·카탈로그 수정 없음. 데스크톱과 모바일 스크린샷 확인 완료.

## 이전: 기본 글자 14px 적용

- 본문·메뉴·입력·버튼·표·보조 문구를 기본14px로 적용, 제목/아이콘 계층 유지.
- 실제 HTTP Chromium에서 데스크톱·390px 모바일 계산 글자 크기14px 및 문서 가로 넘침 없음 확인. offline harness와 모델 호출 없음.
- 기존 자동 테스트151개·JS 구문·vendor 검사 통과.

## 이전: 간결한 UI 적용

- 소개 문구·3단계 가이드·큰 통계 카드 제거, 검색창과 결과를 1열로 배치.
- 반복 안내·사진 판독 메모·AI 설명은 펼쳐보는 방식으로 변경. 원문·변수·버튼 표기는 유지.
- 초안·목록·가져오기·설정 문구와 여백 축소. 기존 데이터/API/인증/모델 설정 유지.
- 자동 테스트151개·JS 구문·vendor 검사 통과 (`compact-ui-tests.xml`).
- 실제 HTTP 브라우저18개 확인 통과(사진목록11 + 임시 DB 업무흐름7), JS 오류0. offline harness 없음. 추가 데스크톱/390px 시각 확인 완료.
- 화면 변경은 실행 중 서비스의 정적 파일에 즉시 반영. 접속 주소 `/code-management/` 유지.

## 이전: 사진 데이터 33건 및 실제 스키마 검증

- 전체 자동 테스트 **151개 통과** (`photo-tests.xml`).
- 실제 HTTP/Nginx 브라우저 확인 **11개 통과**, JavaScript 오류 0개, offline harness 없음 (`photo-browser-check.json`).
- 사진 테스트 목록에 33건 적재. 원본 사진 판독 상태/불확실성 표시, 운영 DB와 분리.
- 실제 DeepSeek V4.1 Flash / Low 검색 3건에서 각각 S-A-19, S-A-14, S-A-23을 첫 후보로 반환. 원문 대조 통과 (`photo-agent-check.json`).
- 접속: `http://localhost:2999/code-management/` (Docker 실행 PC 기준), 내부 포트8767. 기존 앱8766 유지.
- 상세 실행·범위·원본 확인 항목: `PHOTO_TEST.md`.

## 이전: 버그 수정·최적화 검증

- 전체 자동 테스트 **129개 통과**, 오류·실패·건너뜀 0개 (`bugfix-tests.xml`).
- 직접 HTTP 브라우저 확인 **18개 통과**: 기존 업무 흐름 7개와 지연 응답/중복 저장/잠금 회귀 11개. JavaScript 오류 0개. 임시 DB 사용, offline harness 사용 안 함 (`completion-browser-check.json`, `bugfix-browser-check.json`).
- 실행 앱 재시작 후 실제 DeepSeek V4.1 Flash / Low 검색 성공, 요청·관측 모델 설정 일치 (`bugfix-live-ai-check.json`).
- 목록 집계 42.092ms → 0.596ms, 30건 페이지 조회 40.582ms → 0.495ms. 합성 10,000건 DB 구간만의 7회 중앙값 (`optimization-benchmark.json`).
- JS 구문·vendor 무결성 통과. 전용 Supervisor RUNNING. 실제 목록·초안 0개 유지.
- 변경 내용과 재현 명령은 `BUGFIX_OPTIMIZATION.md` 참고.

이하 내용은 이전 단계의 검증 이력입니다. 최초 전달 당시의 Docker Local·모델 연결 불가 기록은 현재 상태가 아닙니다.

## 미완성 흐름 구현 후 검증

- 자동 테스트 **90개 통과** (`completion-tests.xml`).
- 실제 HTTP 브라우저 7개 확인 항목 통과: 접속, 초안 작성·수정, 엑셀 요청·가져오기·연결, AI 검색 UI, 기본 검색 전환, 모바일 가로 넘침 없음, JavaScript 오류 없음.
- 브라우저 검사는 임시 DB와 모의 모델을 사용했고 **offline harness를 사용하지 않았습니다** (`completion-browser-check.json`).
- 별도 실제 DeepSeek V4.1 Flash / Low 상황 검색 성공: 중복 가입 질문을 검색 표현으로 변환하고 예시 코드 EX-0201을 첫 후보로 반환 (`completion-live-ai-check.json`).
- JS 구문과 원본 vendor 무결성 검사 통과. 실제 회사 목록은 아직 비어 있습니다.

## 후속 연결 검증

Docker Local에서 Command Code 연결 후 자동 테스트 **73개 통과**, JS 구문 검사와 vendor 무결성 검사를 통과했습니다. 실제 DeepSeek V4.1 Flash / Low 합성 문구 호출도 성공했습니다. 현재 기록은 `COMMAND_CODE_CONNECTION.md`, `command-code-live-check.json`, `command-code-tests.xml`을 참고하세요. 아래 내용은 최초 전달본의 검증 이력입니다.

## 최초 전달 당시 배포 상태

이 프로젝트는 별도 작업 컨테이너의 `code_management` 폴더에서 구현했습니다. 사용자 Docker Local 호출은 `FORBIDDEN: This conversation does not support developer MCPs`로 실패했습니다. **사용자 Docker Local의 폴더 생성·설치·실행은 수행하지 못했습니다.** 사용자 기존 앱이나 저장소를 수정하지 않았습니다.

`urstory-rag` 전체를 배포한 버전이 아닙니다. 고정 커밋 `75661c676aec650e52f75dd068b687a4cb6a63b7`의 RRFCombiner를 재사용한 독립 애플리케이션이며, 사용 범위는 `UPSTREAM.md`에 명시했습니다.

## 실제 수행 결과

| 검증 | 결과 | 범위 |
|---|---|---|
| 백엔드 자동 테스트 | **65개 통과** | API, 엑셀·CSV 입력, 원문 보존, 코드 조회, 비교, 초안·승인, 권한, 동시성, 모의 AI 응답 |
| 실행 코드 줄 커버리지 | **93.38%** | `catalog`와 `vendor.urstory_rag` 931/997문; 프론트엔드 및 Docker 제외 |
| Chromium UI 검사 | **14개 흐름 통과** | 오프라인 자산 로드 + 실제 FastAPI TestClient API 연결 |
| 브라우저 JavaScript 오류 | **0개** | 위 UI 검사에서 수집한 오류 |
| 실행·키·백업 검사 | **6개 통과** | Python 네이티브 서버의 실제 로컬 HTTP, 키 생성·미덮어쓰기, 인증, 백업 일관성 |
| 프론트엔드 구문 검사 | 통과 | `node --check static/app.js` |
| 재사용 소스 무결성 | 통과 | `scripts/verify_vendor.py` 로컬 SHA-256 확인 |
| Compose/Dockerfile | 정적 점검만 수행 | YAML 구문·포트·볼륨·권한 구성 확인. Docker 엔진 없음 |
| 엑셀 양식 | 생성·내용 검사·미리보기 확인 | 빈 `.xlsx` 양식, 숫자형이 아닌 코드번호, 안내 시트 |

실행 환경은 Python 3.13.5이며 실제 회사 자료가 아닌 합성 데이터로 검사했습니다. 커버리지는 업무 정확도나 보안 완전성을 의미하지 않습니다.

## 자동 테스트가 확인한 중요한 동작

- 실제 목록과 예시 목록을 분리하고 실제 목록은 초기 빈 상태로 둡니다.
- 정확한 코드 조회 시 원문·공백·줄바꿈·변수를 유지합니다. 없는 코드를 만들어 반환하지 않습니다.
- 상황 검색은 재사용 확정이 아니라 관련 후보를 표시합니다.
- 문구 비교는 수치·단위, `이후/이내`, 일부 부정 표현, 자리표시자 차이를 표시합니다. 모든 의미를 판별하지는 않습니다.
- XLSX 헤더 연결·셀 위치·파일 해시를 보존하고 수식·위험한 XML을 거절합니다.
- 업로드는 미리보기와 확정으로 분리합니다. 같은 번호의 원문이 다르면 항목별 선택과 사유 없이 갱신하지 않습니다.
- 목록 버전이 바뀌면 가져오기 및 승인에서 재검토를 요구합니다. 같은 요청·번호를 중복 등록하지 않습니다.
- 초안에는 정식 번호가 없고, 엑셀 공식 목록 모드에서는 앱이 번호를 발급하지 않습니다.
- 시스템 공식 목록 모드의 승인·번호 발급·변경 이력을 별도 검증합니다.
- 기본 설정에서 AI 데이터 전송은 없습니다. 모델 응답 계약 검사는 모의 서버·응답으로만 수행했습니다.

## 브라우저 검사의 정확한 범위

환경 정책으로 Chromium이 `http://127.0.0.1`에 직접 이동하는 요청은 `ERR_BLOCKED_BY_ADMINISTRATOR`로 거절되었습니다. 정책을 변경하거나 비활성화하지 않았습니다.

대신 직접 생성한 로컬 HTML/CSS/JS를 Chromium에 로드하고, fetch를 실제 FastAPI TestClient에 연결하여 클릭·입력·파일 선택·DOM 표시를 검증했습니다. sessionStorage와 clipboard에는 테스트용 대체 구현을 사용했습니다. 따라서 이 결과는 **실제 브라우저 UI 검사이지만 직접 HTTP E2E 검증은 아닙니다.** 브라우저의 CSP·네이티브 클립보드 권한·실제 네트워크 전달은 검증하지 않았습니다.

별도의 Python 네이티브 서버 검사에서는 실제 loopback HTTP로 health, 접속 키 검증과 정적 파일 제공을 확인했습니다. 이것은 브라우저의 정책·권한 검증을 대신하지 않습니다.

UI 검사는 접속, 코드 조회, 원문 복사 내용, 상세/출처, 상황 검색, 조건 비교, 초안, 데모 승인, 파일 가져오기, 안전한 렌더링, 내보내기, 명시적 원문 갱신, 기획서 줄별 검토, 양식 다운로드, 390px 모바일 표시를 포함합니다. 일부 항목은 하나의 흐름으로 묶여 총14개입니다.

`desktop-preview.png`와 `mobile-preview.png`는 이 실제 렌더링 결과입니다. 모바일 화면의17개 예시는 테스트 중 추가한 데모 초안1개를 포함한 수치이며 배포본의 초기 예시는16개입니다. 사용자 데이터는 아닙니다.

## 최초 전달 당시 미검증 항목

1. 사용자 Docker Local의 파일 생성, Docker 이미지 빌드, 컨테이너 실행 및 접근.
2. 실제 회사 엑셀의 모든 양식·규모와 업무별 검색 정확도.
3. 실제 임베딩·채팅 모델 연결, 품질, 비용, 응답 시간.
4. SSO·사용자별 권한·부서별 자료 접근 격리·승인자별 감사. 현재는 로컬 공유 접속 키 방식입니다.
5. 자유형 기획서 전체 해석, 개발 소스코드의 실제 사용처 추적, 엑셀 등록 후 이전 초안의 자동 완료 처리.
6. 고부하, 다중 서버 배포, 장기 운영 및 전체 보안 감사.

## 재현 명령

```bash
pip install -r requirements-dev.txt
python -m pytest --junitxml=docs/test-results.xml --cov=catalog --cov=vendor.urstory_rag --cov-report=json:docs/coverage.json
node --check static/app.js
python scripts/verify_vendor.py
python scripts/smoke_test.py
```

브라우저 검사에는 Playwright와 Chromium이 필요합니다. 자동 설치는 하지 않습니다.

```bash
# 별도 임시 DB와 인프로세스 API를 사용하는 UI 검사
CM_BROWSER_OFFLINE=true CHROMIUM_PATH=/usr/bin/chromium python scripts/browser_test.py

# 직접 HTTP 방식: 운영 데이터가 없는 별도의 테스트 서버에만 실행하세요.
# 이 방식은 제공 환경에서 브라우저 정책상 실행하지 못했습니다.
CM_TEST_URL=http://127.0.0.1:8766 CM_TEST_TOKEN=테스트서버의키 CHROMIUM_PATH=/usr/bin/chromium python scripts/browser_test.py
```

기계 판독 결과는 `test-results.xml`, `coverage.json`, `browser-test-results.json`, `launcher-smoke-results.json`에 보관합니다.
