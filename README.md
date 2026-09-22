# Code Management — UrstoryRAG 통합 알림 코드 에이전트

`AT-1923` 같은 알림 식별코드와 등록 문구를 찾고, 비교하고, 새 초안을 작성하는 **서비스 기획자용 작업실**입니다. 소스코드 분석 도구가 아닙니다.

2026-09-22 최신: 대화·검증은 기존 DeepSeek를 유지합니다. 원본 UrstoryRAG의 PGVector·Nori·RRF·리랭킹 흐름에 맞춰 검색된 청크를 그대로 평가하고, 별도 12건 제한·필드 재조립·창별 점수 집계를 제거했습니다. 합성 메타데이터 검색 5건은 모두 정답 1위였고 후보 집합은 동일했습니다. 전체 답변 검증과 한계는 [최신 보고서](docs/CATALOG_SKILLS_2026-09-22.md), Apple 중단 근거는 [이전 실측](docs/APPLE_USABILITY_REVIEW_2026-09-22.md)을 확인하세요.

**사용자 확정: `UrstoryRAG / 관리자 콘솔에 로그인하세요` 화면·메뉴·진입 링크는 절대 복원하거나 다시 노출하지 않습니다.** 문구 변경을 통한 재도입도 금지합니다. 로그인 없이 `/codes`로 들어가는 흐름을 유지하며, 원본 기능 보존이나 선택형 JWT 지원은 이 메뉴를 되살릴 근거가 아닙니다. 사용자가 명시적으로 금지를 철회하기 전에는 인증 모드도 임의로 변경하지 않습니다. 후속 작업 기준은 [AGENTS.md](AGENTS.md)를 따릅니다.

## 2026-09-21 로컬 구현 상태

외부 AI 호출 없이 원본과의 기능 연결을 정리했다. 검색 모드·HyDE·멀티쿼리·청킹 설정은 임베딩 미연결 중에도 저장되며, 임베딩 연결 및 재인덱싱 후 적용된다. 실행 중 필요한 제약이 원래 선택값을 덮어쓰지 않는다. 기능 범위와 원본 자체의 미완성 부분은 [기능 비교](docs/FUNCTIONAL_PARITY.md)를 확인한다.

기본 `CODE_AUTH_MODE=local`에서는 **로그인·관리자 비밀번호 입력 없이** `http://localhost:3500/codes`로 바로 들어갑니다. 이 Mac에서 접속하는 사람은 모두 동일한 로컬 관리자 계정으로 모든 기능을 사용하며, 대화·초안·변경 기록도 같은 사용자 ID에 연결됩니다. 계정별 구분이 필요하면 `CODE_AUTH_MODE=jwt`로 원본 로그인을 선택합니다.

관리자 **알림 코드 → AI 설정**에서 **DeepSeek / Claude / OpenAI**와 API 키를 선택할 수 있습니다. DeepSeek는 직접 API와 기존 Command Code 연결을 모두 지원합니다. 검색 방식은 AI 공급자와 별도로 **임베딩 없이 키워드 검색 / Mac 로컬 임베딩 / OpenAI 임베딩** 중 선택합니다. **임베딩은 필수가 아닙니다.** Claude API 키만 있다면 Claude + 키워드 검색을 사용할 수 있고, 로컬 모델이 준비되면 Claude + 로컬 의미 검색도 가능합니다.

원본 고정 버전 384개 파일 검증과 전체 프론트엔드·백엔드 Docker 빌드를 수행했습니다. 실제 Command Code 경유 DeepSeek 호출과 Mac의 Docker 안에서 실행한 로컬 E5 모델의 합성 문장 벡터 검사를 통과했습니다. PostgreSQL·Nori·Redis·Langfuse·원본 Next/API·작업자도 기동했습니다. 실제 Next 화면의 무로그인 진입·AI 설정 저장 및 재조회와 실제 HTTP 6개 검사를 통과했습니다. 확장 테스트 142개와 설치 도구 테스트 59개가 통과했으며, 실제 목록은 문서·카탈로그 모두 0건입니다. **직접 DeepSeek / Claude / OpenAI 키의 실제 호출과 카탈로그 전체 검색·초안·승인 종단간 검증은 완료되지 않았습니다.**

