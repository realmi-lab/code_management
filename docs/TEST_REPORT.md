# 통합 확장판 검증 보고서

최신 오류 검사: [2026-09-21 버그 검사·수정 보고서](BUG_AUDIT_2026-09-21.md). 최종 확장 검사 183개, 설치/패치 검사 67개 통과. 주요 화면 16곳에서 JavaScript 오류·HTTP 5xx가 없었고, 외부 네트워크 없는 실제 문장 분할 검사도 통과했다. 외부 AI·임베딩 추론 검증은 제외했다.

## 2026-09-21 현재 검증

최신 설정/사용법은 [AI 설정 안내](AI_SETTINGS.md)를 따른다. 아래 결과는 검사별 실행 범위를 구분하며, 통과 개수를 완성률이나 검색 품질로 해석하지 않는다. 회사 자료를 사용하지 않았고 실제 목록 조회 당시 운영 문서와 카탈로그는 모두 0건이었다.

| 검사 | 결과와 범위 | 근거 |
|---|---|---|
| 고정 원본 검증 | 384개 파일·모드와 Git tree 일치 | `scripts/manage.py verify`, `upstream.lock.json` |
| 확장 도메인/API/연동 계약 | 142개 통과. 외부 AI/인증/검색의 대역 사용 범위는 테스트에 명시 | [pytest 로그](verification/completion-2026-09-21/integration-tests.log) |
| 설치 도구 | 59개 통과 | [unittest 로그](verification/completion-2026-09-21/installer-tests.log) |
| loopback HTTP | 실제 HTTP, 인증·AI는 대역 | [결과](verification/completion-2026-09-21/native-http-results.json) |
| 카탈로그 Chromium UI | 실제 HTTP/DOM, 인증·검색·LLM은 대역 | [결과](verification/completion-2026-09-21/browser-results.json) |
| AI 설정 Chromium UI | DeepSeek/Claude/OpenAI 저장·재조회 및 모바일 표시 통과. 외부 AI 호출 없음 | [결과](verification/completion-2026-09-21/browser-ai-settings.json) |
| 전체 Docker 서비스 | PostgreSQL/PGVector, ES/Nori, Redis, Langfuse, 원본 Next/API/작업자 기동 | 실제 현재 Mac Docker 환경; 이것만으로 전체 검색 품질은 입증하지 않음 |
| 원본 로그인·JWT·API 프록시 | 00:32:33 UTC 검사 통과. 문서·카탈로그 목록 0건 | [실제 서비스 검사](verification/completion-2026-09-21/native-stack-smoke.log) |
| 실제 무로그인 Next 브라우저 | 인증 헤더 없이 진입, 실제 AI 설정 조회, 키워드 모드 저장·재조회, 원래 검색 모드 복원 통과 | [브라우저 결과](verification/completion-2026-09-21/live-browser.json) |
| 실제 무로그인 HTTP | API·프록시·무자격증명 접속·원본 사용자 연결·문서/카탈로그 조회 6개 통과. 양쪽 목록 0건 | [HTTP 결과](verification/completion-2026-09-21/local-access-smoke.json) |
| 선택 라우터의 실제 LLM 호출 | Command Code → DeepSeek, 합성 요청과 토큰 사용량 확인 | [실제 호출 결과](verification/completion-2026-09-21/selected-provider-live.json) |
| 실제 로컬 E5 | 고정 모델, 외부 추론 없이 합성 문장 임베딩 및 기대 후보의 유사도 순위 확인 | [모델 결과](verification/completion-2026-09-21/local-embeddings-live.json) |

사용자 요청에 따라 기본 `CODE_AUTH_MODE=local`로 로그인·관리자 비밀번호 입력을 제거하고 실제 단일 로컬 관리자 신원을 공유하도록 변경했다. 선택형 JWT 모드는 유지한다. 변경 후 실제 Next 브라우저의 직접 진입과 AI 설정 저장·재조회, 실제 HTTP 6개 검사를 통과했다. 이 검사에서 회사 자료나 합성 카탈로그를 삽입하지 않았으며 전체 검색·초안·승인 종단간 검증으로 확대 해석하지 않는다.

직접 DeepSeek API, Anthropic Claude API, OpenAI API의 실제 키 호출은 미검증이다. 로컬 E5 결과는 실제 모델 계산 증거이며 전체 PGVector/Nori 검색, 카탈로그 비교·초안·승인 흐름이나 회사 자료의 정답 검색률을 입증하지 않는다. 원본 전체 테스트, RAGAS 평가, 장기 부하, 백업/복원과 전체 보안 감사도 완료한 것으로 표시하지 않는다.

