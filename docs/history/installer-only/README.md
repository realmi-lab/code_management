# Code Management — UrstoryRAG 원본 전체 실행 패키지

## 현재 전달 상태 — 먼저 확인

이 전달본은 **원본 전체를 내려받아 동일한 애플리케이션 코드를 빌드·실행하는 설치 패키지**입니다. 이전의 RRF 모듈 하나만 사용한 경량판을 원본 전체판으로 부르는 것이 아닙니다.

**이번 ZIP에는 원본 저장소 전체 소스가 아직 들어 있지 않습니다.** 작성 환경에서 GitHub 압축 다운로드가 실패했고 Docker 실행 도구도 없었습니다. 실행 시 공식 GitHub에서 고정 커밋의 전체 파일을 `upstream/`에 내려받습니다. 전체 파일의 Git tree가 아래 값과 일치해야만 빌드를 진행합니다. 다운로드나 검증에 실패하면 중단하며, 경량판으로 몰래 대체하지 않습니다.

- 원본: `https://github.com/urstory/urstory-rag`
- 고정 커밋: `75661c676aec650e52f75dd068b687a4cb6a63b7`
- 원본 전체 Git tree: `6e5ebcef24cfc575f5659329d946cc56c103c9ca`
- **사용자 맥·Docker Local에는 복사하거나 실행하지 못했습니다.**
- 설치 도구의 자동 테스트와 실제 RAG 실행 검증은 다릅니다. 정확한 수행 범위는 `docs/STATUS.md`에 있습니다.

## 시작

필요한 실행 도구는 Python 3.10 이상, 실행 중인 Docker Engine/Desktop와 Docker Compose v2.20 이상입니다. 애플리케이션의 Python·Node·DB 등은 컨테이너에서 설치합니다. 원본과 모델·의존성을 받는 인터넷 연결 및 원본이 사용하는 OpenAI API 키가 필요합니다.

압축을 풀면 `code_management` 폴더가 생깁니다. 그 폴더에서:

```bash
python3 scripts/manage.py start
```

Mac에서는 `start.command`를 실행해도 같습니다. 터미널에서는 `bash start.command`를 사용할 수 있습니다. **설치 도구는 macOS/Linux 파일 권한을 기준으로 작성했습니다.** Windows에서는 Docker Desktop의 WSL 연동을 켜고 WSL의 Linux 파일시스템 안에서 실행해야 합니다. Windows 네이티브 파일시스템의 실행 권한·심볼릭 링크 보존은 지원·검증하지 않았습니다.

이 명령은 Docker 확인 → 로컬 설정 → API 키 입력 → 포트 충돌 검사 → 원본 전체 수집·검증 → 컨테이너 빌드·기동 순으로 실행됩니다. 관리자가 직접 입력하지 않은 API 키를 임의로 만들지 않습니다. 원본 파일이나 기존 데이터 볼륨을 삭제하지 않습니다.

기본 접속 위치:

| 용도 | 주소 |
|---|---|
| **원본 Next.js 관리자 화면** | `http://localhost:3500` |
| 원본 API / Swagger | `http://localhost:8000/docs` |
| 원본에서 사용하는 Langfuse v3 | `http://localhost:3100` |

관리자 계정 정보는 다음 명령으로 확인합니다. API 키·DB 비밀번호는 출력하지 않습니다.

```bash
python3 scripts/manage.py credentials
```

비밀번호는 처음 설정할 때 무작위로 생성합니다. 실제 값은 로컬 `.env`에 저장되며 파일 권한은 0600입니다. `.env`를 공유하거나 Git에 올리지 마세요. 기존 DB가 있으면 `.env` 값을 바꾸는 것만으로 기존 사용자의 비밀번호가 초기화되지는 않습니다.

포트가 사용 중이면 **기존 앱을 종료하지 않고 중단**합니다. `.env`의 `WEB_PORT`, `API_PORT`, `LANGFUSE_PORT`를 변경한 뒤 다시 실행하세요. 이 구성은 호스트 `127.0.0.1`에만 포트를 공개합니다.

## 무엇이 원본과 같은가

새 검색 엔진을 비슷하게 작성하는 것이 아니라 원본 전체 애플리케이션 파일을 그대로 사용합니다. 아래 구성 요소를 일부 코드로 대체하거나 의존성 목록에서 빼지 않습니다.