대화 답변의 충실도·근거 판정만 다른 모델로 돌리려면 `.env`에 `CODE_LLM_JUDGE_MODEL`(선택 `CODE_LLM_JUDGE_REASONING_EFFORT`)을 설정합니다. 비워 두면 지금처럼 생성 모델이 판정합니다. 설정 방법과 각 검색 방식의 차이는 [AI 설정 안내](docs/AI_SETTINGS.md), 검사별 근거와 현재 제한은 [검증 보고서](docs/TEST_REPORT.md)를 확인하세요. 아래 9월 18일 전달 기록과 [이전 로컬 검증 보고서](docs/LOCAL_VERIFICATION_2026-09-21.md)는 당시 수행 범위를 보존한 기록입니다. macOS에서는 `CODE_LLM_JUDGE_PROVIDER=apple`로 판정 두 단계만 Apple Intelligence 온디바이스 모델(`extensions/apple_bridge`)에 맡길 수도 있습니다. 브리지가 꺼져 있으면 판정은 503으로 중단되고 생성 모델로 되돌아가지 않으며, 설정과 실측은 [AI 설정](docs/AI_SETTINGS.md)과 검증 보고서의 2026-09-22 Apple 항목을 보세요.

## 통합 구성

이전 설치본과 달리 **실제 통합 백엔드·화면·대화 에이전트 소스와 테스트가 포함**되어 있습니다. 기본 실행에 `extensions/code_agent`가 원본 FastAPI 안으로 로드되고, 원본 Next.js의 `/codes` 메뉴가 같은 앱 안에서 작업실을 엽니다. 별도 SQLite/공유 키 앱으로 대체하지 않습니다.

**구현 완료와 운영 검증은 구분합니다.** 도메인/API/연동 계약과 화면 검사를 수행했으며, 실제 서비스 기동·외부 모델 호출·모의 응답을 사용하는 검사의 범위를 [검증 보고서](docs/TEST_REPORT.md)에 구분합니다.

원본 전체 소스는 ZIP에 들어 있지 않으며, 첫 실행 때 공식 GitHub에서 아래 버전을 받아 `upstream/`에 저장합니다. 받지 못하면 중단하고, 다른 작은 앱으로 대체 실행하지 않습니다.

- 원본: `urstory/urstory-rag`
- 커밋: `75661c676aec650e52f75dd068b687a4cb6a63b7`
- 원본 Git tree: `6e5ebcef24cfc575f5659329d946cc56c103c9ca`
- 원본 저장소는 전체 보존합니다. 필요한 버그 패치는 빌드되는 컨테이너 사본에만 적용하고 변경 해시를 남깁니다.

## 실행

Python 3.10 이상, 실행 중인 Docker Engine/Desktop, Docker Compose 2.20 이상, 의존성과 원본을 받을 인터넷 연결이 필요합니다. API·작업자·모델 라이브러리·Next.js·PGVector·Elasticsearch/Nori·Redis·Langfuse가 포함된 전체 구성입니다. 가벼운 단일 프로세스 앱이 아니며 메모리 요구량과 빌드 시간은 실제 환경에서 확인해야 합니다.

```bash
cd code_management
python3 scripts/manage.py start
```

원본 전체 다운로드·검증 → 원본 의존성 + 확장 설치 → 원본 DB 마이그레이션 + 카탈로그 테이블 생성 → 서비스 시작을 진행합니다. 외부 API 키는 터미널에서 입력받아 권한 0600인 `.env`에 보관합니다.

기본 접속: **http://localhost:3500/codes**

```bash
# 선택한 인증 모드 확인 (모델 API 키는 출력하지 않음)
python3 scripts/manage.py credentials

# 상태 확인 / 종료. 데이터 볼륨을 삭제하지 않습니다.
python3 scripts/manage.py status
python3 scripts/manage.py stop
```

