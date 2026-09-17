# Code Library — 기획자용 알림 코드 관리

`AT-1923 → 메뉴확인 30초 이후에 인증해주세요.`처럼 코드번호와 알림 문구를 관리하는 기획자용 웹 애플리케이션입니다. **소스코드 분석 도구가 아닙니다.** 기획자는 상황으로 기존 코드를 찾고, 새 문구의 유사·중복 여부를 검토하고, 선택한 코드와 원문을 기획서에 넣습니다.

## 사진 데이터로 바로 테스트

현재 사진 판독본33건으로 별도 테스트 서버가 실행됩니다. Docker 실행 PC에서 `http://localhost:2999/code-management/`로 바로 접속하며 현재 로컬 설정은 일반 접속 키를 요구하지 않습니다. 실제 다중 접두어 코드와 업무구분·타입·용도·타이틀·영문 컬럼을 지원합니다. 잘린 제목 등은 원본 확인 표시가 있습니다. 상세 실행 방법과 검증은 `docs/PHOTO_TEST.md`를 참고하세요.

## 현재 LLM/관리자 설정 — 2026-09-17

- Claude Code CLI `2.1.274`를 설치했고 `claude -p` 기반 `claude-code` provider를 추가했습니다.
- 화면 왼쪽 아래 **설정 → 관리자 LLM 설정**에서 관리자 비밀번호 확인 후 provider, 모델, API key, 추론 강도를 변경할 수 있습니다.
- Claude Code 실행은 `--bare`, `--restricted`, 도구/스킬 비활성, 세션 미저장 방식이며 `ANTHROPIC_API_KEY`만 실행 프로세스에 전달합니다.
- API key는 화면에 다시 노출하지 않습니다. 저장 값은 데이터 폴더의 `.ai-runtime.json`에 권한 `0600`으로 기록되며 `data/`는 Git에서 제외됩니다.
- 일반 앱 접속의 `ACCESS_TOKEN`은 선택 사항입니다. 현재 Docker Local `.env`에서는 비워 두어 첫 접속 시 키 입력창이 뜨지 않습니다. LLM 변경은 별도 `ADMIN_PASSWORD`로 보호합니다.
- 검색/비교/새 문구/기획서 검토/전체 코드 화면의 작성 중 입력은 같은 브라우저 탭의 `sessionStorage`에 화면별로 유지됩니다. 비밀번호·API key·파일 input은 저장하지 않습니다.
- Claude API key는 아직 사용자가 관리자 화면에 입력하기 전이므로 실제 Claude 호출 검증은 수행하지 않았습니다. 기존 provider는 관리자 화면에서 변경하기 전까지 유지됩니다.

## Docker Local 연결 업데이트 — 2026-09-17

현재 `/shared/code_management`에서 Command Code **DeepSeek V4.1 Flash / Low**를 연결했습니다.
`landing-designer`의 CLI 호출 계약을 참고했으며 해당 프로젝트 파일은 수정하지 않았습니다.
기존에 설치·인증된 CLI를 재사용합니다. API 키를 복사하거나 새로 발급하지 않았습니다.

- 새 문구 작성에서 **AI로 표현 다듬기**를 선택하면 연결된 모델을 호출합니다.
- 코드 찾기에서 **AI로 상황 이해하기**를 선택하면 질문을 최대 3개 검색 표현으로 보완합니다. 코드번호와 원문은 DB에서 그대로 가져옵니다. 임베딩 모델 없이 동작하며, 임베딩 검색과는 다른 기능입니다.
- 저장한 초안을 수정할 수 있습니다. 수정 시 엑셀 등록 요청 상태는 작성 중으로 돌아가고 변경 이유를 기록합니다.
- 엑셀 등록 요청 초안은 확정 코드와 비교 후 등록 완료로 연결할 수 있습니다. 확정 엑셀 비고에 `[draft:초안ID]`가 있고 문구·메뉴·조건이 정확히 일치하면 가져오기 확정 시 자동 연결합니다.
- `.env`에 `AI_PROVIDER=command-code`, `AI_CHAT_MODEL=deepseek/deepseek-v4.1-flash`,
  `AI_REASONING_EFFORT=low`, `AI_ENABLED=true`, `AI_ALLOW_EXTERNAL=true`가 설정되었습니다.
