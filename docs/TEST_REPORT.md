# 통합 확장판 검증 보고서

최종 마감: 추가 속도 조정은 하지 않았습니다. 최종 후속 8문항은 자동 7/8·의미 검토 6/8입니다. 수치 정정 문장 차단과 일부 검색 후보를 전체 카탈로그로 단정하는 두 문제는 남아 있으며 [최신 보고서](CATALOG_SKILLS_2026-09-22.md)에 증거와 다음 작업을 기록했습니다.

2026-09-22 최신 검사: 확장/API 508개·설치 83개·대역 인증/모델 기반 native HTTP 10개 통과, JS 구문 검사 및 고정 upstream 384개 파일·모드 일치. 최종 실제 메타데이터 검색 5건은 정답 1위 5/5, 후보 집합 보존. 이는 합성 표본의 검색 결과이며 답변 의미 정확도나 회사 자료의 정확도 수치가 아닙니다. [최신 통합 평가](CATALOG_SKILLS_2026-09-22.md)와 [실제 검색 비교](verification/catalog-skills-2026-09-22/retrieval-challenge-upstream-comparison.json)를 우선합니다.

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

## 2026-09-22 카탈로그 리랭킹 범위 축소 및 무관 질의 후보 제거

실측에서 카탈로그 검색 한 번 14.5초 중 리랭킹이 14.3초였다(벡터+키워드 0.2초). 원인은 색인 청크의 전체 업무 필드(영문 문구·비고 포함)를 RRF 후보 30여 건 전부에 대해 크로스인코더로 채점하고, 그 동기 호출이 이벤트 루프를 막는 것이었다. `gateway.CatalogReranker`가 원본 리랭커를 감싸 RRF 상위 12건만 등록 문구·메뉴·노출 조건 텍스트로 채점하고 워커 스레드에서 실행한다. 결과는 기존과 같이 코드/리비전으로 DB 원문과 대조한다. 원본 소스는 변경하지 않았다.

또한 무관 질의(예: 날씨)가 retrieval_gate(top_score 0.65)를 통과해 후보 8건이 대화에 저장되던 문제를, 근거 검증을 통과한 설명이 코드를 하나도 인용하지 않으면 후보를 비우고 `no_relevant_candidate` trace를 남기는 방식으로 처리했다.

재빌드·재기동 후 실측(demo 279건, 로컬 E5 + Nori + bge-reranker-v2-m3-ko): 비캐시 검색 8건 2.1~3.1초(리랭킹 2.8초), 정답 1위 7건 동일 유지(AT-1923·EX-0101·EX-0201). 실제 대화 턴은 날씨 질의 16.7초·후보 0건, 30초 인증 질의 28.1초·AT-1923 원문 응답. 확장/API 검사 256개, 설치 unittest 72개 통과. 무관 질의 판정은 설명 모델의 인용에 의존하므로 모델 없는 키워드 모드에는 적용되지 않는다.

## 2026-09-22 인계 TODO 처리: 브라우저 검사 재실행 · 원본 테스트 DB 연결 · 대화 턴 지연 원인

브라우저 검사 3종을 이 Mac에서 재실행했다. 스크립트는 `CHROMIUM_PATH` → `/usr/bin/chromium` → Playwright 설치 Chromium 순으로 실행 파일을 찾도록 바꿨다. 이 Mac의 venv(Playwright 1.63)는 headless shell 1243을 요구하지만 캐시에는 1234만 있어, `CHROMIUM_PATH`로 `chromium-1234`의 Google Chrome for Testing을 지정해 실행했다. 결과는 오프라인 브리지 14개, loopback HTTP 14개, 세션 복원 10개 모두 통과이며 JavaScript 오류는 없다. 증거: `verification/browser-offline-results.json`, `verification/browser-results.json`, `verification/browser-session-results.json`(2026-09-22). 인증·모델·클립보드는 검사 대역이며 원본 JWT·Next·실제 모델 검증이 아니다.