기본 로컬 모드는 로그인 화면을 거치지 않으며 관리자 기능도 바로 사용할 수 있습니다. 원본 DB의 실제 로컬 관리자 계정을 사용하고 정식 등록의 사유·버전·중복 확인은 유지합니다. 선택형 `jwt` 모드에서는 원본 로그인과 권한 검사를 사용하며, 작업실 토큰을 메모리의 `postMessage`로 전달합니다.

기존 설치를 갱신할 때는 `.env`와 데이터 볼륨을 유지하세요. `jwt` 모드에서 새 비밀번호를 설정 파일에 적는 것만으로 기존 DB 계정의 비밀번호가 바뀌지는 않습니다. 다른 설치와 Compose 프로젝트 이름을 공유하지 마세요.

기존 원본 체크아웃을 갖고 있으면 다음 방식도 가능합니다.

```bash
python3 scripts/manage.py prepare --source /경로/urstory-rag
python3 scripts/manage.py start
```

지정된 고정 커밋과 다른 소스, 누락·변경된 파일은 검증에서 거절합니다. `upstream/`은 직접 수정하지 않고 `extensions/` 또는 `deploy/patch_*`에서 변경을 추적합니다.

## 기획자 사용 순서

### 1. JSON 샘플 목록 확인

화면의 엑셀·CSV 파일 가져오기 메뉴, 업로드 폼, 파일 선택과 드래그 영역을 제거했습니다. **전체 코드**를 열면 기본으로 **JSON 샘플 · 300건**을 조회합니다. 기존 GitHub 합성 예시 16건을 보존하고 새 합성 예시 284건을 추가했습니다. 사용 중 279건/폐기 21건이며, 실제 회사 정책이나 등록 목록이 아닙니다.

샘플은 `extensions/code_agent/data/sample_catalog_300.json`에 저장합니다. 코드번호·문구·메뉴·노출 조건·상태·출처와 업무구분·타입·타이틀·용도를 포함합니다. **JSON 내보내기**는 현재 선택한 목록 전체를 구조화된 JSON으로 내려받습니다. 검색·상태 필터·30건 단위 페이지 이동·상세·문구 비교·기획서 검토에서 사용할 수 있습니다.

실제 목록과 샘플은 분리되어 있습니다. 샘플은 실제 등록 DB에는 삽입하지 않습니다. 샘플 대화와 전용 검색 인덱스를 별도로 사용하며, 대화에서도 선택한 샘플을 검색합니다. 기존 가져오기 API의 미리보기·버전·승인 보호 장치는 호환성을 위해 유지하지만 화면에서는 제공하지 않습니다. JSON 구성은 [샘플 안내](docs/JSON_SAMPLES.md)를 참고하세요.

### 2. 대화로 기존 코드 검색

- `AT-1923 문구 알려줘` → 원문 DB 직접 조회, 일반적인 단순 조회에는 LLM을 부르지 않습니다.
- `인증 전에 기다리라는 알림이 있어?` → 선택한 키워드 또는 하이브리드 검색과 리랭킹 후 후보와 설명을 제공합니다.
- `두 번째 후보는 어떤 상황이야?` → 직전 검색 후보의 순서와 대화 문맥을 이어서 사용합니다.

등록 문구는 **DB 원문 그대로** 출력·복사하고 모델 설명과 구분합니다. 코드가 없으면 미등록으로 표시합니다. 후보가 변경·폐기되었으면 최신 검색을 요구합니다.

### 3. 문구 비교와 신규 작성

`30초 이내에 인증해주세요`처럼 작성한 표시 문구를 ‘비교할 문구’에 입력하거나 대화에 그대로 적고 비교를 요청합니다. 시간·수치·일부 부정 표현·변수 차이를 규칙으로 확인하고, AI가 관련 근거를 설명합니다. 의미가 비슷하다고 재사용을 확정하지 않습니다.

`맞는 게 없으니 이 상황에 맞게 새로 써줘`라고 하면 기존 후보 확인 → 모델의 문구 초안 → 생성 문구로 재검색 → 조건 비교 → 미등록 초안 저장 순으로 처리합니다. 사용자가 직접 적은 표시 문구는 원문을 유지합니다. AI가 숫자·변수 등을 바꾸면 저장하지 않습니다. 비교와 생성은 보수적인 보호 장치이지 모든 업무 의미를 판정하는 증명이 아닙니다.