루트 [GitHub Actions workflow](../.github/workflows/verify.yml)는 고정 원본 검증, 설치/확장 테스트, Python/JS 구문, 합성 HTTP/브라우저 검사를 자동화한다. 외부 AI 키를 요구하거나 배포하지 않는다. 수동 실행에서는 전체 원본 프론트엔드 Docker 빌드를 추가로 선택할 수 있다. **workflow 파일을 추가한 상태이며 GitHub 원격 실행 결과는 아직 없다.**

## 2026-09-21 AI 선택 항목 null 처리 수정

실제 Command Code의 `deepseek/deepseek-v4.1-flash`에 합성 요청 `로그인 실패 알림 찾아줘`를 보냈을 때 Plan의 `proposed_message`, `menu`, `trigger`가 JSON `null`로 반환되어 문자열 검증이 실패하는 문제를 재현했다. AI 출력 모델의 선택 문자열에만 `null` → 빈 문자열 처리를 추가하고, 출력 JSON Schema를 시스템 프롬프트에 포함했다. 필수 문구·잘못된 action·추가 필드·사용자 입력의 타입 검사는 유지한다.

수정 후 실제 컨테이너의 UrstoryGateway와 안전성 전처리를 거친 동일 합성 요청이 Plan 검증을 통과했다. 운영 목록·대화·초안은 작성하지 않았다. 확장 테스트 **158개**, 설치 테스트 **59개**, 실제 읽기 전용 HTTP **6개**, JavaScript 구문 검사가 통과했다. 이 실제 모델 검사는 요청 분류 단계에 한정하며 전체 검색·초안·승인 종단간 성공을 의미하지 않는다.

## 2026-09-21 기능 연결 정리 (외부 AI 호출 제외)

설정 저장/캐시에는 원래 선택값을 유지하고 실제 요청의 복사본에만 키워드 실행 제약을 적용했다. local/OpenAI 선택 시 검색 모드를 hybrid로 강제하던 처리를 제거했다. 원본 설정 화면은 임베딩 연결 전에도 향후 옵션을 저장할 수 있고, 누락된 청킹 선택지와 빈 Select 이벤트 처리도 보완했다. 감시 경로 입력 전달을 연결하고, 누락된 평가 지표는 미측정으로 표시한다. 원본 감시 작업자의 미구현 부분과 백업 배포 설정 한계는 [기능 비교](FUNCTIONAL_PARITY.md)에 명시했다.

확장 테스트 **172개**, 설치/패치 테스트 **65개**, 원본 파일/모드 **384개** 일치 검사가 통과했다. 전체 백엔드 및 Next 프론트엔드 Docker 빌드도 통과했다. 합성 인증/모델을 사용하는 localhost HTTP 검사 **10개**, 오프라인 TestClient 브리지 브라우저 검사 **14개**가 통과했다. 해당 검사는 외부 AI·임베딩·운영 자료의 종단간 검증이 아니다. 증거 폴더: `verification/functional-parity-2026-09-21/`.

실제 빌드된 Next 화면에서도 설정 보관·HyDE/청킹 안내·감시 경로 전달·미측정/실제 0 구분 **4개 항목**을 통과했다. 저장/감시 시작/평가 데이터 및 외부 공급자 상태 조회는 브라우저 대역으로 처리하여 운영 자료와 공급자를 호출하지 않았다. [검사 결과](verification/functional-parity-2026-09-21/functional-ui.json), [평가 화면](verification/functional-parity-2026-09-21/evaluation-unmeasured.png).

## 2026-09-18 전달 당시 기록

아래 본문은 당시 작성 환경의 기록이며 현재 Docker/모델 기동 상태를 설명하지 않는다. 초기 로컬 빌드와 Command Code 도입 기록은 [이전 로컬 검증 보고서](LOCAL_VERIFICATION_2026-09-21.md)에 보존한다.

실행 기준일: 2026-09-18. 작업 폴더: 별도 작업환경의 `/mnt/data/final_work/code_management`.

회사 데이터, 실제 모델 키, 운영 DB는 사용하지 않았다. 사용자 맥/Docker Local을 변경하지 않았다. 이 보고서는 **실제 작성된 확장 코드의 로컬 검사**이며 전체 보안 감사·운영 승인 또는 전체 원본 라이브 검증이 아니다.

## 1. 실제 결과

