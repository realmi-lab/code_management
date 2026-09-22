# 카탈로그 AI 절차와 검증

사용자 요청: 원본 GitHub의 검색·리랭킹·청킹 흐름을 따르고, 불필요한 처리를 제거해 답변 품질을 개선한다. 기존 프롬프트는 재사용 가능한 앱 스킬 자산으로 관리하되 질문별 정답을 코드에 넣지 않는다. 후보나 업무 필드를 줄여서 토큰을 절약하지 않는다. 대화·판정 모델은 기존 DeepSeek이며 검색 모델과 저장된 인덱스 설정은 유지한다.

## 최종 결과와 남은 문제

사용자의 “속도는 괜찮아” 지시 이후 속도 설정은 유지했으며, “마무리하자” 지시에 따라 추가 구현·모델 실험을 종료했다. API·worker·beat는 최종 소스로 실행 중이고 실행 자산 53개 해시가 작업 트리와 일치한다. 커밋하지 않았다.

| 검사 | 결과 | 의미 |
| --- | --- | --- |
| 실제 메타데이터 검색 | 정답 1위 5/5; 이전 1·3·28·23·12위; 후보 집합 동일 | 합성 검색 표본이며 전체 답변 정확도와 다름 |
| 원본 청크 적용 후 20문항 | 자동 19/20, 원문 대조 의미 검토 19/20 | 설명 지침 1.0.0 시점. 1건은 수치 정정 응답 차단 |
| 최종 지침 1.0.1 및 무인용 후보 보존 후 8문항 | 자동 7/8, 원문 대조 의미 검토 **6/8** | 알려진 실패와 관련 사례에 집중한 표본; 20문항과 합산하지 않음 |
| 전체 회귀 검사 | pytest 508, 설치 unittest 83, 대역 native HTTP 10 통과 | 실제 모델 의미 정확도를 보증하지 않음 |
| 원본·배포·화면 | 원본 384개 파일·모드 일치, 3개 컨테이너 실행 자산 53개 일치, 최신 답변 및 전체 42/42건 표시 | 실제 Docker와 브라우저 검증 |

남은 문제는 두 가지다. 첫째, 잘못된 시간 전제를 정정하면서 “60초가 아니라 30초”라고 쓰면 단순 수치 집합 검사에서 근거 없는 60초로 차단된다. 별도 합성 진단에서 두 번의 거절 문장을 확보해 이 원인을 확인했다. 원문 후보는 보존되며 거절된 설명은 저장하지 않는다. 공통 지침 1.0.1만으로 이 문제는 해결되지 않았다. 둘째, 날씨처럼 범위 밖인 질문에 검색된 일부 후보를 전체 카탈로그로 오인해 “이 업무들만 있다”고 단정하는 응답이 두 의미 판정을 통과했다. 전체 카탈로그는 실제로 더 넓으므로 최종 의미 검토에서 실패 처리했다. 다음 수정은 수치 정정의 부정 표현과 검색 후보의 부분 범위를 검증에 정확히 전달하는 것이며, 이번 종료 이후에는 적용하지 않았다.

20문항의 공급자 사용량은 **556,465 → 439,037토큰(관측상 21.1% 감소)**이었다. 19개 양쪽 성공 문항의 감소는 117,064토큰이다. 동일 corpus·설정·문항, 단일 회차 측정이며 모든 문항이 성공한 비교가 아니므로 절감 검증 플래그는 `false`다. 최종 8문항은 별도 후속 집합으로 123,904토큰을 사용했으며 이 수치를 20문항과 직접 비교하지 않는다. 구현 에이전트의 원문 대조 검토이고 사람의 블라인드 평가·독립 평가가 아니다. 실제 회사 자료의 일반화 정확도는 미측정이다.

## 실행 계약

`extensions/code_agent/skills/`는 계획·검색 설명·비교·초안·검증의 지시문 자산이다. JSON manifest에는 `id`, `version`, `instruction_file`, `instruction_sha256`만 둔다. `skillbook.py`는 알려진 ID, 버전 형식, 자산 내부 경로와 체크섬을 검사하고 변경 불가능한 값을 반환한다. 실행은 기존 Agent/Gateway, 출력 스키마는 Pydantic 모델, 검증은 CatalogSafety가 소유한다. manifest에 실행 순서나 안전 정책을 중복 정의하지 않는다. 로그의 스킬 ID·버전은 지시문 자산을 식별하며, manifest의 체크섬으로 내용을 확인한다. 검색 설명·비교 1.0.1은 등록 사실 확인 시 근거 없는 질문 수치를 재인용하지 않도록 지시하지만, 실제 실행이 항상 이를 준수하지는 않았다.

