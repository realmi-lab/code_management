# 현재 전달 상태 — 통합 확장판

기준일: 2026-09-22

**원본 RAG 연동과 기획자 대화형 코드 관리의 실제 소스를 작성했고, 이 Mac의 Docker에서 전체 스택(원본 API·worker·beat·Next 프론트·PostgreSQL/pgvector·Elasticsearch·Redis·로컬 E5 임베딩·Langfuse)이 기동 중이다. API 컨테이너의 확장 코드는 작업 트리와 sha256이 일치한다. 실제 회사 목록은 아직 비어 있어 production 스코프 종단간 검증은 미수행이다.**

| 항목 | 구현·검증 상태 |
|---|---|
| 원본 FastAPI 안의 코드 관리 API | 구현. 확장/API 검사 256개 통과(대역 인증·모델) |
| 원본 JWT/계정 연결 | 원본 get_current_user 사용. 현재 배포는 `CODE_AUTH_MODE=local`(무로그인)이며 JWT 라이브 검증은 미수행 |
| 원본 Next.js의 /codes | 페이지·사이드바 패치 구현. 전체 Next/TypeScript Docker 빌드 통과, 프론트 서비스 기동 중 |
| 대화 검색→비교→신규 초안 | 구현. demo 목록(합성 279건)에서 실제 DeepSeek Flash(low)로 검색·설명·검증 통과. 실측 한 턴 28~42초(2026-09-22, 판정 모델 추론 토큰이 지배). 판정 두 단계만 다른 모델로 바꾸는 `CODE_LLM_JUDGE_MODEL`/`CODE_LLM_JUDGE_REASONING_EFFORT` 옵션을 추가했으며 기본값은 기존 동작(미설정) |
| 원본 하이브리드 검색 연결 | 실제 PGVector + Nori + RRF + 리랭커 연결. 리랭킹 범위 축소 후 검색 2.0~3.1초 |
| PGVector/Nori 카탈로그 인덱싱 | demo 목록 인덱스 준비 완료(`index_ready: true`). production 목록은 0건 |
| 엑셀/CSV 입력·원문·충돌 처리 | 실제 파서·API·DB 검사 통과. 실제 회사 엑셀은 제공받지 않음 |
| 관리자 등록·감사 | 실제 로직·API·대화 복원 검사 통과. `CODE_CATALOG_AUTHORITY` 기본값은 `system`(compose·.env), 엑셀 확인 절차는 `excel`로 전환 |
| 기존 설치 결함과 원본 연결 결함 | 패치 작성, 회귀 검사 통과. 원본 전체 버그를 고친 것은 아님 |
| 최신 통합/연동 테스트 | 256개 통과 (2026-09-22) |
| 설치 테스트 | 72개 통과 (2026-09-22) |
| 실제 localhost HTTP 테스트 | 10개 검사 통과. 인증·모델은 대역 |
| Chromium UI 테스트 | Mac에서 Playwright Chromium으로 재실행: 오프라인 14 · loopback HTTP 14 · 세션 복원 10개 통과 (2026-09-22) |
| 원본 테스트 (`scripts/test_upstream.py`) | 일회성 PostgreSQL(pgvector)을 내부 네트워크에 띄워 실행: 611 통과 · 27 실패 · 5 건너뜀. 실패는 외부 서비스 부재(Redis/ES/네트워크)와 패치로 달라진 응답 형식(health의 openai 항목, Claude 응답 처리, 설정 응답, 인증 429)이며 원본 계약 384개 파일은 유지 |
| 원본 전체 소스 | 패키지에는 미포함. 설치 시 공식 고정 버전 수집·무결성 검사 |
| 실제 Docker/원본 전체/AI 모델 기동 | 이 Mac에서 전체 스택 기동 중. Command Code 경유 DeepSeek Flash·로컬 E5 실호출 확인 |
| production 스코프 종단간(등록→색인→검색→초안→승인) | 미수행. 실제 목록이 비어 있고 합성 데이터를 production에 넣지 않는 원칙 때문 |

이전 설치본 기록은 docs/history/installer-only/에 보존했다. catalog_legacy/의 코드/문서/과거 스크린샷을 이번 통합판의 실행 결과로 사용하지 않았다. 최신 증거는 docs/verification/ 및 TEST_REPORT.md를 따른다.