- 실행 파일: `/shared/landing-designer/tooling/node_modules/.bin/cmd`
- Python 전용 환경: `.venv`. 실행: `.venv/bin/python run.py`
- 이번 연결은 Docker Local 호스트의 Python 실행입니다. 기존 Compose 이미지에는 Command Code와
  해당 로그인 환경이 포함되지 않으므로 이 설정 그대로 별도 Compose 컨테이너를 실행할 수 없습니다.
- 기본 API 방식은 `AI_PROVIDER=openai-compatible`로 계속 지원합니다.
- AI 상황 검색은 검색 질문만 전송합니다. AI 다듬기는 입력 문구·메뉴·조건과 기존 후보 최대 5개를 전송합니다. 검색 질문 해석은 최대 128개를 메모리에서 5분간 재사용하며 목록은 항상 다시 조회합니다.
- 한 번 호출하고 자동 재시도하지 않습니다. 도구 사용, 스킬 탐색, 세션 저장을 끄고 빈 임시 폴더에서 실행합니다.
- 실제 합성 문구 호출에서 모델과 Low를 확인했습니다. 상세 기록은 `docs/COMMAND_CODE_CONNECTION.md`를 참고하세요.

아래 **최초 전달본**의 미연결·미배포 설명과 검증 기록은 과거 시점의 기록입니다.

## 현재 실행 관리

```bash
# 앱 상태 / 재시작 / 종료 (code_management만 관리)
supervisorctl -c /shared/code_management/deploy/supervisor.conf status
supervisorctl -c /shared/code_management/deploy/supervisor.conf restart code-management
supervisorctl -c /shared/code_management/deploy/supervisor.conf stop code-management
# Docker Local 자체를 다시 켠 뒤 전용 관리자 시작
supervisord -c /shared/code_management/deploy/supervisor.conf
```

전용 Supervisor가 실행 중인 동안 앱이 비정상 종료되면 자동 재시작합니다. Docker Local 재부팅 시 자동 시작되는 인프라 설정은 변경하지 않았습니다. 현재 포트는 내부 `127.0.0.1:8766`입니다.
최신 구현·검증·남은 입력은 `docs/CURRENT_STATUS.md`를 참고하세요.

## 이 전달본의 최초 상태

- 실행 가능한 Python/FastAPI 애플리케이션, 웹 화면, Docker 실행 구성, 테스트와 엑셀 양식을 포함합니다.
- **사용자 Docker Local에는 생성·설치·배포하지 못했습니다.** 해당 연결의 실행 요청이 `FORBIDDEN: This conversation does not support developer MCPs`로 거절되었습니다. 이 ZIP은 별도 작업 환경에서 작성·검증한 전달본입니다.
- 실제 회사 엑셀이나 AI 모델 키는 제공받지 않았으므로 실제 회사 검색 정확도나 모델 응답 품질은 검증하지 않았습니다.
- urstory-rag의 **RRFCombiner 모듈을 실제 호출하도록 재사용한 경량 독립 앱**입니다. 원본 전체 프로젝트를 복제하여 Next.js/PostgreSQL/Elasticsearch/Celery/Langfuse를 배포한 버전은 아닙니다. 자세한 재사용 범위는 `docs/UPSTREAM.md`를 참고하세요.
- 기본 상태는 **AI 미연결**입니다. 코드 직접 조회, 한국어 도메인 키워드·문자 유사 검색, 규칙 기반 조건 비교, 초안 저장이 동작합니다. 의미 임베딩 검색과 AI 문장 다듬기는 별도 모델 연결이 필요합니다. 기본 검색을 AI 의미 검색으로 표시하지 않습니다.

## 빠른 실행 — Docker가 설치된 머신

ZIP을 풀면 `code_management` 폴더가 나옵니다. 해당 폴더에서 실행합니다.

