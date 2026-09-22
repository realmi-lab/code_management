# 현재 전달 상태 — 통합 확장판

최종 마감: 추가 속도 조정은 하지 않았습니다. 최종 후속 8문항은 자동 7/8·의미 검토 6/8입니다. 수치 정정 문장 차단과 일부 검색 후보를 전체 카탈로그로 단정하는 두 문제는 남아 있으며 [최신 보고서](CATALOG_SKILLS_2026-09-22.md)에 증거와 다음 작업을 기록했습니다.

2026-09-22 최신 검색 상태: 원본 검색 청크와 후보를 리랭커에 그대로 전달하는 어댑터를 API·worker·beat에 배포했습니다. 실행 파일 53개가 작업 트리와 일치하고 원본 384개 파일·모드는 보존됐습니다. 메타데이터 검색 5건 모두 정답 1위, 후보 집합 동일. pytest 508·unittest 83·대역 native HTTP 10 통과. 사용자 요청으로 추가 속도 조정은 중단하고 현재 설정을 유지합니다. [최신 평가와 제한](CATALOG_SKILLS_2026-09-22.md)을 아래 과거 기록보다 우선합니다.

기준일: 2026-09-22

**최신 상태(16시 이후): 사용자 지시로 대화·판정을 기존 Command Code DeepSeek Flash로 복귀했다. Apple 실측은 24회 중 유효 답변 2회/입력 초과 22회여서 추가 튜닝을 중단했다. 검색 후보를 Apple에 맞춰 줄이지 않는다. 검색 결과와 AI 오류를 분리하고, 30초 수치 전체 목록 42건을 페이지로 확인할 수 있다. 실제 브라우저의 DeepSeek 답변 및 42/42건 표시 확인. pytest 311·unittest 77·native HTTP 10 통과. 아래 과거 시점 수치보다 [최신 검토](APPLE_USABILITY_REVIEW_2026-09-22.md)를 우선한다.**

**원본 RAG 연동과 기획자 대화형 코드 관리의 실제 소스를 작성했고, 이 Mac의 Docker에서 전체 스택(원본 API·worker·beat·Next 프론트·PostgreSQL/pgvector·Elasticsearch·Redis·로컬 E5 임베딩·Langfuse)이 기동 중이다. API 컨테이너의 확장 코드는 작업 트리와 sha256이 일치한다. 실제 회사 목록은 아직 비어 있어 production 스코프 종단간 검증은 미수행이다.**