| 검사 | 결과 | 실행 범위/증거 |
|---|---|---|
| 통합 도메인·API·원본 어댑터 계약·빌드 패치 | **84개 통과** | `verification/integration-tests.log`, `integration-junit.xml` |
| 설치 도구/회귀 | **58개 통과** | `verification/installer-tests.log` |
| 실제 localhost HTTP | **10개 통과** | `verification/native-http-results.json`, `native-http.log` |
| 실제 Chromium UI 조작 | **14개 통과**, JS 오류 **0개** | `verification/browser-offline-results.json`, `browser-offline-run.log` |
| TSX 구문 변환 | 통과 | `verification/tsx-syntax.json`. 전체 TypeScript 타입 검사/Next 빌드는 아님 |
| Python·JS·셸 구문 | 통과 | compileall, node --check, bash -n |
| 실제 브라우저의 localhost 이동 | **환경 정책으로 차단** | `verification/browser-results.json`, `browser-run.log` |
| Docker/전체 원본/실제 키 사전검사 | **미충족** | `verification/environment-check.json` |

테스트 개수를 합산해 품질 점수나 완성률로 표시하지 않는다. 같은 업무 흐름을 여러 층에서 검사하므로 독립적인 기능 수가 아니다.

## 2. 실제 코드가 실행된 부분

SQLAlchemy 저장소/SQLite, 파서, 버전 검사, 원문 보존, 대화 상태, API 라우터, 프론트 JavaScript, 실제 DOM·클릭·입력·파일 선택은 전달 소스를 실행했다. 코드번호 직접 조회는 모델 없이 실행한다.

대화는 검색→두 번째 후보 비교→신규 초안→관리자 명시적 승인→코드 목록 반영→감사 기록→대화 복원을 검사했다. 다른 사용자 대화 접근 차단, 요청 ID 재전송, stale version, 사용자 승인 권한 차단, 없는 코드 생성 차단, AI가 만든 숫자/비교 문구 거절, 파일 충돌·기존 원문 유지, 수식/손상 XLSX 거절 등을 포함한다.

실제 사용자 회사 파일이 아니라 합성 CSV와 기존 빈 XLSX 양식을 사용했다. 새 코드나 데모 자료를 production 초기 목록에 삽입하는 코드는 없다.

## 3. 대역과 환경 제한

- 도메인/API 테스트는 SQLite에 실제 저장 로직을 실행한다. PostgreSQL의 행 잠금/advisory lock 동작을 SQLite 결과로 증명하지 않는다.
- `ScriptedGateway`는 외부 LLM과 검색 결과만 대신한다. 실제 한국어 검색 품질이나 모델 추론을 테스트한 것이 아니다.
- 원본 어댑터 계약 테스트는 원본 클래스 이름·호출 인수·상속 엔진의 스냅샷 필터·최신 DB 원문 대조·자원 정리를 검사한다. 이때 외부 원본 엔진은 대역이며 실제 Nori/리랭커를 실행하지 않는다.
- 빌드 패치 테스트는 고정 소스의 필요한 문자열/메서드를 담은 최소 계약 fixture를 사용한다. 원본 전체 파일을 다운로드하거나 원본 전체 테스트를 통과한 것이 아니다.
- FastAPI 인증 의존성은 합성 사용자로 대체한다. production 코드가 실제 원본 get_current_user를 호출하는 것은 코드/구성으로 확인했지만 실제 JWT/Redis 로그인 종단 간 검증은 미수행이다.

Chromium에서 실제 localhost HTTP 이동을 시도했으나 `ERR_BLOCKED_BY_ADMINISTRATOR`로 차단되었다. 정책을 끄거나 변경하지 않았다. 별도 오프라인 검사에서는 프로젝트 HTML/CSS/JS를 Chromium에 직접 로드하고 `fetch`를 실제 FastAPI TestClient에 연결했다. postMessage의 부모 로그인과 클립보드는 검사 대역이다. 따라서 실제 origin 보안/CSP/클립보드 권한/Next 프록시 검증으로 해석하면 안 된다.

별도의 httpx 검사에서는 실제 Uvicorn 서버와 loopback HTTP로 401·인증된 조회·정적 HTML·대화·승인·감사를 확인했다. 이 검사도 원본 JWT와 외부 검색 모델은 대역이며 브라우저 HTTP 제한을 우회하는 것이 아니다.

## 4. UI에서 확인한 14개 항목

작업실 표시와 검사 신원 연결, 정확한 원문 조회, 기획서 복사 payload, 대화 검색, 순번 후보 및 조건 비교, 미등록 초안, 관리자 등록, 목록 반영, 파일 선택/미리보기/확정, 업로드 HTML 문자열의 비실행 출력, 승인 감사, 대화 복원과 현재 등록 상태, 390px 모바일 가로 넘침 없음, JS 오류 없음.