```bash
cd code_management
cp .env.example .env
# .env의 ADMIN_PASSWORD를 설정하고 필요하면 ACCESS_TOKEN도 설정
docker compose up -d --build
```

브라우저에서 `http://localhost:8766`을 엽니다. `ACCESS_TOKEN`을 비워 두면 바로 접속하며, 값을 설정한 경우에만 접속 키 화면을 사용합니다. `.env`와 런타임 AI key 파일은 Git에 올리면 안 됩니다. 첫 실행에는 Python 베이스 이미지와 의존성 다운로드를 위한 인터넷 연결이 필요합니다.

서버는 호스트의 `127.0.0.1`에만 공개됩니다. 8766 포트가 이미 사용 중이면 `.env`의 `PORT`를 변경하세요. 기존의 다른 앱·컨테이너는 수정하거나 종료하지 않습니다.

```bash
# 상태 / 로그
docker compose ps
docker compose logs --tail=80 app

# 종료 — 데이터를 지우지 않음
docker compose down
```

데이터는 Docker의 `catalog-data` 볼륨에 보관됩니다. **`docker compose down -v`는 데이터를 삭제하므로 사용하지 마세요.** Docker 이미지 빌드와 사용자 머신에서의 실행은 이번 환경에서 검증하지 못했습니다.

## Docker 없이 Python으로 실행

Python 3.13에서 테스트했습니다.

```bash
cd code_management
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env의 ADMIN_PASSWORD를 설정
python run.py
```

Windows PowerShell에서는 가상환경 활성화 명령만 다릅니다.

```powershell
.venv\Scripts\Activate.ps1
python run.py
```

실제 코드 목록은 처음에는 비어 있습니다. 화면 오른쪽 위의 **실제 목록 ⇄ 예시 목록**을 눌러 합성 예시 16개로 먼저 사용해볼 수 있습니다. 예시는 `demo`, 실제 항목은 `live`로 분리됩니다. 예시 원문이나 번호를 실제 기획서에 쓰지 마세요.

## 기획자의 사용 순서

### 1. 엑셀 가져오기

‘엑셀 가져오기’에서 `.xlsx` 또는 `.csv`를 선택합니다. 필수 항목은 **코드번호와 등록 문구**입니다. 메뉴, 노출 조건, 비고, 상태는 선택 항목입니다.

`examples/code_catalog_template.xlsx`는 빈 양식이며, 실제 목록에 들어갈 예시 행을 포함하지 않습니다. 기존 양식도 헤더 별칭이나 미리보기의 ‘열 직접 연결’로 사용할 수 있습니다.

파일을 고르면 추가 예정·기존과 동일·번호 충돌·오류가 표시됩니다. 확인 전에는 실제 목록에 반영되지 않습니다. **기존 코드와 다른 원문은 자동으로 덮어쓰지 않습니다.** 원문을 갱신하려면 충돌 행을 개별 선택하고 이유를 입력해야 합니다. 선택하지 않은 충돌 행은 명시적으로 제외할 수 있습니다. 가져오기에 없는 기존 항목을 자동 삭제하지 않습니다.

원문은 코드별로 보존하고 파일명, 시트, 행·셀 위치, 원본 파일 해시를 함께 기록합니다. 원본 업로드 파일은 로컬 데이터 폴더에 별도 보관합니다.

지원 제한: 파일 8MB, 압축 해제 48MB, 시트 30개, 목록당 코드 10,000개. 수식, 매크로, 외부 연결, 암호화 엑셀, `.xls`는 지원하지 않습니다. 수식 셀은 계산하거나 캐시값을 믿지 않고 오류로 표시합니다. 코드·문구의 세로 병합도 임의로 펼치지 않습니다.

### 2. 코드 찾기

- `AT-1923이 뭐야?` → 직접 조회. 코드가 없으면 없다고 답합니다.
- `인증 전에 30초 기다리라는 알림 있어?` → 상황에 관련된 후보를 제시합니다.
- `이미 가입된 전화번호라는 안내 찾아줘` → 기존 후보의 번호·원문·노출 조건을 표시합니다.

