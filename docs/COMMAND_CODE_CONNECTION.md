# Command Code 연결 검증

날짜: 2026-09-17. 대상: `/shared/code_management`.

## 후속 업데이트

문구 다듬기 외에 질문만 전달하는 AI 상황 검색을 추가했습니다. 최신 검증은 `CURRENT_STATUS.md` 및 `TEST_REPORT.md` 최상단이 기준입니다. 전용 Supervisor로 실행하며 앱 비정상 종료 시 다시 시작합니다. Docker Local 재부팅 시 전용 Supervisor 시작은 별도입니다. 아래 연결 기록은 최초 연결 시점의 결과입니다.

## 적용

- 공급 경로: 이미 로그인된 Command Code CLI 1.54.0.
- 모델: `deepseek/deepseek-v4.1-flash`, 추론 설정: `low`.
- 기능: 새 문구/변경 초안의 선택형 AI 문구 다듬기.
- 임베딩 미연결. 검색/비교는 기존 기본 검색과 규칙 검사를 유지한다.
- 앱은 Docker Local 안의 Python 환경에서 `127.0.0.1:8766`으로 실행했다.
  별도 공개 라우트는 추가하지 않았다. 재시작은 `.venv/bin/python run.py`.
- 호출은 1회·1턴이며 도구를 비활성화한다. 원문은 표준입력으로 보내고 세션/원시 출력을 저장하지 않는다.
- 타임아웃 90초, 출력 크기 제한, 실패 시 원문 보존. CLI가 보고한 모델/effort 불일치는 거절한다.
- 설정은 개인 `.env`에서 읽는다. 기존 Command Code 인증 파일을 복사하지 않았다.

## 확인 결과

- 자동 테스트 73개 통과 (기존 65 + 연결 관련 8).
- `node --check static/app.js` 통과.
- `python scripts/verify_vendor.py` 통과.
- 실제 모델 호출: 합성 문구 `30초 이후에 인증해주세요.` → `30초 후에 인증해 주세요.`.
- 실제 응답 실행 정보: model=`deepseek/deepseek-v4.1-flash`, effort=`low`.
- 실제 호출 소요 시간 약 3.67초. 회사 자료로 품질을 평가한 결과는 아니다.
- 실행 중 앱: health 200, 인증 없는 meta 401, 인증된 meta에서 모델/Low와 chat_enabled=true 확인.
- 운영 실제 목록은 비어 있고 테스트 문구를 운영 목록에 등록하지 않았다.
- 이번 변경에서 브라우저 UI 검사를 새로 실행하지 않았다. 기존 offline harness 기록과 구분한다.
- CLI 인증은 해당 실행 사용자 환경에 의존한다. 별도 Compose 이미지에는 CLI와 로그인 환경이 없으므로
  Python 실행 방식을 사용한다. 컨테이너 재시작 후 자동 서비스 등록은 이번 범위에 포함하지 않았다.

## 변경 파일

`catalog/command_code.py`, `catalog/command-code-inference.mjs`, `catalog/config.py`,
`catalog/ai.py`, `catalog/main.py`, `static/app.js`, `tests/test_command_code.py`,
`.env.example`, 개인 `.env`, `README.md`, `AGENTS.md`, 이 문서와 검증 기록.

다른 폴더의 구현과 인증은 읽어서 재사용했으며 해당 파일을 수정하지 않았다.
