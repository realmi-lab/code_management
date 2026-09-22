# AI 공급자와 검색 방식 선택

**임베딩은 필수가 아닙니다.** 대화·문구 작성용 AI와 검색 방식을 별도로 선택할 수 있습니다. Claude API 키 하나만 사용한다면 **Claude + 임베딩 없이 키워드 검색**으로 시작할 수 있습니다. 표현이 달라도 비슷한 뜻의 알림을 찾으려면 별도 API 키 없이 **로컬 임베딩**을 추가할 수 있습니다.

## 화면에서 변경하기

1. `http://localhost:3500/codes`에서 **알림 코드 → AI 설정**을 엽니다. 기본 로컬 모드는 로그인이나 관리자 비밀번호가 필요 없습니다.
2. **DeepSeek / Claude / OpenAI**를 선택합니다. DeepSeek는 직접 API 또는 기존 Command Code 연결을 선택합니다.
3. 사용할 모델명을 확인하고 해당 공급자의 API 키를 입력합니다. 이미 등록된 키를 유지할 때는 입력란을 비워 둡니다.
4. **검색 방식**을 선택하고 **설정 저장**을 누릅니다. 다음 요청부터 적용됩니다.
5. 검색 방식을 바꿨다면 **검색 준비**를 실행합니다. 일반 문서도 변경한 임베딩으로 다시 인덱싱해야 합니다.

기본 로컬 모드에서는 접속자 모두 같은 관리자 신원으로 설정을 변경할 수 있습니다. 선택형 `CODE_AUTH_MODE=jwt`에서는 로그인한 관리자만 변경할 수 있습니다. 다른 관리자가 먼저 저장했다면 오래된 화면의 변경은 거절되므로 새로 불러온 뒤 저장합니다. 모델명은 수정할 수 있으며 실제 계정에서 사용 가능한 모델이어야 합니다. 키 저장 성공은 외부 모델 호출 성공을 의미하지 않습니다.

## 대화·문구 작성용 AI

| 화면 선택 | 연결 | 기본 모델 | 초기 환경 변수 |
|---|---|---|---|
| DeepSeek → DeepSeek API 키 | `https://api.deepseek.com` | `deepseek-flash` | `CODE_LLM_PROVIDER=deepseek`, `DEEPSEEK_API_KEY` |
| DeepSeek → 기존 Command Code 연결 | `https://api.commandcode.ai/provider/v1` | `deepseek/deepseek-v4.1-flash` | `CODE_LLM_PROVIDER=commandcode`, `COMMANDCODE_API_KEY` |
| Claude | Anthropic Messages API | `claude-sonnet-5` | `CODE_LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` |
| OpenAI | OpenAI API | `gpt-4.1-mini` | `CODE_LLM_PROVIDER=openai`, `OPENAI_API_KEY` |

Claude 선택은 Anthropic API 키를 사용합니다. Claude Code 로그인 세션이나 구독을 앱 API 키로 가져오는 기능은 포함하지 않습니다. Command Code 연결은 기본 추론 수준 `high`를 유지합니다. 선택한 공급자의 키가 없거나 호출이 실패하면 오류를 표시하고 다른 공급자로 자동 전환하지 않습니다.

기존 Command Code 로컬 키를 가져오려면 `python3 scripts/configure_commandcode.py`를 사용할 수 있습니다. 이 스크립트는 키를 화면에 출력하지 않고 `.env`에 저장합니다. 관리자 화면에서 설정을 이미 저장한 경우에는 저장된 설정이 `.env`보다 우선합니다.

## 검색 방식

| 선택 | 하는 일 | 필요한 키·서비스 | 제한 |
|---|---|---|---|
| 임베딩 없이 · 키워드 검색 | 원본 Elasticsearch/Nori로 단어가 일치하는 알림 검색 | 임베딩 API 키 불필요 | 표현이 크게 다르면 관련 알림을 놓칠 수 있음 |
| 이 Mac의 로컬 임베딩 | E5 의미 검색과 Nori 키워드 검색 결합 | 같은 Mac의 로컬 모델 서비스 | 최초 모델 다운로드·메모리·계산 시간 필요 |
| OpenAI 임베딩 | OpenAI 의미 검색과 Nori 키워드 검색 결합 | 별도 OpenAI API 키 | 질문과 검색용 텍스트의 외부 전송 및 API 사용 발생 |

**코드번호 직접 조회는 모든 모드에서 DB 원문을 바로 읽습니다.** 임베딩 없이도 대화·비교·초안 작성은 선택한 LLM을 사용할 수 있습니다. 키워드 모드에서 의미 검색을 수행했다고 표시하지 않으며, 벡터 검색·HyDE·멀티쿼리와 임베딩 기반 RAGAS 평가는 사용하지 않습니다.

Claude 또는 DeepSeek와 OpenAI 임베딩을 조합하려면 OpenAI 키도 필요합니다. 이 조합에서는 화면에 나타나는 **검색용 OpenAI API 키** 입력란에 별도로 입력할 수 있습니다. 이미 저장한 OpenAI 키를 유지할 때는 비워 둡니다. **Claude 키만** 사용하려면 키워드 또는 준비된 로컬 임베딩을 선택합니다.

로컬 모델은 `intfloat/multilingual-e5-base`의 고정 revision을 Docker 내부에서 실행합니다. 이 Mac의 Docker에서 계산하며 외부 임베딩 API를 부르지 않습니다. 최초 모델 다운로드에는 인터넷이 필요합니다. 실제 벡터는 768차원이며, 원본 DB의 1536차원 계약을 유지하기 위해 뒤에 0을 붙입니다. 이는 코사인 유사도를 바꾸지 않습니다. 모델 파일은 캐시 볼륨에 보관하고 Git/배포 ZIP에는 넣지 않습니다.