`scripts/test_upstream.py`는 `--network none`이라 원본 conftest가 요구하는 PostgreSQL(localhost:5432)에 접속하지 못해 112개 에러 후 중단됐다. 이제 내부 전용 Docker 네트워크에 일회성 pgvector PostgreSQL(원본 conftest 기본 계정·`shared_test` DB, `upstream/infra/init-db.sql`로 vector 확장 생성)을 띄우고 `DATABASE_URL`로 연결한 뒤 실행이 끝나면 컨테이너와 네트워크를 삭제한다. 운영 볼륨은 사용하지 않으며 인터넷 접근도 없다. 실행 결과는 4분 5초에 611 통과·27 실패·5 건너뜀·7 제외(performance)이다. 실패 27개의 원인은 (1) 인증 API 11개: 가입 요청 429와 그에 따른 `access_token` 누락, (2) Redis·Elasticsearch·임베딩 서비스 부재 5개(ConnectError)와 외부 이름 해석 실패 2개, Redis 캐시 1개, (3) 패치로 달라진 응답 형식 8개(health 응답의 `openai` 항목 5개, Claude 응답 처리 2개, 설정 응답 검증 1개)로, DB 연결 실패는 남지 않았다. 원본 전체 384개 파일 계약 검증은 통과했다. 이 결과는 라이브 RAG 벤치마크가 아니다.

대화 턴 지연을 실제 API에서 3회 계측했다: 42.1초(Plan 3.5·설명 3.8·충실도 7.0·근거 32.8), 40.2초(Plan 4.8·설명 18.1·근거 3.5·충실도 14.9), 28.0초(Plan 3.2·설명 4.3·충실도 11.4·근거 18.7). 충실도·근거 판정은 이미 병렬이며 한 턴은 Plan + 설명 + max(충실도, 근거)로 구성된다. 컨테이너 안에서 같은 근거·답변으로 판정 호출만 반복한 결과 프롬프트는 약 1,000토큰, 응답은 55~86자인데 완료 토큰이 738~8,697개(거의 전부 reasoning 토큰)로 편차가 커 5.5초에서 41.2초까지 걸렸다. 출력 길이를 제한하는 지시를 추가해도 추론 토큰은 줄지 않았다. Command Code의 `reasoning_effort`는 `low|medium|high|xhigh|max`만 받고 `none`/`minimal`은 400으로 거부하며, `thinking: disabled`는 무시된다(3,613~6,204 추론 토큰). 따라서 현재 공급자·모델(DeepSeek V4.1 Flash, low)에서는 판정 지연을 파라미터로 줄일 수 없다. 남은 선택지는 판정 단계에 추론 없는 모델을 쓰는 것(공급자 확인 필요)이나 판정 자체를 유지한 채 지연을 감수하는 것이며, 검증을 약화하는 캐시·생략은 적용하지 않았다.

문서 정리: README의 `CODE_CATALOG_AUTHORITY` 기본값 설명을 compose·`.env`의 실제 기본값 `system`으로 맞췄고, `docs/STATUS.md`를 2026-09-22 기준으로 갱신했다. 확장/API 검사 256개, 설치 unittest 72개, native HTTP 10개 통과(대역 인증·모델). API 컨테이너의 `gateway.py`·`agent.py`·`safety.py`·`api.py` sha256이 작업 트리와 일치한다. production 목록은 0건이라 등록→색인→검색→초안→승인 종단간은 여전히 미수행이며, 합성 데이터를 production에 넣지 않는 원칙에 따라 실제 항목 제공 전에는 수행하지 않는다.

## 2026-09-22 판정 단계 모델 옵션과 후보 실측

