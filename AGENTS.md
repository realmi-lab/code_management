# 작업 지침

먼저 README.md, docs/ARCHITECTURE.md, docs/TEST_REPORT.md를 읽는다.

- 이 앱의 ‘코드’는 AT-1923 같은 알림 식별코드다. 개발 소스코드 분석으로 목적을 바꾸지 않는다.
- 실제 코드/엑셀 내용은 추측하거나 합성 예시와 섞지 않는다. demo/live 분리를 유지한다.
- 기존 코드번호와 원문은 DB에서 그대로 표시한다. 생성 모델로 재작성하지 않는다.
- 회사의 번호 규칙이 주어지지 않았으면 번호를 추측하지 않는다.
- 승인 없는 기존 원문 덮어쓰기, 자동 폐기/삭제, 실제 목록 초기화는 구현하지 않는다.
- 실제 API 키와 원본 파일/DB를 커밋하거나 로그에 출력하지 않는다.
- RRF 모듈을 수정하면 원본 출처, MIT 고지, provenance.json을 유지한다.
- UI는 한국어 기획자 업무 용어를 사용한다. 내부 검색 점수를 정답 확률처럼 표시하지 않는다.
- 모델 미연결 시 기본 검색임을 표시한다. 모델 연결 테스트는 실제/모의 응답을 구분해 보고한다.
- 변경 후 `python -m pytest`, `node --check static/app.js`, `python scripts/verify_vendor.py`를 실행한다.
- 브라우저 검사에서 offline harness 사용 여부를 TEST_REPORT에 밝힌다. 배포 검증으로 과장하지 않는다.
- 2026-09-17 Docker Local `/shared/code_management`에서 Command Code DeepSeek V4.1 Flash / Low 연결을 검증했다. `docs/COMMAND_CODE_CONNECTION.md`를 읽고 현재 실행 상태를 다시 확인한다. 다른 프로젝트는 수정하지 않는다.