### 4. 초안 검토와 정식 등록

초안은 번호가 없는 상태입니다. 기본 로컬 모드에서는 접속자 모두 같은 관리자 신원을 공유합니다. 선택형 JWT 모드의 일반 사용자는 자신의 대화와 초안을 보고 작성할 수 있고, 관리자는 초안 목록·가져오기·변경 기록·등록을 처리합니다. 다른 사람의 개인 대화는 관리자에게도 공개하지 않습니다.

`CODE_CATALOG_AUTHORITY=excel`에서는 **엑셀 절차에서 확정된 번호인지 관리자가 확인한 뒤 직접 입력**합니다. 시스템을 공식 목록으로 운영하기로 결정했다면 `system`으로 설정합니다. compose.yaml과 현재 `.env`의 기본값은 `system`이며, 엑셀 확인 절차를 쓰려면 `.env`에서 `excel`로 바꿉니다. 두 모드 모두 현재 통합판은 관리자가 승인한 번호를 직접 입력하며 AI가 다음 번호를 추측하지 않습니다.

최신 목록으로 다시 검토하고 중복 후보를 확인한 후 사유를 적어 등록합니다. 등록·변경은 DB 트랜잭션과 버전 검사를 거치고 승인자 ID를 기록합니다. 기존 번호와 폐기 번호를 재사용하지 않습니다. 초안 저장이나 대화에서 ‘등록해’라는 말만으로 정식 등록하지 않습니다.

‘기획서에 복사’는 코드·원문·기존 조건과 이번 기획의 조건을 구분합니다. CSV 내보내기는 수식 삽입을 막기 위해 위험한 시작 문자에 작은따옴표를 덧붙일 수 있습니다. DB 원문은 변경하지 않습니다.

## 원본 RAG 연동 방식

`extensions/code_agent/gateway.py`가 원본 `HybridSearchOrchestrator`, `VectorSearchEngine`, `ElasticsearchNoriEngine`, 임베딩·LLM·한국어 리랭커·Langfuse를 실제 import/call합니다. 카탈로그의 원문·승인 상태는 같은 PostgreSQL 안의 전용 테이블로 관리하고, 검색에는 전용 벡터 테이블과 Nori 인덱스를 사용합니다. 검색 결과는 다시 최신 원문 DB와 대조합니다.

원본 문서 관리·일반 검색·설정·평가·모니터링 화면은 지우거나 작은 화면으로 대체하지 않습니다. 카탈로그 질문은 `/api/code-catalog`로 보내고 일반 문서 검색은 원본 경로를 유지합니다. 전체 검색 단계를 RRF 한 파일로 대체한 이전 버전이 아닙니다.

## 코드·문서 위치

```text
code_management/
├── extensions/code_agent/        통합 API·DB·대화·검색 어댑터·인덱서·화면
├── extensions/frontend/          원본 Next.js에 추가하는 /codes 페이지
├── deploy/                      전체 원본 빌드 + 추적 가능한 버그 패치
├── scripts/                     원본 수집·검증·실행·기동 후 검사
├── integration_tests/           도메인·API·원본 연동 계약·브라우저·HTTP 검사
├── tests/                       설치 도구 회귀 검사
├── docs/INTEGRATION.md           설계·연동 경계·보호 장치
├── docs/TEST_REPORT.md           이번 버전의 실제 검사 결과
├── docs/verification/           이번 검사 원본 로그·화면·기계 판독 결과
├── docs/history/                이전 설치본의 기록 (현재 상태가 아님)
├── catalog_legacy/              이전 독립 앱 보존본. 기본 실행에서는 사용하지 않음
└── upstream/                    prepare 성공 시 내려받는 전체 원본
```

기존 독립 앱의 SQLite를 자동 이관하지는 않습니다. 공식 엑셀을 새 통합 카탈로그로 가져오세요. 사용자 Docker Local에 복사·배포한 상태는 아닙니다.

## 검증 명령