| 구성 요소 | 적용 방식 |
|---|---|
| Next.js / React / shadcn 기반 화면 | 원본 `frontend/` 전체를 빌드 |
| FastAPI / Haystack 기반 처리 | 원본 `backend/` 전체와 원본 의존성을 설치 |
| PGVector + Elasticsearch Nori | 원본 검색 코드와 실제 두 저장소 사용 |
| 한국어 Cross-Encoder 리랭커 | 원본 모델 로딩·실행 코드 사용 |
| HyDE / 질문 확장 / 멀티쿼리 / RRF | 원본 검색 파이프라인 유지 |
| 근거 기반 답변 생성 / 숫자 검증 | 원본 생성·검증 코드 유지 |
| PII / 인젝션 / 환각·충실도 검증 | 원본 모듈과 설정 유지 |
| PDF / DOCX / TXT / Markdown | 원본 변환기와 Docling 포함 |
| JWT / 관리자·사용자 / API 키 | 원본 인증·권한·관리 기능 유지 |
| OpenAI 호환 API | 원본 `/v1/chat/completions` 구현 유지 |
| RAGAS·Judge 평가 | 원본 평가 기능·의존성 유지 |
| Redis·Celery·Langfuse | 실제 캐시·워커·모니터링 서비스 구성 |
| 문서 감시·테스트·문서·원본 라이선스 | 소스 전체에 포함하며 삭제하지 않음 |

이 표는 **설치가 성공했을 때 실행하는 코드의 범위**입니다. 이 작성 환경에서 해당 기능들을 직접 실행했다는 뜻이 아닙니다. 모델 응답, 검색 정확도, 속도, 장기 안정성까지 원본 작성자의 보고값과 동일하다고 보장하지 않습니다.

## 실행 환경에서 바꾼 부분

원본 애플리케이션 코드는 수정하지 않고 별도의 `deploy/`와 `compose.yaml`로 실행 환경만 보완했습니다.

1. 기존 공용 `shared-infra` 네트워크·외부 DB 의존 대신 이 프로젝트 전용 PostgreSQL·Elasticsearch·Redis를 띄웁니다.
2. Celery 인덱싱 워커와 Beat를 추가합니다. 원본 태스크의 실제 진입점인 `app.worker:celery_app`을 사용합니다.
3. API와 워커가 `/app/uploads` 볼륨을 공유합니다. 모델 캐시도 영속화합니다.
4. Alembic 마이그레이션이 성공한 뒤 API·워커를 시작합니다.
5. Next.js의 API rewrite 주소를 빌드 시점에 지정합니다. 런타임 환경변수만 넣지 않습니다.
6. API 헬스체크에 이미지 안의 Python을 사용합니다. 설치하지 않은 curl을 API 이미지에서 호출하지 않습니다.
7. Langfuse용 DB·ClickHouse·Redis·MinIO·버킷 초기화와 초기 사용자·프로젝트·키 설정을 함께 구성합니다.
8. 공개 포트를 로컬 인터페이스로 제한하고 기본 비밀번호 대신 별도 비밀값을 생성합니다.

상태 확인·종료:

```bash
python3 scripts/manage.py status
python3 scripts/manage.py stop
```

종료는 이 프로젝트의 컨테이너만 정지하며 볼륨을 삭제하지 않습니다. **`docker compose down -v`를 사용하면 자료가 삭제될 수 있습니다.** 운영 백업·복원 절차는 별도 검증이 필요합니다. 원본에 포함된 운영 스크립트도 이 독립 실행 구성에 대한 적용성을 확인한 뒤 사용해야 합니다.

## 기존 기획자용 코드 관리 앱

이전 전달본은 `catalog_legacy/`에 **그대로 보존**했습니다. 원본 전체 앱과 혼동하지 않도록 기본 실행에서는 켜지지 않습니다.

```bash
python3 scripts/manage.py start --legacy
```

이를 실행하면 기존 앱도 `http://localhost:8766`에서 별도로 열립니다. 기존 앱의 SQLite·공유 접속 키·규칙 기반 검색은 그대로입니다. **원본의 JWT 계정·하이브리드 검색·대화 기능과 자동 통합된 것은 아닙니다.** 데이터 역시 분리되어 있습니다. 기존 사용자의 외부 Docker 볼륨을 자동 탐색·이관하지 않습니다.

이번 변경의 목적은 원본 전체 애플리케이션을 실제로 사용하는 실행 기반을 확보하는 것입니다. 엑셀 알림 코드 검색·등록을 원본 Next.js 화면과 원본 RAG에 통합하는 작업은 아직 완료하지 않았습니다. 이를 완료한 것처럼 설명하지 마세요.