`integrated-desktop.png`, `integrated-mobile.png`는 **새 통합 작업실 코드의 실제 Chromium 렌더링**이며 합성 데이터 화면이다. 원본 Next 관리자 셸 전체가 기동된 스크린샷은 아니다. 이전 경량판 이미지를 재사용하지 않았다.

## 5. 작업 중 찾아 수정한 문제

1. `인증 3번 실패`의 횟수를 후보 순번으로 오해하던 해석을 수정했다.
2. 후보 설명 후 원래 검색 순서를 잃어 `그럼 3번째는?`을 처리하지 못하던 상태 보존을 수정했다.
3. 승인한 초안을 대화 복원 시 다시 미등록으로 표시하던 문제를 DB 현재 상태 조회로 수정했다.
4. planner가 사용자가 작성하지 않은 비교 문구를 만들어 진행하는 것을 차단했다. 직접 인용한 초안은 원문을 보존한다.
5. 브라우저의 randomUUID 부재에 대해 crypto.getRandomValues 기반 UUID 생성을 추가했다. 안전하지 않은 Math.random으로 대체하지 않는다.
6. 잘못된 JSON/빈 모델 응답과 외부 서비스 실패를 자료 미저장 오류로 처리하고 내부 provider 오류 문자열을 그대로 노출하지 않게 했다.
7. 설정 변화 중 검색의 모델 설정을 한 snapshot으로 사용하도록 정리했다.
8. 기존 설치 감사의 .env/실행값 차이, 비밀번호 검증, Redis 예약문자, 오래된 성공 보고서, 같은 숫자 포트 문제를 수정했다.
9. 원본 평가 워커의 내부 API 주소·요청자 인증·HTTP 실패 처리·실제 설정 snapshot, 검색 캐시 구분, 시작 LLM 모델, 문서 ES 삭제에 대한 빌드 패치를 추가했다.

이 목록은 전체 결함 목록이 아니며 원본 자체의 모든 알려진 문제를 고쳤다는 뜻이 아니다.

## 6. 아직 실행하지 못한 것

공식 전체 소스 확보/전체 tree 검증, Docker 이미지 빌드, 실제 PostgreSQL·Alembic·PGVector·Nori·Redis·Celery·Langfuse의 동시 기동, 전체 원본 Next 빌드/원본 JWT 프록시/브라우저 HTTP, 실제 LLM·임베딩·리랭커·RAGAS·추적, 회사 엑셀 양식 적합성/정답 검색 품질, PostgreSQL 동시 부하·장기 인덱스 정리·백업/복원·전체 보안 감사.

## 7. 재현

```bash
python3 -m unittest discover -s tests -v
PYTHONPATH=extensions python -m pytest integration_tests -q --junitxml=docs/verification/integration-junit.xml
PYTHONPATH=extensions python integration_tests/native_http_check.py
PYTHONPATH=extensions python integration_tests/browser_offline_check.py
node --check extensions/code_agent/static/app.js
python3 -m compileall -q extensions/code_agent scripts deploy/patch_backend.py
```

실제 배포 후에는 `python3 scripts/smoke.py`로 원본 로그인 ID와 카탈로그 ID의 일치, 원본 문서·카탈로그 조회, 프론트 API 프록시를 확인한다. 실제 회사 테스트 엑셀을 올려 인덱싱 완료 후 `/codes`에서 질문/비교/초안/승인을 수행한다. 이 절차를 이번 환경에서 실행한 것으로 표시하지 않는다.

## 8. 합성 XLSX 200건 추가 검증

`examples/sample_code_catalog_200.xlsx`를 실제 코드 카탈로그 파서와 FastAPI 가져오기 API에 넣었다. 결과는 **200건 파싱, 오류 0, 경고 0, 신규 200건, 커밋 200건**이다. 사용중 190건과 폐기 10건이 구분되며 코드 원문과 원본 셀 위치를 보존한다.

`integration_tests/sample_200_e2e.py`에서는 실제 Store/Importer/Agent/Approval 코드를 사용해 다음 흐름을 실행했다.

- `이미 가입된 휴대폰 번호` → `AT-2011`을 최상위 관련 후보로 확인
- 작성 문구와 `AT-2011` 비교
- `30초 이후`와 `30초 이내` 조건 차이 감지
- `48시간 출금 제한` 신규 문구 생성 → 기존 24시간 제한 `AT-2127` 유사 후보 확인
- 관리자 확인 후 테스트 코드 `AT-2301` 정식 등록 → 최종 201건 확인