```bash
# 설치 도구
python3 -m unittest discover -s tests -v

# 통합 확장 자체 (테스트 전용 의존성)
python3 -m venv .test-venv
source .test-venv/bin/activate
pip install -r integration_tests/requirements.txt
PYTHONPATH=extensions python -m pytest integration_tests -q
PYTHONPATH=extensions python integration_tests/native_http_check.py

# Chromium 설치가 있는 테스트 환경
PYTHONPATH=extensions python integration_tests/browser_check.py
# 브라우저 HTTP 정책 제한 환경에서 파일·API 브리지 검사 (종단간 HTTP 검증 아님)
PYTHONPATH=extensions python integration_tests/browser_offline_check.py

# 실제 전체 서비스가 기동된 후: 원본 로그인·문서/API 연결 검사
python3 scripts/smoke.py
python3 scripts/test_upstream.py
```

브라우저 검사 스크립트는 `CHROMIUM_PATH` 환경변수, 없으면 `/usr/bin/chromium`, 그것도 없으면 Playwright가 설치한 Chromium을 사용합니다. Mac에서는 `playwright install chromium`을 실행했거나 `CHROMIUM_PATH`로 Chromium 실행 파일(예: `~/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`)을 지정해야 합니다. `scripts/test_upstream.py`는 원본 테스트용 PostgreSQL(pgvector)을 내부 전용 Docker 네트워크에 일회성으로 띄운 뒤 삭제하며, 운영 볼륨은 건드리지 않습니다. 모의 로그인·LLM은 `integration_tests/` 안에만 있고 운영 Docker 이미지의 확장 코드에는 포함하지 않습니다.

## 운영 전 확인

문구와 질문은 선택한 외부 LLM에 전달될 수 있습니다. OpenAI 임베딩을 선택하면 임베딩 요청도 외부로 전송됩니다. 로컬 임베딩은 이 Mac에서 계산하지만 대화·초안 LLM까지 로컬로 바꾸지는 않습니다. 카탈로그는 외부 호출 전 PII를 가리고 새 턴 추적에는 원문을 넣지 않습니다. 원본 문서·검색 경로의 추적과 회사 자료 처리 범위는 별도로 확인해야 합니다. 실제 API 키·회사 자료는 전달본에 포함하지 않습니다.

기본 로컬 모드는 접속자 모두 동일한 관리자 신원을 사용하므로 사람별 대화·초안을 분리하지 않습니다. 선택형 JWT 모드에서는 계정별 대화와 초안을 분리하고 카탈로그를 로그인 사용자에게 공유합니다. 부서별·테넌트별 카탈로그 격리, 다국어별 코드 범위, 승인자의 이중 승인, 원본 서비스의 실제 알림 사용처 추적까지 구현한 것은 아닙니다. 원본 알려진 모든 문제나 전체 보안 감사를 완료한 버전도 아닙니다.

DB·볼륨 백업/복원 및 디스크 암호화는 운영 환경에서 확인하세요. `docker compose down -v`는 데이터를 삭제할 수 있으므로 사용하지 마세요. 현재 README가 최신 기준이며 `catalog_legacy/`와 `docs/history/` 문서는 이전 버전에 대한 기록입니다.

## 합성 샘플 200건으로 바로 검증

`examples/sample_code_catalog_200.xlsx`에 `AT-2001`~`AT-2200` 합성 알림 코드 200건을 넣었다. 실제 회사 데이터가 아니며, 사용중 190건/폐기 10건으로 구성했다. 본인인증·회원가입·입출금·주문·보안·API 등 20개 영역을 포함하고 `30초 이후`/`30초 이내`, 24시간/48시간처럼 유사하지만 조건이 다른 사례도 포함한다.

이 200건 XLSX는 기존 자동 검증 전용 자료다. 현재 화면에는 파일 가져오기 메뉴가 없으며 운영 초기 목록에는 삽입하지 않는다. 로컬 자동 검증은 다음 명령으로 재현한다.

```bash
python3 integration_tests/sample_200_e2e.py
PYTHONPATH=extensions python3 -m pytest integration_tests/test_sample_200.py -q
```