## 원본을 이미 내려받았다면

네트워크 다운로드 대신 깨끗한 원본 체크아웃 또는 공식 tar.gz를 사용할 수 있습니다. 이 경우에도 파일·실행 권한·symlink를 포함한 전체 Git tree를 검증합니다.

```bash
python3 scripts/manage.py prepare --source /경로/urstory-rag
# 또는
python3 scripts/manage.py prepare --archive /경로/urstory-rag-75661c6.tar.gz
```

원본은 위의 고정 커밋이어야 합니다. 변경된 소스·다른 버전·파일이 빠진 소스는 거절합니다. 기존 `upstream/`이 변경되어 있으면 자동 삭제·초기화하지 않습니다. 원본 폴더 안에서 `npm install`, 파일 수정 등의 작업을 하면 검증에 걸릴 수 있으므로 개발 변경은 별도 작업 사본에서 진행하세요.

```bash
python3 scripts/manage.py verify
```

검증 결과와 파일별 해시는 `.local/upstream-manifest.json`에 기록됩니다. 실행 후 사용한 컨테이너 이미지 정보는 `.local/runtime-images.json`에 기록됩니다. 원본의 Python 의존성은 범위 지정이 포함되어 있고 일부 이미지 태그는 가변이므로 **소스 고정과 의존성의 바이트 단위 재현성은 구분**해야 합니다. 이미지 버전은 `.env`에서 검토·변경할 수 있습니다. 특정 버전의 현재 취약점 부재나 운영 적합성은 이번에 인증하지 않았습니다.

## 검증

설치 도구 자체의 로컬 테스트:

```bash
python3 -m unittest discover -s tests -v
```

실제 전체 스택 기동 후, 로그인·API·화면의 API 연결을 검사합니다. 자료를 업로드·삭제하거나 AI 요청을 보내지 않습니다.

```bash
python3 scripts/smoke.py
```

실제 RAG 호출까지 확인하려면 기존 테스트 문서에 대한 질문을 명시합니다. 원본 설정의 쿼리 확장·임베딩·생성 등으로 외부 API 비용이 발생할 수 있습니다.

```bash
python3 scripts/smoke.py --query "테스트 문서에서 확인할 질문"
```

원본 백엔드 테스트를 별도의 테스트 컨테이너에서 실행하는 명령도 포함했습니다. 실제 모델 키를 전달하지 않고 테스트 컨테이너의 네트워크를 차단합니다. 네트워크·실제 DB 등이 필요한 테스트는 별도 환경이 필요할 수 있습니다.

```bash
python3 scripts/test_upstream.py
```

원본 프론트 테스트·브라우저 E2E는 원본 저장소의 `frontend/` 테스트 안내에 따라 수행해야 합니다. 이 전달본에 이전 경량판 화면을 원본 전체판의 실행 증거로 사용하지 않았습니다.

## 보안·데이터 주의

이 구성은 원본과 동일하게 기본 LLM·임베딩 경로가 OpenAI API입니다. **자가 호스팅한다고 자료가 모두 로컬에서 처리되는 것은 아닙니다.** 회사 자료를 업로드하기 전 외부 API 전송 허용 범위를 확인하세요. 지금 전달본에는 실제 회사 엑셀·자료·사용자 API 키를 넣지 않았습니다.

원본 자체에 있는 설정 연결·캐시·문서 삭제·호환 API 등의 문제를 이 설치 패키지에서 모두 수정한 것은 아닙니다. 원본과 같은 코드를 쓴다는 사실을 보안 감사 완료·운영 승인·완전한 다중 사용자 자료 격리로 해석하지 마세요. 상세 범위는 `docs/STATUS.md`와 `docs/PARITY.md`를 확인하세요.

## 파일 위치

```text
code_management/
├── README.md
├── AGENTS.md
├── upstream.lock.json
├── compose.yaml
├── .env.example
├── start.command / start.sh
├── scripts/          # 전체 원본 수집·검증·실행·실제 HTTP 검사
├── deploy/           # 컨테이너 빌드·독립 DB/모니터링 구성
├── tests/            # 설치 도구의 테스트 (원본 RAG 테스트 아님)
├── docs/             # 완료/미완료 구분 및 실제 검증 결과
├── catalog_legacy/   # 이전 경량 앱. 원본 전체 앱과 별개
└── upstream/         # prepare 성공 후 생성되는 원본 저장소 전체
```