원문은 AI가 재작성하지 않고 DB에서 그대로 표시합니다. 검색 결과가 있다는 사실만으로 재사용을 확정하지 않습니다. ‘기획서에 복사’는 기존 등록 조건과 이번 기획에서 작성할 조건을 구분합니다.

### 3. 문구 비교

새로 작성한 문구를 입력해 기존 항목과 비교합니다. 수치·단위, 이후/이내 등의 조건 방향, 일부 부정 표현, `{seconds}` 등의 자리표시자 차이를 검사합니다. **이 검사는 보수적인 규칙 기반 검토이며 모든 업무적 의미 차이를 판별하는 시스템은 아닙니다.** 메뉴·노출 조건이 없으면 재사용 확정 대신 확인이 필요하다고 표시합니다.

### 4. 새 문구와 초안함

새 문구를 저장하기 전에 유사 항목을 조회할 수 있습니다. AI가 연결되지 않았다면 입력 원문 그대로 초안으로 저장합니다. AI 문장 다듬기는 입력 문구의 숫자·조건·변수를 바꾸는 결과를 거절하지만, 그 검사만으로 의미 보존을 완벽히 보장하지 않으므로 사람이 확인해야 합니다.

초안에는 정식 번호가 없습니다. ‘초안 저장’과 ‘정식 등록’은 별도 작업입니다. 이미 등록된 항목은 상세 화면에서 변경 초안을 만들 수 있습니다.

### 5. 공식 목록을 어디서 관리할지 선택

기본값 `CATALOG_AUTHORITY=excel`에서는 공식 번호 발급을 엑셀 담당자가 맡습니다. 초안은 ‘엑셀 등록 요청’으로 표시하거나 CSV로 내보냅니다. 앱은 임의의 정식 번호를 발급하지 않습니다. 번호를 확정한 엑셀을 가져오면 코드 목록에 반영됩니다. 초안 내보내기의 **등록연결표시** 값을 확정 엑셀 비고에 넣으면 ID와 문구·메뉴·조건이 모두 같고 후보가 하나일 때 자동으로 등록 완료 처리합니다. 일치하지 않거나 후보가 여러 개면 자동 연결하지 않습니다. 초안 검토 화면의 **엑셀 등록 확인**에서 원문을 비교한 뒤 이유를 입력해 직접 연결할 수 있습니다. 등록 코드의 원문은 변경하지 않습니다.

시스템을 공식 목록으로 전환하기로 결정했다면 `.env`에서 `CATALOG_AUTHORITY=system`으로 설정하고 서버를 재시작합니다. 초안 검토 후 승인한 번호를 직접 입력하거나, **미리 승인한 발급 규칙**으로만 번호를 만듭니다. 발급 규칙은 기본적으로 비어 있습니다.

```dotenv
CATALOG_AUTHORITY=system
# 아래는 예시입니다. 회사의 실제 발급 규칙으로 확정한 후 입력하세요.
CODE_RULES_JSON={"AT":{"start":2000,"width":4}}
```

동시 등록은 DB 트랜잭션으로 처리하고, 같은 번호나 폐기 번호를 재발급하지 않습니다. 검토 후 목록이 변경되었으면 재검토를 요구합니다. 문구 변경은 원본 버전과 대조하고 변경 전후·이유를 기록합니다.

### 6. 기획서 검토

한 줄에 하나씩 코드번호 또는 문구를 입력하면 최대 30개 항목을 기존 목록과 비교합니다. 이 기능은 자유형 기획서 전체의 정책 해석이나 소스코드 사용처 추적이 아닙니다.

## 선택: AI 연결

지원 provider는 `claude-code`, `openai-compatible`, 기존 `command-code`입니다. Claude Code는 관리자 화면에서 Anthropic API key와 모델을 입력해 바로 전환할 수 있습니다. OpenAI-compatible `/chat/completions` 방식도 유지합니다. API key는 브라우저 응답으로 다시 전달하지 않습니다.