검색 설명·비교의 근거는 전체 검색 후보이며 질문·과거 답변을 등록 사실로 취급하지 않는다. `evidence.py`는 마스킹 후 JSON의 반복 키를 열 이름과 행으로 바꿀 수 있다. 후보 수·순서·필드·타입·중첩 값은 복원 가능하게 보존한다. 일반 JSON보다 짧을 때만 사용하며 실제 토큰 절감 여부는 공급자 usage로 따로 측정한다. Apple 브리지의 기존 전송 계약은 유지한다.

검증은 개인정보 → 코드별 명시 인용 원문 → 수치 → 충실도 → 근거 판정 순서다. 코드별 원문 검사는 명확한 `코드/문구/메뉴/노출 조건` 연결만 검사하며 자유 설명의 의미 정확도를 대신하지 않는다. 적용 필드가 없으면 `not_applicable`로 기록한다. 두 의미 판정과 기존 임계값은 유지한다. 형식·내용 거절 시 동일 근거로 한 번만 재작성하며 원문·등록 승인 권한은 바꾸지 않는다.

## 검색 실행

[원본 고정 정보](../upstream.lock.json)의 UrstoryRAG 커밋은 `75661c676aec650e52f75dd068b687a4cb6a63b7`이다. `upstream/` 원본은 수정하지 않으며 필요한 변경은 확장 어댑터와 빌드 사본 패치로 적용한다. E5 query/passage 접두어, 정규화 및 768→1536 영벡터 패딩, PGVector, Elasticsearch Nori, RRF, 한국어 cross-encoder를 유지한다.

카탈로그는 활성 DB 행 한 건의 업무 필드 10개와 메뉴·노출 조건을 청크 하나로 함께 색인한다. 일반 업로드 문서의 청킹 설정은 카탈로그를 분할하지 않는다. `CatalogReranker`는 원본 검색 결과의 `content`와 후보 목록을 그대로 `run_rerank`에 전달한다. 세 필드 요약, 전체 필드 재조립, 별도 12건 제한, 추가 창 분할·최고 점수 집계, highlight 기반 입력 재구성은 사용하지 않는다. 원본 리랭커의 결과 개수·순서·점수·메타데이터를 그대로 반환한다.

[원본 hybrid 검색](../upstream/backend/app/services/search/hybrid.py)은 RRF 이후 입력 후보를 `reranker_top_k * 4`로 제한하고 리랭커 출력에는 `reranker_top_k`를 적용한다. 저장 설정 retriever 20 / reranker 50에서는 vector·keyword 각 20건의 합집합이 최대 40건이므로 원본 입력 상한 200건으로 잘리지 않는다. 어댑터는 별도의 후보 상한을 추가하지 않는다. 검색 캐시 정책은 4이며 이전의 필드 재구성·창 집계 결과를 재사용하지 않는다.

`rerank_runtime.py`는 CPU 계산을 한 번에 하나 실행하고 Torch 계산 스레드를 기본 2개로 제한한다. 대기 요청이 취소되면 계산을 제출하지 않는다. 실행 중인 계산은 await 취소만으로 멈추지 않으므로 실제 완료 전 다음 계산을 시작하지 않는다. 이 설정은 모델·문서·순위 공식을 변경하지 않는다.

[원본 리랭커](../upstream/backend/app/services/reranking/korean.py)는 `doc.content[:512]`를 평가한다. 이는 **512자 제한**이며 512토큰 제한이 아니다. 이번 활성 demo 279건의 색인 청크는 212~434자로 모두 제한 이내다. 512자를 넘는 장문은 원본과 동일하게 뒤쪽 내용이 리랭킹 점수에 반영되지 않는다. DB 원문은 보존되지만 장문 전체를 평가한다는 보장은 없다. 별도 장문 창 분할 기능은 최종 구현에서 제외했다.