인계 TODO의 "판정 단계 모델" 항목을 처리했다. 충실도·근거 판정 두 단계만 다른 모델로 바꾸는 `CODE_LLM_JUDGE_MODEL`과 `CODE_LLM_JUDGE_REASONING_EFFORT`(low·medium·high·none, none은 파라미터 생략) 환경 변수를 추가했다. 비어 있으면 기존과 같이 생성 모델이 판정한다. 판정 전송(`routing.JudgeLLM`)은 같은 공급자·키를 쓰고 temperature 0이며, 생성·HyDE·재작성·RAGAS 평가 모델은 바뀌지 않는다. 상태 API의 `llm.judge_model`과 트레이스 단계에 실제 판정 모델을 기록하고, 잘못된 값은 오류로 중단하며 원래 모델로 몰래 되돌아가지 않는다. compose.yaml은 `scripts/render_compose.py`로 재생성했다. 확장/API 검사 263개(신규 7개: 옵션 해석, 판정 단계 한정 적용, 실제 패치 전송의 model·reasoning_effort 본문, safety 단계 교체), 설치 unittest 72개, native HTTP 10개 통과. 이 코드는 아직 실행 중인 API 컨테이너에 반영하지 않았다.

후보 실측은 실행 중인 서비스를 건드리지 않도록 같은 이미지의 일회용 컨테이너에 작업 트리 코드를 읽기 전용으로 마운트해 실제 Command Code를 호출했다. 합성 답변·근거 1쌍을 원본 FaithfulnessChecker/HallucinationDetector와 StrictJudge 경로로 두 판정을 동시에 실행했다.

- 현재 모델 DeepSeek V4.1 Flash(low): 판정 한 턴 13~44초, 충실도 추론 토큰 2천~9.5천. `reasoning_effort`를 생략해도 17~24초로 같다. 이 합성 근거에서는 등록 원문 그대로인 답변도 충실도 판정이 3회 모두 차단했고, 틀린 답변(30초를 60초로 바꾸고 이메일 전송 문장을 추가)은 2회 모두 차단했다. 실제 API에서는 같은 문구가 통과한 기록(9/21·9/22)이 있으므로 합성 근거 형식의 차이로 판단하며, 아래 후보 비교는 같은 입력을 놓고 견준 상대 결과다.
- Command Code의 `claude-*` 모델은 `/provider/v1/messages` 전용이라 이 옵션(chat/completions)으로 쓸 수 없다. `gpt-5.4-mini`, `gemini-3.1/3.5-flash-lite`는 현재 요금제 밖(403 MODEL_NOT_IN_PLAN)이고 `MiniMax-M2.7`은 공급자 없음(400)이다.
- 요금제로 호출 가능한 13개 중 정답 3회 통과와 오답 3회 차단을 모두 만족한 모델은 네 개다. `inclusionai/ling-3.0-flash-sante:free`는 정답 3.7~5.8초·오답 3.9~5.2초·추론 300~700, `thinkingmachines/inkling-small`은 8.6~12초·4.0~4.5초·추론 700~2천, `z-ai/glm-5.3-flashx`는 7.2~9.5초·8.3~10.6초·추론 400~700, `poolside/laguna-s-2.1-free`는 2.8~6.7초·3.9~28.6초·추론 0이다.
- 제외 사유: `xiaomi/mimo-v2.6-flash`는 정답 1/3 차단과 오답 근거 판정 1회 형식 불량(502), `deepseek-v4-flash`와 `Step-3.7-Flash`는 정답 3/3 차단, `deepseek-v4-flash-fast`와 `GLM-5.2-Fast`는 정답 2/3 차단, `Qwen3.8-Flash`는 120초 초과 1회, `Kimi-K2.6`·`Qwen3.7-Flash`·`glm-5.3-flash`는 정확하나 15~55초.
- 한계: 답변 1종·근거 1쌍·3회 표본이라 위양성률 추정이 아니다. `:free` 모델의 데이터 정책과 속도 제한은 확인하지 않았다. 판정 모델 전환은 사용자 결정 사항이며 기본값은 바꾸지 않았다. 원시 결과는 `verification/judge-model-bench-2026-09-22.json`에 있다.

## 2026-09-22 Apple 온디바이스 판정 브리지 구현과 판정 모델 실제 턴 실측

