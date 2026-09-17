# urstory-rag 재사용 범위와 출처

원본: https://github.com/urstory/urstory-rag

검토 기준 커밋: `75661c676aec650e52f75dd068b687a4cb6a63b7`

사용한 원본 파일:
https://github.com/urstory/urstory-rag/blob/75661c676aec650e52f75dd068b687a4cb6a63b7/backend/app/services/search/rrf.py

라이선스:
https://github.com/urstory/urstory-rag/blob/75661c676aec650e52f75dd068b687a4cb6a63b7/LICENSE

## 실제 재사용

`vendor/urstory_rag/rrf.py`의 `RRFCombiner`를 `catalog/search.py`에서 import하여 검색 결과 결합에 실제 사용합니다. 벡터 또는 문자 유사 후보 목록과 키워드 후보 목록을 순위 기반으로 합치는 로직입니다. 입력/출력의 `SearchResult` 계약은 `catalog/models.py`에 필요한 필드만 유지했습니다. 모듈 import 경로와 소스 전사 과정의 서식 일부가 달라 원본 파일과 바이트 동일하지 않습니다. 원본 MIT 저작권 고지를 포함했습니다.

`provenance.json`에 원본 커밋·Git blob 참조값과 실제 전달 파일의 SHA-256을 구분해 적었습니다. `python scripts/verify_vendor.py`는 전달된 파일의 무결성을 확인합니다. 원본 git blob 해시와 수정된 로컬 파일의 해시를 같다고 주장하지 않습니다.

## 별도로 구현한 부분

코드 카탈로그 데이터 모델, Excel/CSV 항목 수집, 정확한 번호 조회, 키워드 별칭·문자 유사 후보 생성, 조건 검사, 선택적 모델 어댑터, 초안·승인·번호 발급, 충돌 검토·원문 갱신, 감사 기록, 웹 화면, 접속 보호, Docker 실행 구성, 테스트를 새로 작성했습니다.

## 이번에 가져오지 않은 부분

원본 Next.js UI, Haystack 전체 파이프라인, 한국어 Cross-Encoder 리랭커, PGVector/Elasticsearch Nori 인프라, Celery, Redis, Langfuse, 원본 JWT 계정 시스템을 가져오거나 배포하지 않았습니다. 따라서 이 전달본의 검색 품질을 원본 README에 기재된 평가 수치로 설명하지 않습니다.

기획자용 코드번호 카탈로그는 원문 정확성, 번호 발급, 버전과 승인 흐름이 중요해 독립적인 정형 DB를 먼저 구현했습니다. 원본 전체 스택으로 확장할 때도 코드번호를 자유형 문서 청크로만 저장하지 말고 이 카탈로그를 기준 데이터로 유지해야 합니다.