전체 샘플 시나리오는 약 0.1초 수준으로 완료되었지만 SQLite 로컬 테스트 시간이며 운영 성능 기준이 아니다. 외부 검색·LLM은 결정론적 테스트 대역이다. FastAPI 실제 업로드 경로는 `integration_tests/test_sample_200.py`로 별도 검증했다. 증거는 `docs/verification/sample-200-e2e.json`, `sample-200-e2e.log`, `integration-tests-with-sample200.log`에 있다.

## 2026-09-21 GitHub 메뉴·샘플 복원

전체 코드의 표·검색·상태 필터·상세·복사·CSV 내보내기, 문구 비교, 기획서 줄별 검토, 변경 기록 표와 전후 펼치기를 현재 확장에 연결했다. GitHub 고정 커밋 `f739e89aec0e8341697394857f005713ef2af5a1`의 `catalog/demo.py`에서 16건을 Git blob 검증 후 AST 리터럴로 추출했다. 다운로드 Python은 실행하지 않았다. 샘플은 SHA-256 검증한 별도 읽기 전용 자료이며 실제 목록에 삽입하지 않았다.

- 확장 도메인/API/계약 검사: **192개 통과**. 인증·외부 AI/검색은 테스트 대역 범위를 유지한다.
- 설치/패치 unittest: **67개 통과**. Python·JavaScript 구문, 고정 원본 384개 파일/모드 검증 통과.
- 전체 백엔드 및 Next 프론트엔드 Docker 빌드 통과. TSX는 전체 Next 빌드에서 검사했다.
- 합성 인증·LLM의 실제 loopback HTTP 및 Chromium 브라우저 흐름 통과. 추가 메뉴·샘플 분리·변경 기록 전후 표시를 포함한다.
- 실행 중인 `http://localhost:3500/codes`의 실제 Next/API로 **9개 항목 통과**. 목록 검색·샘플 16건·상세·실제 클립보드·CSV 다운로드·폐기 필터/복사 차단·조건 비교·기획서 검토·변경 기록 조회·390px 모바일을 확인했다. 브라우저/API 대역이나 외부 AI 호출 없이 실행했다. 실제 운영 카탈로그는 검사 전후 0건/버전 0으로 같았다. 운영 변경 기록도 0건이며 실제 변경 전후 내용은 격리된 합성 테스트로 검증했다.

의미 검색 실패가 규칙 비교로 대체되지 않는 API 검사는 통과했다. 이번 기능 검사는 실제 외부 AI·Nori/PGVector를 통한 비어 있지 않은 운영 카탈로그의 의미 검색 품질 검사로 표현하지 않는다. 근거: `verification/catalog-restore-2026-09-21/`.

## 2026-09-21 파일 가져오기 화면 제거 · JSON 샘플 300건

엑셀/CSV 가져오기 탭·버튼·파일 입력·드래그 영역과 관련 UI 이벤트를 제거했다. 전체 코드는 기본으로 별도 JSON 샘플을 표시하며 JSON 내보내기를 제공한다. 기존 GitHub 예시 16건과 새 합성 284건으로 총 300건, 사용 중 279건/폐기 21건이다. 모든 항목은 synthetic으로 표시하고 실제 목록에 삽입하지 않는다.

확장/API **193개**, 설치 unittest **67개**, Python·JS 구문 및 고정 원본 384개 파일·모드 검증을 통과했다. 전체 백엔드·Next 프론트엔드 Docker 빌드와 실제 loopback HTTP **10개**, 합성 인증·AI를 사용하는 Chromium 검사 **14개**, 오프라인 브리지 검사 **14개**를 통과했다.

실제 설치된 Next/API의 브라우저 검사 **11개**를 통과했다. 파일 가져오기 입력 제거, 샘플 300건, 상세·복사, JSON 다운로드의 항목 수·중복 없음·합성 표시, 페이지 이동, 폐기 상태, 문구 비교, 기획서 검토, 변경 기록 조회, 모바일 표시를 확인했다. 실제 목록은 검사 전후 0건/버전 0이며 변경하지 않았다. 외부 AI 호출·의미 검색 품질을 검증한 것으로 표현하지 않는다. 현재 사용자의 인앱 브라우저를 새로고침해 가져오기 탭 없이 `1–30 / 총 300개`와 `JSON 내보내기`가 표시되는 것도 직접 확인했다.

증거: `verification/json-samples-300-2026-09-21/`. JSON 구조와 재생성 방법은 [JSON 샘플 안내](JSON_SAMPLES.md)를 참고한다.