사용자 요청으로 Siri가 쓰는 Apple Intelligence 온디바이스 모델을 판정 단계에 붙이는 경로를 구현했다. 구성은 세 부분이다. `extensions/apple_bridge/applefm.swift`는 FoundationModels 프레임워크로 모델을 호출하는 표준 입출력 워커이며 요청에 JSON Schema가 있으면 그 구조를 강제한다. `extensions/apple_bridge/bridge.py`는 127.0.0.1:8787에서 OpenAI 호환 `chat/completions`를 제공하고 공유 토큰을 요구하며, `apple/on-device` 외 모델명·스트리밍·`json_object`를 거절하고 토큰 사용량을 추정해 넣지 않는다. `extensions/code_agent/apple_judge.py`와 `routing.JudgeLLM`은 `CODE_LLM_JUDGE_PROVIDER=apple`일 때 충실도·근거 판정 두 단계만 브리지로 보내고 구조화 응답을 StrictJudge가 읽는 세 줄로 되돌려 쓰며, 브리지 불통은 503, 브리지 오류와 점수·판정 범위 이탈은 502로 중단하고 생성 모델로 되돌아가지 않는다. compose는 `extra_hosts`로 `host.docker.internal`을 등록하고 `manage.py start/stop/status/doctor`가 브리지 수명을 다룬다. 확장/API 검사 274개(신규 11개: 옵션 해석, 스키마 전송 본문, 세 줄 변환과 StrictJudge 연계, 형식 불량 6종 차단, 브리지 오류·불통 시 생성 모델 미대체, 판정만 전환되고 생성 전송 불변), 설치 unittest 77개(신규 5개: 브리지 HTTP 형식·토큰 401·모델 404·스트리밍 400·워커 오류 502), native HTTP 10개 통과. 이 Mac은 Apple M5·macOS 26.5.1·Xcode 26.6이며 `applefm --check`가 가용을 반환했고 브리지는 API 컨테이너에서 `host.docker.internal`로 도달했다. 재배포 뒤 API 컨테이너의 `provider.py`·`routing.py`·`apple_judge.py`·`safety.py`·`operations.py` sha256이 작업 트리와 일치했다.

판정 품질은 실제 파이프라인 형식(demo 목록 EX-0104·EX-0105·EX-0101 실제 행을 근거로 `CatalogSafety.validate` 호출, 변형 6종 × 3회)으로 쟀다. 온디바이스 모델은 등록 원문 그대로인 정답을 3/3 차단하고 두 코드를 나열한 정답도 3/3 차단했으며, 문서에 없는 문장을 덧붙인 답변은 3/3 통과시켰다. 메뉴 값 변경과 코드 번호 변경은 3/3 차단했고 60초 변형은 수치 검증이 먼저 차단했다. 근거 형식을 설명하는 시스템 지시를 붙인 추가 실험에서는 정답이 통과했지만 덧붙인 문장은 근거 판정 1.0으로 여전히 통과했고 충실도 판정은 스키마 디코딩 실패로 끝났다. 같은 입력에서 기존 DeepSeek V4.1 Flash(low) 판정은 정답 3/3 통과, 덧붙인 문장 3/3 차단, 메뉴·코드 변경 3/3 차단이었고 두 코드 정답만 3/3 차단했다. 실제 서비스에 Apple 판정을 반영해 같은 10문항을 돌린 결과는 200 응답 2건(3·9번, 정답 1위), 422 차단 7건, 502 1건(7번, 브리지 디코딩 실패)이었고 한 턴 15.4~39.5초였다. 따라서 이 옵션은 현재 판정보다 검증이 약하고 정답 대부분을 막으므로 기본값을 끈 채 선택 기능으로만 남긴다.