설치된 sentence-transformers 4.1.0에서 `CrossEncoder.predict`의 기본 배치는 32이며, 원본은 `max_length`·배치·Torch 스레드를 명시하지 않는다. 캐시된 모델의 tokenizer 최대 길이는 8192토큰이고 배치 내 입력 길이에 맞춰 padding한다. 모든 입력을 8192토큰까지 채우는 것은 아니다. [빌드 패치](../deploy/patch_reranker.py)는 원본 해시를 검사한 후 `predict(..., activation_fn=torch.nn.Identity(), batch_size=4)`를 적용한다. 이 리랭커 소스 패치의 실행 자원 변경은 배치 32→4뿐이며 후보 수·원문·512자 제한·순위 공식을 유지한다. 배치 4는 최대 배치 메모리 부담을 줄이려는 조치로, 최종 5개 검색은 27.8~40.6초였으며, 사용자 요청으로 추가 속도 조정은 중단하고 현재 설정을 유지한다. 속도 개선을 완료했다고 주장하지 않는다.

Identity는 설치 버전의 기본 활성화와 원본 후처리가 sigmoid를 두 번 적용하던 결함을 고친다. raw logits를 받아 원본의 sigmoid를 한 번 적용하고, `replace` 모드도 원래 의도한 raw logits를 사용한다. [설치 소스·모델 config 증거](verification/catalog-skills-2026-09-22/retrieval-model-contract.json)와 [공식 CrossEncoder 계약](https://www.sbert.net/docs/package_reference/cross_encoder/model.html)을 대조했다. 게이트 임계값은 변경하지 않았다. 순위 보너스가 남으므로 **점수는 정확도가 아니며 게이트 통과도 관련성의 증명이 아니다.**

실제 PostgreSQL 행 키는 일반 문자열의 하위형인 `quoted_name`이다. 인코더는 JSON과 동일하게 문자열 호환 키를 허용한다. 최초 엄격한 타입 검사의 실서비스 실패는 `after-pre-fix/`에 보존하고 최종 성공 실측과 분리한다. 설명 오류가 있어도 검색·설명·비교의 검증된 DB 후보와 규칙 비교 결과는 보존하며, 거절된 AI 문장은 저장하지 않는다. 성공한 설명이 코드번호를 인용하지 않아도 검색 후보를 삭제하지 않고 `no_cited_candidate`로 기록한다. 인용 부재는 검색 결과가 무관하다는 증거가 아니다.

## 재현 가능한 평가

`scripts/benchmark_catalog_skills.py`는 고정된 합성 demo manifest, corpus, 설정을 저장하고 변경 전후 동일 조건만 비교한다. 정답 코드 회수, 코드별 인용, 이후/이내 방향, 수치 전체 목록, 후보 원문 보존, AI 오류와 실제 모델 호출을 구분한다. 모델 응답 성공이나 자체 판정 점수를 의미 정확도로 보고하지 않는다. 의미 적합성·잘못된 전제 정정은 별도 원문 대조가 필요하다.

```bash
python3 scripts/benchmark_catalog_skills.py --output docs/verification/catalog-skills-2026-09-22/new-run --phase baseline --runs 2 --concurrency 2 --suite all
# 동일 corpus/settings/manifest에서 구현 변경·검증·배포 후:
python3 scripts/benchmark_catalog_skills.py --output docs/verification/catalog-skills-2026-09-22/new-run --phase after --runs 2 --concurrency 2 --suite all
```

각 phase 결과는 덮어쓰지 않는다. 실패하거나 usage가 누락된 요청을 0토큰으로 계산하지 않는다. 실패 답변 때문에 사용량이 줄면 검증된 절감으로 표시하지 않는다. 공급자가 usage를 반환하지 않은 내부 재시도 비용은 알 수 없다. 표본은 합성 알림 카탈로그이며 실제 회사 자료의 일반화 정확도가 아니다.

`scripts/audit_catalog_retrieval.py`는 설정을 바꾸지 않고 vector → keyword → RRF → 리랭커 입력 단계의 정답 순위를 따로 측정한다. 기본 모드에서는 LLM과 cross-encoder를 추가 실행하지 않는다. 일반 문서 검색과 카탈로그 검색의 결과를 섞지 않는다.

## 이번 실행 증거

실측 자료는 `verification/catalog-skills-2026-09-22/`에 보존한다. 자료는 합성 demo 300건 중 활성 279건이며 운영 자료는 0건이다.

| 평가 | 확인된 결과 | 해석 범위 |
| --- | --- | --- |
| [완료된 기준선](verification/catalog-skills-2026-09-22/live-scheduled/baseline/summary.json) | 20건 중 객관 검사 19건 통과, 공급자 usage 합계 556,465토큰 | 의미 정확도 95% 또는 최종 개선 효과를 뜻하지 않음 |
| [중간 전체 필드·창 처리 실험](verification/catalog-skills-2026-09-22/retrieval-challenge-after.json) | 5건 중 3건 완료, 네 번째 HTTP 504, 다섯 번째 미실행 | 최종 원본 청크 어댑터의 평가가 아님 |
| [최종 원본 청크·배치 4 검색](verification/catalog-skills-2026-09-22/retrieval-challenge-upstream-final.json) | 5건 모두 정답 1위, 후보 집합 동일, 오류 없음 | 합성 메타데이터 검색 표본. 답변의 일반화 정확도가 아님 |
| [원본 청크 적용 후 답변 20문항](verification/catalog-skills-2026-09-22/live-scheduled/after/summary.json) | 객관 19/20, 의미 19/20 | 최종 지침 1.0.1 이전 측정 |
| [최종 후속 8문항](verification/catalog-skills-2026-09-22/accuracy-followup/baseline/summary.json) | 객관 7/8, 의미 6/8 | CLI phase 이름은 baseline이나 최종 수정 후 독립 후속 검사 |

처음 병렬 검색 두 건은 약 162/169초 후 HTTP 504였으며 `live/baseline/`은 중단된 부분 결과다. 완료된 기준선과 섞지 않는다. 별도 메타데이터 질의의 [변경 전후 비교](verification/catalog-skills-2026-09-22/retrieval-challenge-comparison.json)에서는 세 필드만 보는 기존 입력의 정답 순위 1·3·28위가 중간 전체 필드 실험에서 모두 1위로 바뀌었다. 그러나 완료된 세 요청도 약 40·133·105초가 걸렸고 다음 요청은 실패했다. 이를 5건 전체 성공이나 최종 성능 개선으로 보고하지 않는다.

[자원 진단](verification/catalog-skills-2026-09-22/resource-diagnosis.md)에서 호스트 RAM 32GiB, Docker VM 약 7.75GiB와 거의 소진된 VM 스왑, 호스트 압축 메모리·스왑 사용을 직접 관측했다. 같은 시기 여러 서비스가 CPU를 사용했고 평가 요청은 직렬 리랭커 대기열을 공유했다. 자원 경합은 관측됐지만 입력 길이·배치 크기·호스트 경합 각각의 지연 기여율은 계측하지 않았다. 당시 활성 청크는 모두 512자 이내여서 창 분할에 따른 추가 추론은 없었다. 원본 청크 복귀나 배치 축소만으로 지연이 해결됐다고 단정하지 않는다.

## 최종 증거 파일

- [검색 전후](verification/catalog-skills-2026-09-22/retrieval-challenge-upstream-comparison.json)
- [20문항 의미 검토](verification/catalog-skills-2026-09-22/after-manual-review.json) · [최종 8문항 의미 검토](verification/catalog-skills-2026-09-22/accuracy-followup-manual-review.json)
- [수치 정정 거절문 진단](verification/catalog-skills-2026-09-22/false-premise-captured-diagnostic.json)
- [최종 배포 해시](verification/catalog-skills-2026-09-22/deployed-hashes-accuracy-final.json) · [최종 브라우저](verification/catalog-skills-2026-09-22/live-browser-accuracy-final.json)
- [최종 pytest](verification/catalog-skills-2026-09-22/integration-tests-accuracy-final.log) · [설치 검사](verification/catalog-skills-2026-09-22/installer-tests-upstream-final.log) · [최종 HTTP](verification/catalog-skills-2026-09-22/native-http-accuracy-final.log)

평가 하네스 v2는 후보의 모든 JSON 필드·중첩 값·타입을 원문과 비교하고 서비스와 같은 코드 문법을 사용한다. 기존 20문항 결과는 원본을 보존하고 [오프라인 재채점](verification/catalog-skills-2026-09-22/regraded-v2/)에 별도 저장했다. 모델 추가 호출 없이 재채점했으며 전후 모두 19/20으로 동일했다.