## 2026-09-21 샘플 대화 연결 · DeepSeek Flash low 실측

샘플 대화와 검색을 demo 스코프로 연결했다. 별도 대화 소유권/스코프 및 샘플 상태 테이블, Elasticsearch 샘플 인덱스, 공개 스냅샷을 사용한다. 실제 목록에 샘플을 삽입하지 않으며 샘플 정식 등록/초안 생성은 차단한다. 사용 중인 279건의 실제 Nori 키워드 인덱스를 구축했다. embedding=none이므로 PGVector 의미 검색 검증으로 표현하지 않는다.

확장/API 검사 **199개**, 설치 unittest **68개** 통과. 전체 Next 및 백엔드 Docker 빌드 통과. loopback HTTP **10개**, 합성 인증/AI 브라우저 **14개** 검사는 실제 모델 검사와 구분한다. 원본 384개 파일 계약을 보존했다.

실행 서비스를 `deepseek/deepseek-v4.1-flash`, `reasoning_effort=low`로 재기동했다. 실제 인앱 브라우저에서 “인증 전에 30초 기다리라는 알림 있어?”를 질문하여 HTTP 200 및 AT-1923 첫 후보와 원문 “메뉴확인 30초 이후에 인증해주세요.” 표시를 확인했다. 샘플 출처도 표시된다. 기존 30초 Next 프록시 중단은 300초 제한 패치로 수정했다. 두 독립 답변 검증은 병렬 수행하되 둘 다 통과해야 한다.

이번 단일 실제 호출은 **66.851초**였다. 계획 5.374초, 설명 11.898초, 사실 충실도 검증 28.334초, 근거 검증 45.765초(두 검증 병렬)이다. low 적용 후에도 모델 검증이 주요 지연이며 즉시 응답을 달성했다고 주장하지 않는다. 이전 high 호출 85.076초와는 프롬프트/병렬화/캐시 조건도 달라 추론 강도만의 성능 개선으로 해석하지 않는다. 증거: `verification/sample-chat-2026-09-21/low-live-metrics.log` 및 관련 검사 로그.

## 2026-09-21 업무 DB 컬럼 및 하이브리드 검색 적용

사용자 요청의 업무구분·타입·메시지코드·용도·title·맞춤법검사·영문 title·영문 contents·비고·추가날짜를 실제 cm_codes 컬럼에 적용했다. 기존 원문·코드·이력과 호환 API를 유지하는 추가형 마이그레이션이다. JSON 300건은 schema_version 2 구조로 재생성했고 원문은 title에 유지했다. 맞춤법검사는 미검사이며 영문 문구는 합성 번역 예시다. 기존 자료의 알려지지 않은 추가날짜는 추정하지 않는다.

확장/API **202개**, 설치 unittest **68개**, 실제 loopback HTTP **10개** 통과. HTTP 검사 인증·AI는 대역이며 별도 실제 실행 증거와 구분한다. Python/JS 구문, 원본 384개 파일 계약, 백엔드 Docker 빌드, 실제 PostgreSQL 마이그레이션을 통과했다. Next/TSX는 이번 변경이 없어 재빌드하지 않았다. 실제 인앱 브라우저에서 10개 업무 헤더, 300건 목록, 상세 필드, 영문 구절 검색 결과 AT-1923을 확인했다.

로컬 multilingual-e5-base를 활성화하고 샘플 버전 2를 재색인했다. 현재 공개 스냅샷 PostgreSQL 벡터 **279개**, Elasticsearch 문서 **279개**, 양쪽 UUID 집합 일치, 10개 업무 필드 검색 텍스트 포함을 확인했다. 실제 목록은 0건으로 유지한다. 폐기 샘플 21건은 목록에만 남고 활성 검색에서 제외한다. 앞선 실제 자연어 호출에서도 벡터 검색 20건·키워드 검색 20건·RRF 결합·리랭킹·DeepSeek 답변을 통과했다. 증거는 `verification/business-schema-2026-09-21/` 및 `verification/hybrid-samples-2026-09-21/live-turn.json`에 있다.

새 업무 구조 적용 후 실제 질문 재검증도 통과했다. AT-1923을 첫 후보로 반환했고 vector_search 20건, keyword_search 20건, RRF 결합 33건, 리랭킹 8건 및 외부 모델 검증을 거쳐 HTTP 200으로 응답했다. 단일 호출은 62.516초로 지연 개선 완료를 의미하지 않는다. 근거: `verification/business-schema-2026-09-21/live-hybrid-turn.json`.

