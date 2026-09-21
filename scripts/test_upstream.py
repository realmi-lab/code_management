#!/usr/bin/env python3
"""Run the original tests in a dedicated container, without real provider keys.

Downloads/installing dependencies occurs during Docker build. The test container
has no network. Integration tests requiring live services may fail or be skipped;
never describe this as a live RAG benchmark.
"""
from manage import ROOT, SetupError, docker_preflight, prepare, run

if __name__ == '__main__':
    try:
        docker_preflight(); prepare()
        run(['docker', 'build', '--target', 'test', '-f', 'deploy/backend.Dockerfile', '-t', 'code-management-upstream-test:75661c6', '.'])
        run(['docker', 'run', '--rm', '--network', 'none',
             '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'OPENAI_API_KEY=test-not-a-real-api-key',
             '-e', 'JWT_SECRET_KEY=test-only-jwt-secret-not-for-production',
             '--entrypoint', 'python', 'code-management-upstream-test:75661c6', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-m', 'not performance'])
    except SetupError as exc:
        print('테스트 중단:', exc)
        raise SystemExit(1)