판정 모델 전환 실측은 같은 10문항(68문항 세트 1·2·5·7·27·67·3·9·12번과 무관 질의)으로 했다. 전환 전 DeepSeek 판정은 10건 모두 200, 차단 0건, 정답 순위 1위 8건·2위 1건(27번), 한 턴 12.4~31.9초(중앙값 18.2), 충실도 2.8~21.4초(중앙값 4.8), 근거 2.9~14.2초(중앙값 3.4), 판정 추론 토큰 217~4,519개였다. `z-ai/glm-5.3-flashx`(effort none)로 바꾼 뒤에는 200 응답 8건(정답 모두 1위), 502 2건(3·9번, 판정 응답 형식 불량), 한 턴 15.5~60.0초(중앙값 20.9), 충실도 7.2~32.4초(중앙값 10.0), 근거 5.3~49.1초(중앙값 7.2)로 오히려 길어졌고 추론 토큰도 264~2,667개로 줄지 않았다. 합성 근거 벤치에서 7~11초로 보였던 이점이 실제 파이프라인에서는 나타나지 않았고 형식 불량이 새로 생겼다. 같은 날 기준선의 판정 시간이 이전 계측(17~44초)보다 짧았으므로 Command Code 쪽 지연 편차가 큰 것으로 본다. 실측 뒤 `.env`의 판정 설정을 모두 비워 전환 전과 같은 상태(생성 모델이 판정)로 되돌리고 API·worker·beat를 재기동했으며 브리지는 내렸다. 재배포의 첫 `docker compose up --build --wait`는 모든 서비스가 정상이고 일회성 컨테이너가 0으로 종료했는데도 종료코드 1을 반환했다. 오류 문구는 없었고 같은 명령을 빌드 없이 다시 실행하면 0을 반환했으며 원인은 특정하지 못했다. 원시 결과와 스크립트는 `verification/judge-switch-2026-09-22/`에 있다. 표본은 문항 10건과 변형 6종 × 3회이며 위양성률 추정이 아니다.


## 2026-09-22 최종 범위: Apple 연결만 유지

사용자의 “그냥 연결만” 요청에 따라 Apple 전용 검색 관련성 필터, 상위 1건 입력 제한, 고정 답변 대체, 대화 프롬프트 재작성을 제거했다. 기존 검색·프롬프트·검증 흐름을 유지하고 대화 공급자와 답변 검증 공급자를 `apple/on-device`로 연결했다. multilingual-e5-base(768→1536 패딩), PGVector, Nori, RRF, 상위 12건 리랭킹은 변경하지 않았다.

API·worker·beat 재배포 완료. 컨테이너 내 연결 관련 파일 8개의 해시가 작업 트리와 일치한다. 배포된 `RoutingLLM`을 통한 실제 Apple 응답 “안녕하세요! 어떻게 도와드릴까요?”를 확인했다. 확장/API 검사 294개, 설치 unittest 77개, 대역 기반 native HTTP 10개 및 JS 구문 검사 통과. 이는 연결 검증이며 긴 카탈로그 프롬프트의 답변 품질·성공률 검증을 뜻하지 않는다. 이전 `apple-chat-*` 실험 결과는 최종 구현의 품질 수치로 사용하지 않는다. 관련 로그는 `docs/verification/judge-switch-2026-09-22/*connection-only*`에 있다. 커밋하지 않았다.


## 2026-09-22 Apple 전달 형식 오류 수정

실제 `30초인증관련 메시지찾아줘`를 후보 8건으로 재현할 때 `exceededContextWindowSize`(4089/4096)와 `decodingFailure`를 확인했다. 후보 4건도 decodingFailure가 발생해 후보 개수만의 문제는 아니었다. Apple 어댑터에서 중복 스키마 안내 제거, 모든 필드·값을 유지하는 동일 값 그룹 표기, 스키마 필드 순서 보존 및 참조 코드 enum을 적용했다. 검색·리랭커·판정 기준은 변경하지 않았다. 최초 판정 502의 원본 상세 예외는 보존되어 있지 않아 같은 원인이라고 단정하지 않는다.

동일한 8건 자료의 설명 생성→검증 3회 통과. Docker 반영 뒤 실제 브라우저에서 같은 질문의 자동 분류→검색→생성→검증→저장 완료(6.056초, 후보 8건). 수치·충실도·근거 검사 통과. 이 턴은 답변 원문 일치로 판정 모델 추론 없이 검증됐으며 모든 자유 서술 판정의 성공을 보장하는 결과가 아니다. pytest 295·unittest 77·native HTTP 10 통과(마지막은 대역 모델). 증거: `verification/apple-adapter-fix-2026-09-22/`. 추가 커밋 없음.


