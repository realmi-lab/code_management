# CLAUDE.md

이 저장소에서 작업하는 Claude를 위한 안내입니다. **규칙의 원본은 [AGENTS.md](AGENTS.md)** 이며, 이 파일과 충돌하면 AGENTS.md가 우선합니다. 작업 전 README.md → docs/INTEGRATION.md → docs/TEST_REPORT.md 순서로 읽습니다.

## 프로젝트 한 줄 요약

UrstoryRAG(`urstory/urstory-rag`) 원본 위에 **알림 식별코드(예: `AT-1923`)와 등록 문구를 검색·비교·초안 작성하는 기획자용 작업실**을 확장으로 얹은 통합판입니다. '코드'는 알림 문구 식별번호이며, **소스코드 분석 도구가 아닙니다.**

## 절대 금지 (사용자 확정)

- `UrstoryRAG / 관리자 콘솔에 로그인하세요` 화면·메뉴·진입 링크를 **복원하거나 다시 노출하지 않는다.** 문구만 바꿔 되살리는 것도 금지.
- 로그인 없이 `http://localhost:3500/codes`로 바로 들어가는 흐름(`CODE_AUTH_MODE=local`)을 유지한다. 인증 모드를 임의로 `jwt`로 바꾸지 않는다.
- upstream에 로그인 소스가 남아 있다는 이유로 위 메뉴를 활성화하지 않는다. 사용자가 명시적으로 철회하기 전까지 유효.

## 핵심 원칙

- **원본 보존**: `upstream/`은 직접 수정하지 않는다. 확장은 `extensions/`, 원본 변경은 `deploy/patch_*`로 추적한다. 고정 소스 계약이 달라지면 빌드를 중단한다.
- **고정 버전**: 원본은 `upstream.lock.json`(commit `75661c67…`)으로 고정. 검증 전 다운로드 파일을 신뢰하지 않는다.
- **경량 대체 금지**: 원본 기능·의존성·화면을 작은 대체물로 바꾸지 않는다. RRF 하나만 가져와 전체 RAG라고 말하지 않는다.
- **원문 우선**: 번호·문구는 DB 원문을 그대로 출력한다. AI가 번호나 기존 원문을 만들어내지 않는다.
- **정식 등록**: 관리자 명시적 승인 엔드포인트로만 한다. 최신 버전·중복 확인·사유·사용자 ID를 검사한다. 대화의 "등록해"만으로 등록하지 않는다.
- **actor**: 모든 요청의 사용자는 원본 `get_current_user`에서 얻는다. body의 사용자 ID/role을 믿지 않는다.
- **데이터 분리**: 회사 데이터와 합성 샘플(`extensions/code_agent/data/sample_catalog_300.json`)을 섞지 않는다. production 초기 목록은 비어 있어야 한다.
- **정직한 실패**: 인덱스 미준비/실패를 의미 검색 성공처럼 보이게 하지 않는다. 실패 시 규칙 검색으로 몰래 대체하지 않는다.
- **비밀 정보**: `.env`, API 키, 토큰, 운영 DB, 회사 엑셀, 모델 파일을 Git/ZIP에 넣지 않는다.
- **테스트 대역**: `integration_tests/`의 모의 LLM·오프라인 브리지는 검사 전용. 운영 fallback으로 쓰지 않는다.

## 디렉터리

| 경로 | 내용 |
|---|---|
| `extensions/code_agent/` | 원본 FastAPI에 로드되는 카탈로그 API·대화 에이전트·검색 어댑터(`gateway.py`)·인덱서·AI 설정 |
| `extensions/frontend/` | 원본 Next.js에 추가하는 `/codes` 페이지 |
| `deploy/` | Dockerfile, `patch_*.py` / `patch_*.mjs` (원본 빌드 사본에만 적용) |
| `scripts/` | `manage.py`(실행 관리), `smoke.py`, `test_upstream.py` 등 |
| `integration_tests/` | 도메인·API·연동 계약·브라우저·HTTP 검사 |
| `tests/` | 설치 도구·패치 회귀 검사 |
| `docs/` | INTEGRATION, TEST_REPORT, AI_SETTINGS, FUNCTIONAL_PARITY, verification/ 등 |
| `upstream/` | 내려받은 원본 전체 (수정 금지) |
| `catalog_legacy/`, `docs/history/` | 이전 버전 보존본. 현재 상태 근거로 쓰지 않음 |

## 자주 쓰는 명령

```bash
# 실행 관리
python3 scripts/manage.py start          # 원본 수집·검증 → 설치 → 마이그레이션 → 기동
python3 scripts/manage.py status | stop | doctor | verify | credentials
python3 scripts/manage.py configure

# 설치 도구 테스트
python3 -m unittest discover -s tests -v

# 통합 확장 테스트
source .test-venv/bin/activate
PYTHONPATH=extensions python -m pytest integration_tests -q
PYTHONPATH=extensions python integration_tests/native_http_check.py

# 전체 서비스 기동 후
python3 scripts/smoke.py
python3 scripts/test_upstream.py
```

⚠️ `docker compose down -v`는 데이터 볼륨을 삭제하므로 사용하지 않는다.

## 주요 설정 (compose.yaml / .env)

- `CODE_AUTH_MODE` — 기본 `local` (무로그인). 변경 금지.
- `CODE_CATALOG_AUTHORITY` — `excel` / `system`. (README는 `excel`을 기본으로 설명하지만 compose.yaml 기본값은 `system`이므로 변경 전 확인)
- `CODE_LLM_PROVIDER` — DeepSeek / Claude / OpenAI (Command Code 경유 DeepSeek 지원)
- `CODE_LLM_JUDGE_MODEL` / `CODE_LLM_JUDGE_REASONING_EFFORT` — 충실도·근거 판정 두 단계만 다른 모델·effort로 전환(선택, 기본 비어 있음 = 생성 모델이 판정). 생성 모델은 바뀌지 않는다.
- `CODE_LLM_JUDGE_PROVIDER` — `apple`이면 판정 두 단계만 이 Mac의 Apple Intelligence 온디바이스 브리지(`extensions/apple_bridge`, macOS 전용·선택)로 보낸다. 판정 선택은 이 env로만 하며 화면에는 판정 칸이 없다(대화 AI가 Apple이면 검증도 Apple). 브리지에 닿지 못하면 판정은 503으로 중단되며 생성 모델로 되돌아가지 않는다. Apple 판정은 근거를 한국어 표찰 문장으로 바꾸고 답변을 줄 단위로 나눠 원문 일치는 기계 비교, 자유 서술만 모델에 묻는다(`apple_judge.py`).
- `CODE_EMBEDDING_PROVIDER` — `none`(키워드) / 로컬 E5 / OpenAI. 임베딩은 필수가 아님.

## 결과 보고 시

- Python 도메인/API 검사, 설치 unittest, JS/TSX 구문, native HTTP, UI 검사를 각각 재실행하고 결과를 구분해 보고한다.
- TestClient·모의 LLM 검사를 실제 PGVector/Nori/JWT/모델/Next E2E 검증으로 표현하지 않는다.
- 실제 경로·권한을 확인하기 전에는 "배포했다"고 말하지 않는다.
- 현재 미검증: 직접 DeepSeek/Claude/OpenAI 키 실호출, 카탈로그 전체 검색·초안·승인 종단간 검증.
