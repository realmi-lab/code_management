# UI 디자인 기준

적용일: 2026-09-17. 대상: Docker Local `/shared/code_management`.

## 참고한 Taste Skill

- 저장소: https://github.com/Leonxlnx/taste-skill
- 확인한 커밋: `e79ca9ec7e071eb3a3b623c4fb752e853fc3ed58`.
- 적용 지침: `skills/redesign-skill/SKILL.md` (`redesign-existing-projects`), `skills/minimalist-skill/SKILL.md` (`minimalist-ui`).
- 원문을 읽고 이번 화면 작업에 적용했다. 사용자 전역 설정이나 스킬 설치 경로를 변경하지 않았다.
- 기본 v2 지침은 랜딩 페이지 중심이다. 이 앱은 기획자용 코드 카탈로그이므로 기존 화면 개선과 미니멀한 업무 화면 지침을 선택했다.

## 적용한 디자인 설정

```text
DESIGN_VARIANCE: 8
MOTION_INTENSITY: 6
VISUAL_DENSITY: 4
```

사용자가 직접 지정한 값이다. 이 값은 디자인 지침이며, 아래 실제 화면 규칙으로 반영한다.

- 디자인 변화8: 데스크톱 검색 입력과 옵션을 넓이가 다른 두 영역으로 배치. 첫 결과는 코드·메시지 영역으로 나누어 전체 폭에 표시하고, 나머지 결과는2열. DOM 순서와 검색 순위는 유지.
- 모션6: 페이지 요소 등장440–580ms, 검색 결과 순차 등장(최대 지연220ms), 상세창320ms, 버튼·카드의 hover/active 반응. transform/opacity 중심, 스크롤 강제 이동 없음.
- 정보 밀도4: 데스크톱 내부 여백28px, 영역 간격22–28px로 정리. 본문 글자를 줄이거나 원문을 생략하지 않음.
- 1000px 미만 화면에서는 검색·결과를1열로 유지. 시스템의 동작 줄이기 설정에서는 애니메이션과 hover 이동을 중지.

## 기존 화면에서 개선한 점

- 보라색 강조와 여러 회색 계열을 중립색·차콜·절제된 녹색으로 통일.
- 옅은 보조 문구의 대비, 검색 입력과 결과의 시각적 구분, 표의 행 간격 정리.
- 문자 기호로 섞여 있던 아이콘을 Phosphor Regular로 통일.
- 카드·입력·버튼·상세의 간격과 모서리를 일관된 규칙으로 정돈.
- 화면 폭 제한, 모바일 탐색·입력, 키보드 포커스, 로딩 상태 다듬기.

## 사용자 요구 우선

- 본문·입력·메뉴·버튼·보조 문구 기본14px. 제목만 위계에 따라 확대.
- `[나가기]`, `[확인]` 등은 원문 그대로 표시. 별도 버튼 변환 없음.
- 기존의 간결한 문구와 접힌 보조 설명 유지. 홍보용 문구·장식 사진·가상 지표 추가 없음.
- 데이터, 인증, 모델/Low 설정, 저장·승인·가져오기·내보내기 동작 유지.
- 기존 HTML/JavaScript/CSS 사용. 프레임워크 전환이나 런타임 패키지 추가 없음.
- 사용자 지정 모션6에 맞춰 등장·전환·반응 효과 적용. reduced-motion 지원.

## 자체 제공 자산

- Pretendard Variable1.3.9: 한글 UI의 일관된 글자 표시. SIL OFL 라이선스 동봉.
- Phosphor Icons Core2.1.1: 필요한 아이콘만 SVG 스프라이트로 포함. MIT 라이선스 동봉.
- 자산은 `static/assets/`에서 직접 제공하며 브라우저의 외부 CDN 요청이 필요 없다.
- 정확한 출처와 버전은 `static/assets/provenance.json`에 기록.

검증 결과는 `TEST_REPORT.md` 최신 항목 참고.


## 2차 Taste Skill v2 정제 — 2026-09-17

기준 저장소: `https://github.com/Leonxlnx/taste-skill` main `e79ca9ec7e071eb3a3b623c4fb752e853fc3ed58`.

- 기존 정보구조, 네비게이션명, 폼 이름, 업무 흐름과 원문 표시 규칙은 유지했다.
- `DESIGN_VARIANCE: 8 / MOTION_INTENSITY: 6 / VISUAL_DENSITY: 4`를 유지했다.
- 색상은 forest 단일 accent와 off-white/off-black 계열로 재정리했다.
- 반경을 control 8px / surface 14px / dialog 18px의 세 단계로 통일했다. pill은 상태 tag와 결과 mode처럼 의미가 있는 작은 라벨에만 쓴다.
- 검색 영역을 가장 중요한 workbench로 올렸다. 넓은 입력면과 별도 action rail, 얇은 accent rail, 절제된 shadow로 계층을 분리했다.
- 검색 결과 첫 항목만 dark forest identity pane을 가진 featured 결과로 강조하고, 후속 결과는 기존 2열 카드 구조를 유지한다. 반복 카드에 불필요한 elevation을 추가하지 않았다.
- 버튼, 입력, 표, dialog, sidebar active state를 같은 토큰으로 정리했다. 기본 본문·메시지 글자는 14px를 유지한다.
- 기존 transform/opacity 기반 motion과 `prefers-reduced-motion` 경로를 그대로 보존했다.
- `[나가기]`, `[확인]` 같은 대괄호 표시는 원문이며 별도 버튼 UI로 변환하지 않는다.

검증: `scripts/photo_ui_check.py` 12/12 통과, `pytest` 151개 통과. 사진 테스트 데이터나 운영 카탈로그는 수정하지 않았다.