## 2026-09-22 일반 문서 검색 초기 인덱스 404 수정

문서·청크가 0건인 새 저장소에서 `rag_chunks`는 최초 업로드 때만 생성되어 일반 검색 테스트가 404를 반환했다. 시작 시 청크가 없는 경우 원본 Nori 매핑으로 빈 인덱스를 준비하도록 보완했다. 기존 청크가 있는데 인덱스가 사라진 경우에는 재색인 오류로 중단해 데이터 손실을 빈 검색으로 숨기지 않는다. 알림 샘플 인덱스와 데이터는 변경하지 않았다.

Docker 재배포·파일 해시 일치 확인. 실제 `/search`에서 기존 질문 `30초`, 하이브리드·HyDE·리랭킹 선택 그대로 재실행: 3.24초, 벡터/키워드/RRF 완료, 참조 문서 0건 및 관련 문서를 찾지 못했다는 정상 결과 표시. pytest 298·unittest 77 통과. 증거 로그: `verification/empty-document-search-2026-09-22/`.


## 2026-09-22 15:33 Apple 반복 요청 보완

`30초 관련메시지찾아줘`의 기존 대화 후속 요청에서 생성 단계 502가 보고됐다. 당시 상세 예외는 남지 않아 원인을 확정하지 않는다. 동일 문맥 재시도에서는 모델이 사용자에게 없는 proposed_message를 생성해 차단되는 별도 오류도 관찰했다. Apple 구조화 응답 호출만 temperature=0(greedy)으로 변경하고 일반 자유 생성 온도는 유지했다. Apple 대화/판정 API 오류는 허용된 원인 코드만 로그·화면에 표시하도록 추가해 원문·키 노출 없이 context/decoding/language/guardrail/rate-limit을 구분한다. 검증 생략·외부 모델 대체·검색 설정 변경은 없다.

Docker 실제 브라우저에서 같은 후속 질문 9.615초 완료, 후보 8건, 수치·충실도·근거 검사 통과. 같은 대화 상태에서 저장을 생략한 전체 Agent 경로 추가 3회도 모두 `본인인증을 30초 이내에 완료해주세요.`로 완료됐다. 이는 해당 재현 범위이며 최초 502의 원인 규명 또는 모든 요청의 성공 보장은 아니다. pytest 304 통과, 후속 temperature 검증 포함 초점 14 통과. 컨테이너 apple.py/apple_judge.py 해시 일치. 증거: `verification/apple-repeat-2026-09-22/`.


## 2026-09-22 검색 결과 보존 및 DeepSeek 복귀

검색 성공/AI 실패를 분리해 DB 원문 후보를 계속 보여주고, 수치 조건 전체 목록·버전 검사·20건 페이지를 추가했다. 사용자 질문을 등록된 사실의 검증 근거에서 제외하고, 명백한 새 검색의 의도 분류 및 이력의 UI 메타데이터 전송을 생략했다. pytest **311개**, unittest **77개**, 대역 native HTTP **10개**, JS 구문 통과. 원본 384개 파일·모드 일치, API·worker·beat 재배포 및 핵심 9개 파일 해시 일치.

Apple 실제 12문항×2회는 유효 답변 **2/24**, **22회 입력 초과**. HTTP 200은 오류를 명시하며 검색 결과를 보존한 것이므로 AI 성공률이 아니다. 사용자 지시로 Apple 추가 최적화를 중단하고 기존 DeepSeek로 변경했다. 실제 브라우저에서 DeepSeek 생성·판정·근거 재작성 완료(66.420초), 후보 25건, 수치 전체 목록 42/42건과 상세 열기를 확인했다. 회사 데이터는 검증하지 않았다. [상세 결과](APPLE_USABILITY_REVIEW_2026-09-22.md), 증거 `verification/apple-usability-2026-09-22/`.
