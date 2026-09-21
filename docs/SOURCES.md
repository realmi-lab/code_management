# 확인한 원본 및 공식 문서

모든 UrstoryRAG 경로의 기준 커밋: 75661c676aec650e52f75dd068b687a4cb6a63b7.

- 저장소: https://github.com/urstory/urstory-rag
- 기준 버전 확인: https://api.github.com/repos/urstory/urstory-rag/branches/main
- 기본 Compose: https://github.com/urstory/urstory-rag/blob/75661c676aec650e52f75dd068b687a4cb6a63b7/docker-compose.yml
- 운영 Compose: https://github.com/urstory/urstory-rag/blob/75661c676aec650e52f75dd068b687a4cb6a63b7/docker-compose.prod.yml
- 백엔드 초기화: https://github.com/urstory/urstory-rag/blob/75661c676aec650e52f75dd068b687a4cb6a63b7/backend/app/main.py
- Celery 진입점: https://github.com/urstory/urstory-rag/blob/75661c676aec650e52f75dd068b687a4cb6a63b7/backend/app/worker.py
- 프론트 rewrite: https://github.com/urstory/urstory-rag/blob/75661c676aec650e52f75dd068b687a4cb6a63b7/frontend/next.config.ts
- Langfuse headless 초기화: https://langfuse.com/self-hosting/administration/headless-initialization
- Docker 환경변수 처리: https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/
- MinIO 릴리스 확인: https://github.com/minio/minio/releases/tag/RELEASE.2025-04-22T22-12-26Z
- MinIO Client 릴리스 확인: https://github.com/minio/mc/releases/tag/RELEASE.2025-04-16T18-13-26Z

이 패키지는 원본과 같은 Langfuse v3 이미지 계열을 사용한다. headless 초기화 등의 실제 v3 이미지 동작은 이 환경에서 실행 검증하지 않았다. 이미지 태그의 존재와 해당 조합의 실행·보안 적합성은 다른 확인이다.

추가 연동 근거: 원본 backend/app/dependencies.py, services/search/{hybrid,vector,keyword_es}.py, services/embedding/openai.py, services/generation/openai.py, frontend/src/lib/auth-context.tsx, components/layout/sidebar.tsx, middleware/security.py. 해당 파일의 계약을 기준으로 확장했다.