| 항목 | 구현·검증 상태 |
|---|---|
| 원본 FastAPI 안의 코드 관리 API | 구현. 확장/API 검사 256개 통과(대역 인증·모델) |
| 원본 JWT/계정 연결 | 원본 get_current_user 사용. 현재 배포는 `CODE_AUTH_MODE=local`(무로그인)이며 JWT 라이브 검증은 미수행 |
| 원본 Next.js의 /codes | 페이지·사이드바 패치 구현. 전체 Next/TypeScript Docker 빌드 통과, 프론트 서비스 기동 중 |
| 대화 검색→비교→신규 초안 | 구현. demo 목록(합성 279건)에서 실제 DeepSeek Flash(low)로 검색·설명·검증 통과. 실측 한 턴 28~42초(2026-09-22, 판정 모델 추론 토큰이 지배). 같은 날 오후 재계측은 12.4~31.9초(중앙값 18.2). 판정 두 단계만 다른 모델로 바꾸는 `CODE_LLM_JUDGE_MODEL`/`CODE_LLM_JUDGE_REASONING_EFFORT` 옵션을 추가했으며 기본값은 기존 동작(미설정) |
| 판정 단계 모델 옵션 | `.env`의 `CODE_LLM_JUDGE_MODEL`·`_REASONING_EFFORT`·`_PROVIDER=apple`(Apple 온디바이스 브리지) 구현. 화면에는 판정 칸을 두지 않고 대화 AI가 검증도 맡는다(사용자 결정, 2026-09-22). Apple 판정은 문장 분해 방식으로 재작성해 호스트 하네스에서 정답 통과·오답 차단 확인, 실제 턴 2차 실측은 미수행 |
| 원본 하이브리드 검색 연결 | 실제 PGVector + Nori + RRF + 리랭커 연결. 리랭킹 범위 축소 후 검색 2.0~3.1초 |
| PGVector/Nori 카탈로그 인덱싱 | demo 목록 인덱스 준비 완료(`index_ready: true`). production 목록은 0건 |
| 엑셀/CSV 입력·원문·충돌 처리 | 실제 파서·API·DB 검사 통과. 실제 회사 엑셀은 제공받지 않음 |
| 관리자 등록·감사 | 실제 로직·API·대화 복원 검사 통과. `CODE_CATALOG_AUTHORITY` 기본값은 `system`(compose·.env), 엑셀 확인 절차는 `excel`로 전환 |
| 기존 설치 결함과 원본 연결 결함 | 패치 작성, 회귀 검사 통과. 원본 전체 버그를 고친 것은 아님 |
| 최신 통합/연동 테스트 | 274개 통과 (2026-09-22, Apple 판정 전송 11개 포함) |
| 설치 테스트 | 77개 통과 (2026-09-22, Apple 브리지 HTTP 검사 5개 포함) |
| 실제 localhost HTTP 테스트 | 10개 검사 통과. 인증·모델은 대역 |
| Chromium UI 테스트 | Mac에서 Playwright Chromium으로 재실행: 오프라인 14 · loopback HTTP 14 · 세션 복원 10개 통과 (2026-09-22) |
| 원본 테스트 (`scripts/test_upstream.py`) | 일회성 PostgreSQL(pgvector)을 내부 네트워크에 띄워 실행: 611 통과 · 27 실패 · 5 건너뜀. 실패는 외부 서비스 부재(Redis/ES/네트워크)와 패치로 달라진 응답 형식(health의 openai 항목, Claude 응답 처리, 설정 응답, 인증 429)이며 원본 계약 384개 파일은 유지 |
| 원본 전체 소스 | 패키지에는 미포함. 설치 시 공식 고정 버전 수집·무결성 검사 |
| 실제 Docker/원본 전체/AI 모델 기동 | 이 Mac에서 전체 스택 기동 중. Command Code 경유 DeepSeek Flash·로컬 E5 실호출 확인 |
| production 스코프 종단간(등록→색인→검색→초안→승인) | 미수행. 실제 목록이 비어 있고 합성 데이터를 production에 넣지 않는 원칙 때문 |

이전 설치본 기록은 docs/history/installer-only/에 보존했다. catalog_legacy/의 코드/문서/과거 스크린샷을 이번 통합판의 실행 결과로 사용하지 않았다. 최신 증거는 docs/verification/ 및 TEST_REPORT.md를 따른다.


## 2026-09-22 최종 범위: Apple 연결만 유지

사용자의 “그냥 연결만” 요청에 따라 Apple 전용 검색 관련성 필터, 상위 1건 입력 제한, 고정 답변 대체, 대화 프롬프트 재작성을 제거했다. 기존 검색·프롬프트·검증 흐름을 유지하고 대화 공급자와 답변 검증 공급자를 `apple/on-device`로 연결했다. multilingual-e5-base(768→1536 패딩), PGVector, Nori, RRF, 상위 12건 리랭킹은 변경하지 않았다.

API·worker·beat 재배포 완료. 컨테이너 내 연결 관련 파일 8개의 해시가 작업 트리와 일치한다. 배포된 `RoutingLLM`을 통한 실제 Apple 응답 “안녕하세요! 어떻게 도와드릴까요?”를 확인했다. 확장/API 검사 294개, 설치 unittest 77개, 대역 기반 native HTTP 10개 및 JS 구문 검사 통과. 이는 연결 검증이며 긴 카탈로그 프롬프트의 답변 품질·성공률 검증을 뜻하지 않는다. 이전 `apple-chat-*` 실험 결과는 최종 구현의 품질 수치로 사용하지 않는다. 관련 로그는 `docs/verification/judge-switch-2026-09-22/*connection-only*`에 있다. 커밋하지 않았다.
