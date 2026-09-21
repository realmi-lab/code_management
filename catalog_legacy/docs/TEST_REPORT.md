# 구현 검증 기록

작성일: 2026-09-17

## 전달 및 배포 상태

이 프로젝트는 별도 작업 컨테이너의 `code_management` 폴더에서 구현했습니다. 사용자 Docker Local 호출은 `FORBIDDEN: This conversation does not support developer MCPs`로 실패했습니다. **사용자 Docker Local의 폴더 생성·설치·실행은 수행하지 못했습니다.** 사용자 기존 앱이나 저장소를 수정하지 않았습니다.

`urstory-rag` 전체를 배포한 버전이 아닙니다. 고정 커밋 `75661c676aec650e52f75dd068b687a4cb6a63b7`의 RRFCombiner를 재사용한 독립 애플리케이션이며, 사용 범위는 `UPSTREAM.md`에 명시했습니다.

## 실제 수행 결과

| 검증 | 결과 | 범위 |
|---|---|---|
| 백엔드 자동 테스트 | **65개 통과** | API, 엑셀·CSV 입력, 원문 보존, 코드 조회, 비교, 초안·승인, 권한, 동시성, 모의 AI 응답 |
| 실행 코드 줄 커버리지 | **93.38%** | `catalog`와 `vendor.urstory_rag` 931/997문; 프론트엔드 및 Docker 제외 |
| Chromium UI 검사 | **14개 흐름 통과** | 오프라인 자산 로드 + 실제 FastAPI TestClient API 연결 |
| 브라우저 JavaScript 오류 | **0개** | 위 UI 검사에서 수집한 오류 |
| 실행·키·백업 검사 | **6개 통과** | Python 네이티브 서버의 실제 로컬 HTTP, 키 생성·미덮어쓰기, 인증, 백업 일관성 |
| 프론트엔드 구문 검사 | 통과 | `node --check static/app.js` |
| 재사용 소스 무결성 | 통과 | `scripts/verify_vendor.py` 로컬 SHA-256 확인 |
| Compose/Dockerfile | 정적 점검만 수행 | YAML 구문·포트·볼륨·권한 구성 확인. Docker 엔진 없음 |
| 엑셀 양식 | 생성·내용 검사·미리보기 확인 | 빈 `.xlsx` 양식, 숫자형이 아닌 코드번호, 안내 시트 |

실행 환경은 Python 3.13.5이며 실제 회사 자료가 아닌 합성 데이터로 검사했습니다. 커버리지는 업무 정확도나 보안 완전성을 의미하지 않습니다.

## 자동 테스트가 확인한 중요한 동작

- 실제 목록과 예시 목록을 분리하고 실제 목록은 초기 빈 상태로 둡니다.
- 정확한 코드 조회 시 원문·공백·줄바꿈·변수를 유지합니다. 없는 코드를 만들어 반환하지 않습니다.
- 상황 검색은 재사용 확정이 아니라 관련 후보를 표시합니다.
- 문구 비교는 수치·단위, `이후/이내`, 일부 부정 표현, 자리표시자 차이를 표시합니다. 모든 의미를 판별하지는 않습니다.
- XLSX 헤더 연결·셀 위치·파일 해시를 보존하고 수식·위험한 XML을 거절합니다.
- 업로드는 미리보기와 확정으로 분리합니다. 같은 번호의 원문이 다르면 항목별 선택과 사유 없이 갱신하지 않습니다.
- 목록 버전이 바뀌면 가져오기 및 승인에서 재검토를 요구합니다. 같은 요청·번호를 중복 등록하지 않습니다.
- 초안에는 정식 번호가 없고, 엑셀 공식 목록 모드에서는 앱이 번호를 발급하지 않습니다.
- 시스템 공식 목록 모드의 승인·번호 발급·변경 이력을 별도 검증합니다.
- 기본 설정에서 AI 데이터 전송은 없습니다. 모델 응답 계약 검사는 모의 서버·응답으로만 수행했습니다.

## 브라우저 검사의 정확한 범위

환경 정책으로 Chromium이 `http://127.0.0.1`에 직접 이동하는 요청은 `ERR_BLOCKED_BY_ADMINISTRATOR`로 거절되었습니다. 정책을 변경하거나 비활성화하지 않았습니다.

대신 직접 생성한 로컬 HTML/CSS/JS를 Chromium에 로드하고, fetch를 실제 FastAPI TestClient에 연결하여 클릭·입력·파일 선택·DOM 표시를 검증했습니다. sessionStorage와 clipboard에는 테스트용 대체 구현을 사용했습니다. 따라서 이 결과는 **실제 브라우저 UI 검사이지만 직접 HTTP E2E 검증은 아닙니다.** 브라우저의 CSP·네이티브 클립보드 권한·실제 네트워크 전달은 검증하지 않았습니다.

별도의 Python 네이티브 서버 검사에서는 실제 loopback HTTP로 health, 접속 키 검증과 정적 파일 제공을 확인했습니다. 이것은 브라우저의 정책·권한 검증을 대신하지 않습니다.

UI 검사는 접속, 코드 조회, 원문 복사 내용, 상세/출처, 상황 검색, 조건 비교, 초안, 데모 승인, 파일 가져오기, 안전한 렌더링, 내보내기, 명시적 원문 갱신, 기획서 줄별 검토, 양식 다운로드, 390px 모바일 표시를 포함합니다. 일부 항목은 하나의 흐름으로 묶여 총14개입니다.

`desktop-preview.png`와 `mobile-preview.png`는 이 실제 렌더링 결과입니다. 모바일 화면의17개 예시는 테스트 중 추가한 데모 초안1개를 포함한 수치이며 배포본의 초기 예시는16개입니다. 사용자 데이터는 아닙니다.

## 아직 검증하지 않은 것

1. 사용자 Docker Local의 파일 생성, Docker 이미지 빌드, 컨테이너 실행 및 접근.
2. 실제 회사 엑셀의 모든 양식·규모와 업무별 검색 정확도.
3. 실제 임베딩·채팅 모델 연결, 품질, 비용, 응답 시간.
4. SSO·사용자별 권한·부서별 자료 접근 격리·승인자별 감사. 현재는 로컬 공유 접속 키 방식입니다.
5. 자유형 기획서 전체 해석, 개발 소스코드의 실제 사용처 추적, 엑셀 등록 후 이전 초안의 자동 완료 처리.
6. 고부하, 다중 서버 배포, 장기 운영 및 전체 보안 감사.

## 재현 명령

```bash
pip install -r requirements-dev.txt
python -m pytest --junitxml=docs/test-results.xml --cov=catalog --cov=vendor.urstory_rag --cov-report=json:docs/coverage.json
node --check static/app.js
python scripts/verify_vendor.py
python scripts/smoke_test.py
```

브라우저 검사에는 Playwright와 Chromium이 필요합니다. 자동 설치는 하지 않습니다.

```bash
# 별도 임시 DB와 인프로세스 API를 사용하는 UI 검사
CM_BROWSER_OFFLINE=true CHROMIUM_PATH=/usr/bin/chromium python scripts/browser_test.py

# 직접 HTTP 방식: 운영 데이터가 없는 별도의 테스트 서버에만 실행하세요.
# 이 방식은 제공 환경에서 브라우저 정책상 실행하지 못했습니다.
CM_TEST_URL=http://127.0.0.1:8766 CM_TEST_TOKEN=테스트서버의키 CHROMIUM_PATH=/usr/bin/chromium python scripts/browser_test.py
```

기계 판독 결과는 `test-results.xml`, `coverage.json`, `browser-test-results.json`, `launcher-smoke-results.json`에 보관합니다.