## 검증 판정 진단 로그

`catalog_validation` 이벤트에 thread_id/request_id, 검증 종류, 점수, 임계값, 모델 판정, 통과/차단 여부, 사유(distortions/ungrounded_claims)를 기록한다. 파싱 실패와 호출 실패는 원문 대신 상태/예외 타입을 기록한다. 사유는 길이를 제한하고 PII 및 설정된 자격 증명을 마스킹하며 전체 프롬프트/답변/카탈로그를 로깅하지 않는다. 원래 차단 기준은 유지했다. 안전성·운영 검사 14개 통과, 백엔드 빌드 및 API/워커 재기동 완료. 설치된 컨테이너에서 합성 FAIL 응답으로 진단 로그 생성·422 유지 확인. 과거 실패의 미저장 사유를 복구한 것은 아니다.

## 2026-09-21 JSON 정본을 PostgreSQL로 이전 및 관리 화면 연결

검증한 300건을 별도 `cm_sample_codes` 테이블로 최초 1회 이전했다. `cm_sample_bootstrap` 기록과 트랜잭션 잠금으로 재시작 시 중복 삽입/덮어쓰기를 방지한다. JSON을 읽지 못하도록 검사 함수에서 차단해도 DB 초기화 재실행·300건 조회가 성공했다. 실제 목록 `cm_codes`는 0건으로 유지한다.

확장/API **206개**, 설치 unittest **69개**, loopback HTTP **10개** 검사 통과. 테스트 대역과 실서버 결과는 구분한다. 원본 384개 파일 계약 유지 및 전체 backend/Next TypeScript Docker 빌드 통과. 문서 관리의 실제 브라우저에서 DB 검색 EX-0101·상세 10개 필드를 확인했다. 검색 테스트 실제 브라우저에서 “인증번호 전송 성공” → EX-0101 첫 결과, 벡터 20건·키워드 20건·RRF 35건·리랭킹 8건을 확인했다. 일반 문서 업로드·목록·검색은 그대로 보존했다. DB 샘플과 실제 목록의 게이트웨이 및 대화는 분리하고 공통 검색·리랭킹 설정을 적용한다. 증거: `verification/db-catalog-2026-09-21/`.

## 검색 화면 상태 유지

검색어·결과·옵션·선택 상세를 사용자별 sessionStorage에 저장했다. 설치/패치 검사 70개 및 전체 Next/TypeScript Docker 빌드 통과, 프론트 서비스 반영 완료. 실제 인앱 브라우저에서 알림 DB 검색 후 설정으로 이동했다 돌아와 검색어·8건 결과·검색 단계·EX-0101 상세가 복원됨을 확인했다. 일반 문서 입력과 HyDE 선택도 유지된다. 같은 탭 새로고침 후에도 검색 결과와 상세 복원을 확인했다. 증거: `verification/search-persistence-2026-09-21/`.

## 모니터링 트레이스 표시 수정

실제 Langfuse 응답과 화면 타입의 불일치를 수정했다. 목록·상세 API 정규화와 날짜/시간 누락값 표시를 적용하고 알 수 없는 상태를 오류로 단정하지 않는다. 변환 테스트 4개, 설치/계약 unittest 72개, 전체 backend/Next TypeScript 빌드 및 원본 384개 파일 검증 통과. 서비스 반영 후 실제 API 37건의 날짜·소요시간 유효 확인, 성공 20/실패 5/미확인 12건 확인. 실제 인앱 브라우저 목록에 Invalid Date/NaN 없이 한국어 시각과 초 단위 시간이 표시됨을 확인했다. 상세에서도 인증번호 전송 성공·25.99s와 리랭킹/HyDE 등 실제 스팬 시간을 확인했다. 근거: `verification/monitoring-fix-2026-09-21/`.

## 모니터링 추가 점검 및 검색 중 화면 왕복 수정

수치 검증 후속 점검(2026-09-21): 사용자 질문 ‘인증 전에 30초 기다리라는 알림 있어?’의 과거 요청은 502로 실패했고, 당시 생성 답변/차단 수치는 저장되지 않아 구체적인 오탐 원인은 복구할 수 없다. 같은 질문의 실제 재실행은 AT-1923 원문과 함께 수치·충실도·근거 검증을 통과했다. 이를 특정 정규식 오탐 수정으로 주장하지 않는다. 수치 검증에 request/thread 식별자, 누락 수치·단위 및 마스킹한 차단 표현 로그를 추가했다. 설명 생성에서만 수치 검증 실패 시 동일 근거로 한 번 재작성하고 모든 검증을 다시 수행한다. 두 번째 실패는 저장하지 않으며 초안과 다른 검증 실패는 자동 재시도하지 않는다. 생성 프롬프트에서도 불필요한 후보 개수·순번 및 추정 수치를 금지했다.