샘플 검증 결과: XLSX 200건 파싱, 신규 200건 미리보기/커밋, 기본 검색 대상 190건(폐기 10건 제외), 자연어 후보 `AT-2011`, `이후/이내` 조건 차이, 48시간 신규 초안과 기존 24시간 코드 `AT-2127` 유사 후보, 관리자 확인 후 `AT-2301` 등록 흐름을 확인했다. 외부 RAG/LLM은 API 키 없이 반복 검증하기 위해 테스트 대역을 사용했으며 실제 OpenAI/Nori/PGVector 품질 측정은 아니다. 자세한 내용은 `docs/SAMPLE_200.md`와 `docs/verification/sample-200-e2e.json`을 참고한다.

## GitHub 메뉴 복원 · 2026-09-21

`알림 코드` 작업실에서 **전체 코드 · 문구 비교 · 기획서 검토 · 변경 기록**을 사용합니다. 전체 코드는 검색·사용 상태 필터·30건 단위 표·원문 상세·복사·JSON 내보내기를 제공합니다. 엑셀의 업무구분·타입·용도·타이틀·영문타이틀·영문컨텐츠도 원문 메타데이터로 보존하며, 변경 시 미리보기·충돌 확인·사유 절차를 유지합니다. 없는 열의 값을 AI로 채우지 않습니다.

전체 코드/문구 비교/기획서 검토의 **조회할 목록 → JSON 샘플 · 300건**을 선택하면 합성 예시를 사용할 수 있습니다. 기존 GitHub의 16건과 추가 생성한 284건으로 구성됩니다. 샘플은 별도 읽기 전용 자료이며 실제 등록 목록·기존 대화·운영 검색 인덱스·감사 기록에 섞지 않습니다. 기존 원본 출처는 `extensions/code_agent/data/github_samples.provenance.json`, 현재 300건의 무결성과 구성은 `sample_catalog_300.provenance.json`에 기록했습니다.

문구 비교와 기획서 검토는 기본적으로 **원문·규칙 비교**를 사용하며 외부 AI를 호출하지 않습니다. 코드번호 직접 조회, 관련 문구 후보, 숫자·시간 방향·변수 차이를 확인합니다. 기획서는 텍스트를 한 줄에 하나씩 최대 30줄 붙여넣습니다. 의미 검색은 별도 선택이며 기존 원본 검색 엔진과 준비된 운영 인덱스를 사용합니다. 실패 시 규칙 비교로 자동 전환하지 않습니다. 샘플은 운영 의미 검색에 포함하지 않습니다.

## 샘플 대화 검색 연결 · 2026-09-21

대화 화면에도 **조회할 목록**이 표시됩니다. 기본값인 **JSON 샘플 · 300건**에서 자연어로 질문하면 기존 UrstoryRAG 검색 엔진과 선택한 AI 공급자를 사용해 샘플 원문을 찾습니다. 샘플 중 사용 중인 279건은 전용 Nori 인덱스와 별도 공개 스냅샷으로 검색하며 폐기 21건은 일반 검색에서 제외합니다. 번호 직접 조회는 폐기 상태도 표시합니다.

샘플 대화 기록과 실제 목록 대화 기록은 분리해 저장합니다. 목록을 바꾸면 해당 목록의 대화 기록을 보여주고, 진행 중 대화의 목록을 바꾸지 못하도록 합니다. 기존 대화는 실제 목록에 그대로 남아 있습니다. 샘플 대화는 검색·비교·설명을 제공하고, 정식 등록용 초안 작성은 실제 목록에서 진행합니다. 샘플 검색 준비가 실패하면 실제 오류를 표시하며 규칙 검색으로 자동 대체하지 않습니다.

### Apple 로컬 대화 AI

AI 설정의 **대화 AI**에서도 **이 Mac의 Apple 온디바이스 모델**을 선택할 수 있습니다. 답변 검증을 Apple 또는 생성 모델과 동일로, 검색을 로컬 임베딩 또는 키워드로 선택하면 생성·판정·검색 모델을 이 Mac에서 사용합니다. 외부 AI로 자동 전환하지 않으며, 지원 범위와 실패 동작은 [AI 설정 안내](docs/AI_SETTINGS.md)를 참조하세요.
