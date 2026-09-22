#!/usr/bin/env python3
"""Run the original tests in a dedicated container, without real provider keys.

Downloading/installing dependencies occurs during Docker build. The test
container joins only an *internal* Docker network (no internet) together with a
throwaway PostgreSQL (pgvector) that exists for this run only; the project's
live database volume is never touched. Integration tests requiring other live
services may fail or be skipped; never describe this as a live RAG benchmark.
"""
import subprocess
import time

from manage import ROOT, SetupError, docker_preflight, load_env, prepare, run

IMAGE = 'code-management-upstream-test:75661c6'
NETWORK = 'code-management-upstream-test-net'
DATABASE = 'code-management-upstream-test-pg'
# Same credentials the original tests/conftest.py uses by default.
DB_USER, DB_PASSWORD, DB_NAME = 'admin', 'changeme_strong_password', 'shared_test'


def quiet(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_database() -> None:
    image = load_env(ROOT / '.env').get('POSTGRES_IMAGE') or 'pgvector/pgvector:pg17'
    run(['docker', 'network', 'create', '--internal', NETWORK], capture=True)
    run(['docker', 'run', '-d', '--rm', '--name', DATABASE, '--network', NETWORK,
         '-e', f'POSTGRES_USER={DB_USER}', '-e', f'POSTGRES_PASSWORD={DB_PASSWORD}', '-e', f'POSTGRES_DB={DB_NAME}',
         '-v', f"{ROOT / 'upstream/infra/init-db.sql'}:/docker-entrypoint-initdb.d/10-vector.sql:ro",
         image], capture=True)
    for _ in range(60):
        ready = subprocess.run(['docker', 'exec', DATABASE, 'pg_isready', '-U', DB_USER, '-d', DB_NAME],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if ready.returncode == 0:
            time.sleep(1)  # the init script may still be running right after the first ready signal
            return
        time.sleep(1)
    raise SetupError('테스트용 PostgreSQL이 60초 안에 준비되지 않았습니다.')


def cleanup() -> None:
    quiet(['docker', 'rm', '-f', DATABASE])
    quiet(['docker', 'network', 'rm', NETWORK])


if __name__ == '__main__':
    try:
        docker_preflight(); prepare()
        run(['docker', 'build', '--target', 'test', '-f', 'deploy/backend.Dockerfile', '-t', IMAGE, '.'])
        cleanup()  # leftovers from an interrupted run
        try:
            start_database()
            run(['docker', 'run', '--rm', '--network', NETWORK,
                 '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'OPENAI_API_KEY=test-not-a-real-api-key',
                 '-e', 'JWT_SECRET_KEY=test-only-jwt-secret-not-for-production',
                 '-e', f'DATABASE_URL=postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DATABASE}:5432/{DB_NAME}',
                 '--entrypoint', 'python', IMAGE, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-m', 'not performance'])
        finally:
            cleanup()
    except SetupError as exc:
        print('테스트 중단:', exc)
        raise SystemExit(1)