확장/API 214개, 설치/패치 72개, 백엔드 빌드 및 고정 원본 384개 파일 계약 검증 통과. 30초 통과, 근거 없는 60초 차단, 동일 근거 재작성, 재실패 차단은 외부 모델 대역으로 검증했다. API/worker/beat에 반영했다. 검사·빌드 증거: `verification/numeric-grounding-2026-09-21/`.

Langfuse 최대 limit=100을 위반하던 통계 조회(limit=1000)를 수정했다. 한국 시간 오늘 범위의 페이지를 조회해 트레이스 수와 유효한 소요시간 평균을 계산한다. 목록 API의 page/size를 제공자 조회에 적용하고 전체 건수 및 이전/다음 버튼을 연결했다. 검색 중 화면을 왕복한 뒤 완료 결과가 현재 화면에 반영되지 않던 문제는 사용자별 상태 변경 이벤트로 수정했다. 검색 진행 상태도 왕복 후 유지하며 새로고침에서는 이전 요청의 대기 표시가 남지 않도록 문서 timeOrigin을 사용한다.

확장/API **211개**, 설치/패치 **72개** 통과. 테스트의 외부 서비스 대역은 실제 통합 검증과 구분한다. 전체 backend/Next TypeScript 빌드 및 최종 검색 진행 상태 변경 후 프론트 재빌드 통과, 실행 서비스에 반영했다. 원본 384개 파일 계약을 유지했다.

실제 API에서 점검 시점 오늘 37건·평균 29,826.62ms, 페이지별 10건과 페이지 간 ID 비중복을 확인했다. 새 테스트 요청으로 총 건수는 증가할 수 있다. 실제 인앱 브라우저에서 트레이스 2페이지와 마지막 페이지 다음 버튼 비활성화를 확인했다. 알림 검색 실행 → 설정 → 검색 테스트 왕복 후 ‘검색 중…’ 버튼 비활성화가 유지되고, 완료 후 버튼 활성화 및 EX-0101 결과가 자동 반영됨을 확인했다. 실제 합성 샘플 DB 검색이며 운영 목록은 수정하지 않았다. 증거: `verification/bug-audit-2026-09-21/`의 검사·빌드 로그.

수치 검증 보완 배포 후 실제 인앱 브라우저에서도 동일 질문에 AT-1923 및 등록 원문 “메뉴확인 30초 이후에 인증해주세요.”가 오류 없이 표시됨을 확인했다. 실제 모델의 수치·충실도·근거 검증 모두 통과했다. 자동 재작성 분기는 이번 실제 성공 호출에서 발생하지 않았으며 위 대역 회귀 검사로 검증했다. native HTTP 검사도 통과(합성 인증/모델 대역).

## 알림 검색 의도와 설명 검증 보완 (2026-09-21)

기존 문구 조회를 초안 작성으로 분류하는 오류를 막고, 설명 프롬프트에서 자료 부재/UI 동작 추측을 제거했다. 설명의 형식·수치·근거 실패에는 같은 자료로 최대 한 번 재생성하며 기존 검증 기준을 모두 유지한다. 같은 거절 답변은 재채점하지 않는다. 검증 모델 오류·입력/개인정보 차단과 초안에는 이 재생성을 적용하지 않는다.

확장/API 251개, 설치 72개, 대역 인증/모델을 사용하는 native HTTP 10개, Python/JS 및 TS/TSX 6개 파일 구문, upstream 384개 파일 계약 검증 통과. 실제 API 반영 파일 해시 일치 확인. 실제 브라우저에서 EX-0201 원문과 줄바꿈 확인.

최종 실제 모델 검사는 기존 실패 5문항 × 2회로, 응답 10/10 성공·정답 10/10 첫 번째·GOOD 10/10·평균 98.6점이었다. 별도 채점 호출 한 번 실패해 저장된 답변을 변경하지 않고 재채점한 결과를 별도 기록했다. 실제 검색 8회는 PGVector/Nori/RRF/리랭커, 나머지 2회는 검색 캐시를 사용했다. 전체 68문항 재평가나 회사 데이터 검증은 아니다. 생성과 채점 모델은 동일하다. 첫 수정본의 형식 오류 2회와 원래 68문항 기록을 보존했다. 상세: [최종 수정 검증](verification/catalog-quality-fix-final-2026-09-21/README.md).
