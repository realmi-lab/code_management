# 로컬 구현·검증 — 2026-09-21

실행 경로: `/Users/apple/Documents/ChatGPT/code_management`.

## 변경

- 공식 고정 커밋 `75661c676aec650e52f75dd068b687a4cb6a63b7`의 전체 384개 파일을 `upstream/`에 확보. Git tree `6e5ebcef24cfc575f5659329d946cc56c103c9ca` 및 모드를 검증.
- Mac Python 인증서 문제를 OS 신뢰 저장소 추가로 해결. TLS 인증서·호스트 검증을 끄지 않음.
- 원본 LLM 호출을 Command Code 공식 Provider API의 DeepSeek V4.1 Flash / high로 선택하는 연동 구현. 원본 파일 변경은 빌드 사본의 정확한 문자열 계약·SHA-256 기록을 통해 수행.
- 대화/초안, 원본 검색의 LLM 단계, 문서 문맥 청킹과 평가 judge에 동일 모델 적용. 설정 화면에 유효 모델을 표시. 임베딩은 기존 경로 유지.
- 키는 로컬 `.env` 0600에 보관. Git 및 Docker 컨텍스트 제외 규칙 추가.
- 기존 9월 18일 검사 증거를 덮어쓰지 않도록 검사 출력 경로를 지정할 수 있게 수정.

## 결과

| 검사 | 결과 | 범위 |
|---|---|---|
| 원본 전체 검증 | PASS, 384개 파일 | `manage.py verify` |
| 도메인/API/연동/패치 | PASS, 90개 | SQLite 및 검색/LLM 대역. 추가 6개는 provider 계약과 실제 고정 소스 패치 검사 |
| 설치 unittest | PASS, 58개 | 설치 도구 회귀 |
| native HTTP | PASS, 10개 | 실제 loopback HTTP, 인증·검색·LLM은 대역 |
| 실제 Chrome HTTP UI | PASS, 12개, JS 오류 0 | 실제 HTTP·DOM·iframe, 원본 JWT·LLM은 대역 |
| 오프라인 브리지 UI | PASS, 14개 | 별도 검사, 실제 Next/JWT E2E 아님 |
| Python/JS 구문 | PASS | Python AST, node --check |
| 전체 원본 Next + 확장 Docker 빌드 | PASS | 실제 Next 컴파일·TypeScript 검사 포함 |
| 전체 원본 백엔드 + 확장 Docker 빌드 | PASS | 원본 전체 의존성 및 기존·provider 패치 포함 |
| Command Code live | PASS | 패치한 원본 LLM 모듈, 실제 API, 합성 요청, V4.1 Flash / high |
| 빌드된 백엔드 컨테이너 LLM | PASS | 실제 이미지의 원본 LLM import와 Command Code 합성 응답. 전체 앱 기동과 구분 |

증거: `verification/local-2026-09-21/`의 로그·JUnit·JSON·화면 이미지. `commandcode-live.json`은 호스트에서 실행한 실제 호출 결과, `commandcode-container-live.json`은 빌드된 백엔드 이미지에서 실행한 실제 호출 결과다. 로컬 API/UI 대역 검사와 실제 모델 API 검사는 서로 다른 검사다.

## 남은 범위

임베딩용 `OPENAI_API_KEY`는 미설정이며 전체 RAG 서비스를 기동하지 않았다. 실제 PostgreSQL/Nori/Redis/Celery/Langfuse 동시 기동, 원본 JWT/Next 프록시 E2E, 임베딩·리랭커·검색·RAGAS 품질은 아직 검증하지 않았다. 회사 데이터는 사용하지 않았다. 생성된 Docker 이미지는 로컬 빌드 산출물이며 운영 배포 완료가 아니다.

공식 연동 명세: [Command Code Provider API](https://commandcode.ai/docs/provider).
