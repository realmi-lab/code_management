# 리랭커 지연 및 자원 상태 진단

기록일: 2026-09-22. 관측 시점은 after 평가 중단 및 Docker Compose Recreate 정체를 진단하던 배포 전 과도 상태다. 개별 명령의 정확한 벽시계 시각은 기록하지 않았으므로 시·분은 추정하지 않는다. 아래 값은 현재 상태를 보증하는 지속 관측값이 아니다.

모델 추론·큰 검색·코드 변경 없이 호스트 상태, Docker 단일 자원 스냅샷, 컨테이너 cgroup/캐시 설정/설치 소스 및 기존 279건 corpus를 읽었다. 원문과 비밀값은 기록하지 않았다.

## 직접 관측

| 항목 | 관측값 |
|---|---|
| 호스트 CPU / RAM | 10 CPU / 32 GiB |
| 호스트 free pages | 3,959 × 16 KiB, 약 61.9 MiB. 회수 가능한 전체 메모리를 뜻하지 않음 |
| 호스트 compressor 점유 | 647,607 × 16 KiB, 약 9.88 GiB |
| 호스트 스왑 | 총 5,120.00 MiB / 사용 4,118.94 MiB / 여유 1,001.06 MiB |
| Docker VM 메모리 | 총 8,124,516 KiB / MemAvailable 1,029,116 KiB |
| Docker VM 스왑 | 총 1,048,572 KiB / 여유 84 KiB |
| API cgroup 메모리 | 1,070,235,648 bytes, memory.max=max |
| API cgroup CPU | cpu.max=max 100000, nr_throttled=0, throttled_usec=0 |
| API cgroup OOM | oom=0, oom_kill=0 |
| 컨테이너 자원 제한 | 해당 Compose 컨테이너들의 명시적 CPU/메모리 제한 없음, OOMKilled=false |

동일 `docker stats --no-stream` 호출의 CPU 표시값: API 148.79%, local-embeddings 119.80%, ClickHouse 202.90%, Langfuse web 182.79%, MinIO 133.50%, frontend 185.86%, worker 195.56%. 이는 도구의 단일 표본이며 장기 평균이나 호스트 CPU 사용률과 직접 동일시하지 않는다.

설치된 sentence-transformers는 4.1.0이다. `CrossEncoder.predict` 구현의 기본 batch_size는 32이며 tokenizer에 padding=True/truncation=True를 전달한다. 캐시된 `dragonkue/bge-reranker-v2-m3-ko` 설정은 XLM-RoBERTa, 24층, hidden_size 1024, attention heads 16, max_position_embeddings 8194이며 tokenizer model_max_length는 8192다. 실행 중 모델 객체의 메모리 내부 설정은 조회하지 않았다. 원본 `korean.py`의 512 제한은 `doc.content[:512]`라는 **문자 제한**이며 512 토큰 제한이 아니다.

`rerank_runtime` 소스는 worker 1개와 이벤트 루프별 semaphore를 사용하고, 취소된 await의 실제 작업이 끝날 때까지 gate를 유지한다. CODE_RERANK_THREADS는 컨테이너에서 미설정이었으므로 소스상 기본 설정은 Torch 2 threads다. 실제 모델 스레드 사용률을 계측한 것은 아니다. 두 요청의 검색 제한 시간에는 이 gate 대기 시간도 포함된다.

## 기존 corpus의 입력 길이 — 추론 없이 계산

자료: `docs/verification/catalog-quality-68/corpus.json`, active 합성 자료 279건. 관측 당시 `text_for`와 `rerank_text`를 적용했다.

| 표현 | 최소 문자 | 중앙값 | 최대 문자 | 512자 초과 | 전체 윈도 수 |
|---|---:|---:|---:|---:|---:|
| 원본 색인 입력 `text_for` | 212 | 330 | 434 | 0 | 279 |
| 당시 전체 필드 재구성 `rerank_text` | 139 | 244 | 306 | 0 | 279 |

**현재 279건에서는 모든 문서가 단일 윈도이며 윈도 증폭·overlap 계산이 추가 추론을 만들지 않는다.** 따라서 이번 39~133초 지연을 윈도 증폭으로 설명할 수 없다. 원본 색인 입력으로 복귀하면 중간 재구성은 없어지지만 중앙 입력 길이는 244→330자, 약 35.2% 늘어난다. 원본 입력 복귀 자체를 속도 개선으로 주장할 근거는 없다.

## 해석 및 한계

- Docker VM 스왑 소진, 호스트 압축/스왑 사용 및 여러 서비스의 높은 CPU 표시값은 자원 경합을 뒷받침한다. 단일 관측만으로 Recreate 정체나 리랭커 지연의 원인을 하나로 확정하지 않는다.
- 긴 입력을 batch 32로 padding하는 방식은 최대 activation 메모리 부담을 키울 수 있다. 실제 token 길이 분포·텐서 shape·peak memory·추론별 시간은 측정하지 않았으므로 padding의 지연 기여율은 미확정이다.
- batch_size=4는 후보와 원문을 그대로 처리하면서 최대 배치 메모리를 줄이려는 변경이다. 속도 개선 수치는 아직 없다. 기록 시 부모 작업자는 이 패치를 완료했다고 보고했으며, 이 진단에서 배포 완료를 검증하지 않았다.
- 불필요한 중간 처리 제거와 원본 GitHub 흐름 준수는 별도 목적이다. DB 내부 식별자·추적 메타데이터·중복 별칭값을 모델에 반복 전달할 필요는 없지만 메뉴·조건·영문·용도·비고 등 검색 가능한 업무 필드의 값은 유지해야 한다.
- 이번 진단 이후 추가 추론이나 자원 재측정은 하지 않았다.