로컬 서비스가 아직 없는 설치에서는 `.env`에 `CODE_EMBEDDING_PROVIDER=local`을 설정한 뒤 `python3 scripts/manage.py start`로 모델 서비스를 준비해야 합니다. 화면은 로컬 서비스의 실제 준비 상태와 고정 모델 식별자를 확인하고, 준비되지 않은 로컬 선택을 비활성화합니다. 로컬 모드를 저장하는 것만으로 모델 컨테이너를 새로 설치하거나 기동하지 않습니다. 의미 검색 중 로컬 모델 연결에 실패해도 키워드 검색으로 몰래 전환하지 않습니다.

## 판정 단계 모델 (선택)

대화 답변은 생성 뒤 충실도(faithfulness)·근거(grounding) 판정을 통과해야 저장됩니다. 기본값은 판정도 생성 모델과 같은 모델·같은 `reasoning_effort`로 수행하는 것이며, 2026-09-22 실측에서 DeepSeek V4.1 Flash(low)의 판정 한 번은 응답이 55~86자인데도 추론 토큰 3천~9천 개로 17~44초가 걸렸습니다. `reasoning_effort`로는 줄일 수 없습니다.

판정 두 단계만 다른 모델로 바꾸려면 `.env`에 다음을 설정하고 `python3 scripts/manage.py start`로 재기동합니다.

| 변수 | 기본값 | 의미 |
|---|---|---|
| `CODE_LLM_JUDGE_MODEL` | 비어 있음 | 판정에 쓸 모델명. 비어 있으면 생성 모델을 그대로 사용 |
| `CODE_LLM_JUDGE_REASONING_EFFORT` | 비어 있음 | 판정 호출의 `reasoning_effort`. `low`/`medium`/`high` 또는 파라미터를 보내지 않는 `none`. 비어 있으면 `CODE_LLM_REASONING_EFFORT`를 따름. Command Code에서만 전송 |

- 생성·HyDE·다중 질의·형식/근거 재작성·RAGAS 평가는 이 설정의 영향을 받지 않고 관리자 화면의 모델을 계속 씁니다. 판정 전송은 같은 공급자·같은 키를 쓰며 temperature 0입니다.
- 상태 API(`GET /api/code-catalog/status`)의 `llm.judge_model`에 실제 판정 모델이 표시됩니다. 트레이스의 `catalog-Explanation/faithfulness`·`/grounding` 단계도 판정 모델을 기록합니다.
- 잘못된 값(허용되지 않은 문자·`minimal` 등)은 판정 시점에 오류로 중단하며 원래 모델로 몰래 되돌아가지 않습니다.
- Command Code의 Claude 계열(`claude-*`)은 `/provider/v1/messages` 경로만 허용해 이 옵션(chat/completions)으로는 쓸 수 없고, 요금제에 없는 모델은 403(`MODEL_NOT_IN_PLAN`)으로 실패합니다. 후보 모델별 실측은 [검증 보고서](TEST_REPORT.md)의 2026-09-22 항목을 보세요.
- 이 옵션은 판정을 생략하거나 캐시하지 않습니다. 판정 기준(충실도 0.9·근거 0.8, 형식 불량은 502)은 그대로입니다.

## 설정과 키의 보관

초기 선택은 `.env`의 `CODE_LLM_PROVIDER`, `CODE_LLM_MODEL`, `CODE_EMBEDDING_PROVIDER`와 공급자 키에서 읽습니다. 관리자 화면에서 저장한 뒤에는 `CODE_AI_SETTINGS_FILE`이 가리키는 서버 파일을 우선합니다. 기본 Compose 경로는 `/app/private-settings/ai.json`이며 `ai-settings` 전용 볼륨에 저장합니다. API와 작업자가 같은 설정을 읽습니다.

파일은 권한 0600으로 저장하고 공개 API 응답에는 키 대신 등록 여부만 반환합니다. 파일 자체를 암호화하는 저장소는 아니므로 이 볼륨과 `.env`를 비밀 자료로 취급해야 합니다. 키·볼륨·운영 DB·회사 엑셀·모델 파일을 Git, ZIP, 공유 로그에 포함하지 않습니다. 일반 문서 기능을 제거하거나 별도 인증 앱으로 대체하지 않습니다.

## 확인한 범위

2026-09-21 기준, 관리자 설정의 DeepSeek/Claude/OpenAI 저장·재조회와 모바일 표시를 실제 브라우저에서 검사했습니다. 이 설정 UI 검사는 인증 대역을 사용했고 외부 AI를 호출하지 않았습니다. 실제 호출로 확인한 것은 **Command Code 경유 DeepSeek**와 **로컬 E5 합성 문장 임베딩**입니다. 직접 DeepSeek, Claude, OpenAI는 실제 키 호출을 아직 확인하지 않았습니다.

기본 로컬 모드로 실제 Next 화면에 인증 헤더 없이 진입하고 AI 설정 조회, 키워드 모드 저장·재조회, 원래 모드 복원을 확인했습니다. 실제 HTTP 6개 검사도 통과했고 문서·카탈로그는 모두 0건이었습니다. 전체 검색·초안·승인 종단간 검증은 별도입니다. 회사 자료를 운영 목록에 넣지 않았으며, 자세한 근거는 [검증 보고서](TEST_REPORT.md)를 참고하세요.