로컬 모델 서버의 실제 모델 ID를 확인해 설정합니다. Docker 내부에서 호스트 머신에 연결하는 주소와, Python 직접 실행 시 주소는 다릅니다.

```dotenv
AI_ENABLED=true
# Docker에서 호스트의 로컬 모델 서버를 사용할 때의 예시
AI_BASE_URL=http://host.docker.internal:1234/v1
# Python 직접 실행이면 서버에 맞게 http://127.0.0.1:1234/v1 등으로 변경
AI_CHAT_MODEL=실제로_로드한_채팅_모델_ID
AI_EMBEDDING_MODEL=실제로_로드한_임베딩_모델_ID
AI_API_KEY=
AI_ALLOW_EXTERNAL=false
```

서버를 재시작한 뒤 화면 왼쪽 아래 ‘연결 및 운영 기준 → AI 검색 준비하기’를 실행합니다. 코드 문구·메뉴·노출 조건이 설정된 모델 서버로 전송됩니다. 이후 검색어도 해당 서버로 전송됩니다. 생성된 벡터는 서버 주소·모델 ID·항목 내용에 연결해 보관하며, 변경된 항목은 재생성해야 합니다. 임베딩이 일부 없거나 서버에 오류가 있으면 기본 검색으로 보완하고 화면에 표시합니다.

외부 클라우드 모델을 사용하려면 HTTPS 주소와 `AI_ALLOW_EXTERNAL=true`가 필요합니다. 사내 자료 반출 승인을 먼저 확인하세요. 모델 연결 전에는 학습·임베딩·채팅을 위한 데이터 전송이 없습니다. AI 서비스를 자동으로 설치하거나 모델을 다운로드하는 기능은 포함하지 않습니다.

## 테스트

```bash
pip install -r requirements-dev.txt
python -m pytest
python scripts/verify_vendor.py
```

현재 결과는 `docs/TEST_REPORT.md`에 기록했습니다. API·규칙·동시성 테스트와 브라우저 UI 검사를 구분합니다. 테스트 데이터는 합성 예시이며 회사 업무 정확도 평가를 대신하지 않습니다.

## 디렉터리

```text
code_management/
├── catalog/           # API, DB, 엑셀/CSV 읽기, 검색, 비교, 초안·승인
├── static/            # 반응형 기획자 화면
├── vendor/urstory_rag/# 원본 RRF 재사용 + MIT 라이선스 + 출처
├── examples/          # 빈 엑셀 양식
├── scripts/           # 실행 준비, 백업, 브라우저 검사
├── tests/             # 합성 데이터 기반 자동 테스트
├── docs/              # 설계, 보안·한계, 검증 기록
├── compose.yaml
├── Dockerfile
├── requirements.txt
└── run.py
```

## 운영 전 확인

이 버전은 **단일 사용자 또는 하나의 공유 접속 키를 사용하는 로컬 검증용**입니다. SSO, 사용자별 권한, 부서별 자료 접근 분리, 실제 개발 서비스에 대한 코드 사용처 추적, 다국어별 코드 관리, 대규모 검색 품질 검증은 추가 작업입니다. 승인 이력에는 개인 사용자 신원을 별도로 기록하지 않습니다. 공유 접속 키로 운영하면서 개인별 승인자 감사가 가능하다고 해석하면 안 됩니다.

DB와 원본 파일을 암호화 저장하지 않으므로 호스트의 디스크 암호화와 접근권한을 확인하세요. 데이터를 유지하려면 볼륨 백업이 필요합니다. `scripts/backup.py`는 SQLite backup API로 일관된 DB 스냅샷과 원본 파일을 복사합니다. CSV 내보내기는 수식 삽입 방지를 위해 `= + - @`로 시작하는 값에 작은따옴표를 붙일 수 있으며, DB 원문을 수정하지 않습니다. 바이트 단위 원문 보존이 필요한 이관에는 CSV가 아니라 DB 백업과 원본 파일을 사용하세요.
