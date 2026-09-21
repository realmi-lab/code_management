"""Generate a standalone deployment for the unmodified, pinned upstream tree.

JSON is also YAML and is accepted by Docker Compose. No third-party dependency
is required to render or inspect this file. Secrets remain environment references.
"""
from __future__ import annotations
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def health(command: list[str], start: str = '30s') -> dict:
    return {'test': command, 'interval': '10s', 'timeout': '5s', 'retries': 12, 'start_period': start}


def build_compose() -> dict:
    app_env = {
        'DATABASE_URL': 'postgresql+asyncpg://${POSTGRES_USER:-rag}:${POSTGRES_PASSWORD:?Run configure}@postgres:5432/${POSTGRES_DB:-rag}',
        'ELASTICSEARCH_URL': 'http://elasticsearch:9200',
        'REDIS_URL': 'redis://:${REDIS_PASSWORD_URLENCODED:?Run configure}@redis:6379/0',
        'RAG_INTERNAL_API_URL':'http://rag-api:8000',
        'CODE_CATALOG_AUTHORITY':'${CODE_CATALOG_AUTHORITY:-system}',
        'CODE_AUTH_MODE':'${CODE_AUTH_MODE:-local}',
        'OPENAI_API_KEY': '${OPENAI_API_KEY:-}',
        'ANTHROPIC_API_KEY': '${ANTHROPIC_API_KEY:-}',
        'DEEPSEEK_API_KEY': '${DEEPSEEK_API_KEY:-}',
        'CODE_AI_SETTINGS_FILE':'/app/private-settings/ai.json',
        'CODE_EMBEDDING_PROVIDER': '${CODE_EMBEDDING_PROVIDER:-none}',
        'LOCAL_EMBEDDING_TOKEN': '${LOCAL_EMBEDDING_TOKEN:-}',
        'LOCAL_EMBEDDING_URL': 'http://local-embeddings:8080',
        'CODE_LLM_PROVIDER': '${CODE_LLM_PROVIDER:-openai}',
        'COMMANDCODE_API_KEY': '${COMMANDCODE_API_KEY:-}',
        'CODE_LLM_MODEL': '${CODE_LLM_MODEL:-}',
        'CODE_LLM_REASONING_EFFORT': '${CODE_LLM_REASONING_EFFORT:-high}',
        'JWT_SECRET_KEY': '${JWT_SECRET_KEY:?Run configure}',
        'ADMIN_USERNAME': '${ADMIN_USERNAME:-admin}',
        'ADMIN_PASSWORD': '${ADMIN_PASSWORD:-}',
        'ALLOW_PUBLIC_SIGNUP': 'false',
        'CORS_ORIGINS': 'http://localhost:${WEB_PORT:-3500},http://127.0.0.1:${WEB_PORT:-3500}',
        'LANGFUSE_PUBLIC_KEY': '${LANGFUSE_PUBLIC_KEY:?Run configure}',
        'LANGFUSE_SECRET_KEY': '${LANGFUSE_SECRET_KEY:?Run configure}',
        'LANGFUSE_HOST': 'http://langfuse-web:3000',
        'LOG_FORMAT': 'json', 'LOG_LEVEL': '${LOG_LEVEL:-INFO}',
        'SENTRY_DSN': '${SENTRY_DSN:-}', 'SENTRY_ENVIRONMENT': 'local',
        'TOKENIZERS_PARALLELISM': 'false',
        'HF_HOME': '/home/appuser/.cache/huggingface',
        'XDG_CACHE_HOME': '/home/appuser/.cache',
    }
    base_build = {'context': '.', 'dockerfile': 'deploy/backend.Dockerfile', 'target': 'runtime'}
    base = {
        'build': base_build, 'image': '${COMPOSE_PROJECT_NAME:-code-management-full}-api:75661c6',
        'environment': app_env,
        'volumes': ['uploads:/app/uploads', 'model-cache:/home/appuser/.cache', 'watch:/watch', 'ai-settings:/app/private-settings'],
        'restart': 'unless-stopped', 'init': True, 'stop_grace_period': '40s',
        'security_opt': ['no-new-privileges:true'],
    }
    db_health = {'postgres': {'condition': 'service_healthy'}, 'redis': {'condition': 'service_healthy'}, 'elasticsearch': {'condition': 'service_healthy'}}
    app_deps = {**db_health, 'db-migrate': {'condition': 'service_completed_successfully'}}
    lf_env = {
        'DATABASE_URL': 'postgresql://${POSTGRES_USER:-rag}:${POSTGRES_PASSWORD:?Run configure}@postgres:5432/langfuse',
        'NEXTAUTH_URL': 'http://localhost:${LANGFUSE_PORT:-3100}',
        'NEXTAUTH_SECRET': '${NEXTAUTH_SECRET:?Run configure}',
        'SALT': '${LANGFUSE_SALT:?Run configure}',
        'ENCRYPTION_KEY': '${LANGFUSE_ENCRYPTION_KEY:?Run configure}',
        'CLICKHOUSE_URL': 'http://clickhouse:8123',
        'CLICKHOUSE_MIGRATION_URL': 'clickhouse://clickhouse:9000',
        'CLICKHOUSE_USER': 'langfuse', 'CLICKHOUSE_PASSWORD': '${CLICKHOUSE_PASSWORD:?Run configure}',
        'CLICKHOUSE_CLUSTER_ENABLED': 'false',
        'REDIS_HOST': 'langfuse-redis', 'REDIS_PORT': '6379', 'REDIS_AUTH': '${LANGFUSE_REDIS_PASSWORD:?Run configure}',
        'LANGFUSE_S3_EVENT_UPLOAD_BUCKET': 'langfuse', 'LANGFUSE_S3_EVENT_UPLOAD_REGION': 'auto',
        'LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID': '${MINIO_ROOT_USER:-langfuse}',
        'LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY': '${MINIO_ROOT_PASSWORD:?Run configure}',
        'LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT': 'http://langfuse-minio:9000',
        'LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE': 'true',
        'TELEMETRY_ENABLED': 'false', 'AUTH_DISABLE_SIGNUP': 'true',
    }
    lf_deps = {'postgres': {'condition': 'service_healthy'}, 'clickhouse': {'condition': 'service_healthy'},
               'langfuse-redis': {'condition': 'service_healthy'}, 'langfuse-minio-init': {'condition': 'service_completed_successfully'}}
    services = {
        'local-embeddings': {
            'profiles':['local-embedding'],
            'build':base_build,'image':'${COMPOSE_PROJECT_NAME:-code-management-full}-api:75661c6',
            'command':['uvicorn','code_agent.local_embeddings:app','--host','0.0.0.0','--port','8080'],
            'environment':{'LOCAL_EMBEDDING_TOKEN':'${LOCAL_EMBEDDING_TOKEN:-}',
                           'HF_HOME':'/home/appuser/.cache/huggingface','TOKENIZERS_PARALLELISM':'false',
                           'HF_HUB_DISABLE_XET':'1'},
            'volumes':['model-cache:/home/appuser/.cache'],
            'healthcheck':health(['CMD','python','-c',"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=4)"],'900s'),
            'restart':'unless-stopped','init':True,
        },
        'postgres': {
            'image': '${POSTGRES_IMAGE:-pgvector/pgvector:pg17}',
            'environment': {'POSTGRES_USER': '${POSTGRES_USER:-rag}', 'POSTGRES_PASSWORD': '${POSTGRES_PASSWORD:?Run configure}', 'POSTGRES_DB': '${POSTGRES_DB:-rag}'},
            'volumes': ['postgres-data:/var/lib/postgresql/data', './deploy/init-postgres.sh:/docker-entrypoint-initdb.d/10-rag.sh:ro'],
            'healthcheck': health(['CMD-SHELL', 'pg_isready -h 127.0.0.1 -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"']),
            'restart': 'unless-stopped',
        },
        'elasticsearch': {
            'build': {'context': '.', 'dockerfile': 'deploy/elasticsearch.Dockerfile', 'args': {'ES_IMAGE': '${ES_IMAGE:-docker.elastic.co/elasticsearch/elasticsearch:8.17.0}'}},
            'environment': {'discovery.type': 'single-node', 'xpack.security.enabled': 'false',
                            'ES_JAVA_OPTS': '${ES_JAVA_OPTS:--Xms1g -Xmx1g}'},
            'volumes': ['elasticsearch-data:/usr/share/elasticsearch/data'],
            'healthcheck': health(['CMD-SHELL', "curl -fsS 'http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=3s' >/dev/null"], '60s'),
            'restart': 'unless-stopped',
        },
        'redis': {
            'image': '${REDIS_IMAGE:-redis:7-alpine}',
            'environment': {'REDIS_PASSWORD': '${REDIS_PASSWORD:?Run configure}'},
            'command': ['sh', '-c', 'exec redis-server --appendonly yes --requirepass "$${REDIS_PASSWORD}"'],
            'volumes': ['redis-data:/data'],
            'healthcheck': health(['CMD-SHELL', 'REDISCLI_AUTH="$${REDIS_PASSWORD}" redis-cli ping | grep -q PONG']),
            'restart': 'unless-stopped',
        },
        'db-migrate': {
            **base, 'command': ['sh', '-c', 'alembic upgrade head && python -m code_agent.migrate'],
            'depends_on': {'postgres': {'condition': 'service_healthy'}},
            'restart': 'no',
        },
        'rag-api': {
            **base, 'depends_on': app_deps,
            'ports': ['127.0.0.1:${API_PORT:-8000}:8000'],
            'healthcheck': health(['CMD', 'python', '-c', "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready',timeout=4)"], '120s'),
        },
        'rag-worker': {
            **base, 'depends_on': app_deps,
            'command': ['celery', '-A', 'code_agent.worker:celery_app', 'worker', '--loglevel=INFO', '--pool=solo', '--concurrency=1', '--hostname=worker@%h'],
            'healthcheck': {'test': ['CMD-SHELL', 'celery -A code_agent.worker:celery_app inspect ping -d "worker@$${HOSTNAME}" --timeout 5 | grep -q pong'], 'interval': '30s', 'timeout': '15s', 'retries': 6, 'start_period': '120s'},
        },
        'rag-beat': {
            **base, 'depends_on': app_deps,
            'command': ['celery', '-A', 'code_agent.worker:celery_app', 'beat', '--loglevel=INFO', '--schedule=/app/run/celerybeat-schedule'],
            'volumes': base['volumes'] + ['beat-state:/app/run'],
        },
        'rag-frontend': {
            'build': {'context': '.', 'dockerfile': 'deploy/frontend.Dockerfile', 'args': {'NEXT_PUBLIC_API_URL': 'http://rag-api:8000'}},
            'ports': ['127.0.0.1:${WEB_PORT:-3500}:3000'],
            'environment': {'NODE_ENV': 'production', 'HOSTNAME': '0.0.0.0'},
            'depends_on': {'rag-api': {'condition': 'service_healthy'}},
            'healthcheck': health(['CMD', 'node', '-e', "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"], '60s'),
            'restart': 'unless-stopped', 'init': True,
        },
        'clickhouse': {
            'image': '${CLICKHOUSE_IMAGE:-clickhouse/clickhouse-server:24.12}',
            'environment': {'CLICKHOUSE_USER': 'langfuse', 'CLICKHOUSE_PASSWORD': '${CLICKHOUSE_PASSWORD:?Run configure}', 'CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT': '1'},
            'volumes': ['clickhouse-data:/var/lib/clickhouse', './deploy/clickhouse.xml:/etc/clickhouse-server/config.d/local.xml:ro'],
            'healthcheck': health(['CMD', 'wget', '-qO-', 'http://127.0.0.1:8123/ping']),
            'ulimits': {'nofile': {'soft': 262144, 'hard': 262144}}, 'restart': 'unless-stopped',
        },
        'langfuse-redis': {
            'image': '${REDIS_IMAGE:-redis:7-alpine}',
            'environment': {'REDIS_PASSWORD': '${LANGFUSE_REDIS_PASSWORD:?Run configure}'},
            'command': ['sh', '-c', 'exec redis-server --appendonly yes --requirepass "$${REDIS_PASSWORD}"'],
            'volumes': ['langfuse-redis-data:/data'],
            'healthcheck': health(['CMD-SHELL', 'REDISCLI_AUTH="$${REDIS_PASSWORD}" redis-cli ping | grep -q PONG']),
            'restart': 'unless-stopped',
        },
        'langfuse-minio': {
            'image': '${MINIO_IMAGE:-quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z}',
            'environment': {'MINIO_ROOT_USER': '${MINIO_ROOT_USER:-langfuse}', 'MINIO_ROOT_PASSWORD': '${MINIO_ROOT_PASSWORD:?Run configure}'},
            'command': ['server', '/data', '--console-address', ':9001'], 'volumes': ['minio-data:/data'],
            'healthcheck': health(['CMD-SHELL', 'mc alias set health http://127.0.0.1:9000 "$${MINIO_ROOT_USER}" "$${MINIO_ROOT_PASSWORD}" >/dev/null && mc ready health']), 'restart': 'unless-stopped',
        },
        'langfuse-minio-init': {
            'image': '${MINIO_MC_IMAGE:-quay.io/minio/mc:RELEASE.2025-04-16T18-13-26Z}',
            'environment': {'MINIO_ROOT_USER': '${MINIO_ROOT_USER:-langfuse}', 'MINIO_ROOT_PASSWORD': '${MINIO_ROOT_PASSWORD:?Run configure}'},
            'volumes': ['./deploy/minio-init.sh:/init.sh:ro'], 'entrypoint': ['sh', '/init.sh'],
            'depends_on': {'langfuse-minio': {'condition': 'service_healthy'}}, 'restart': 'no',
        },
        'langfuse-web': {
            'image': '${LANGFUSE_WEB_IMAGE:-langfuse/langfuse:3}',
            'ports': ['127.0.0.1:${LANGFUSE_PORT:-3100}:3000'],
            'environment': {**lf_env, 'HOSTNAME':'0.0.0.0',
                'LANGFUSE_INIT_ORG_ID': 'code-management', 'LANGFUSE_INIT_ORG_NAME': 'Code Management',
                'LANGFUSE_INIT_PROJECT_ID': 'urstory-rag', 'LANGFUSE_INIT_PROJECT_NAME': 'Urstory RAG',
                'LANGFUSE_INIT_PROJECT_PUBLIC_KEY': '${LANGFUSE_PUBLIC_KEY:?Run configure}',
                'LANGFUSE_INIT_PROJECT_SECRET_KEY': '${LANGFUSE_SECRET_KEY:?Run configure}',
                'LANGFUSE_INIT_USER_EMAIL': '${LANGFUSE_ADMIN_EMAIL:-admin@example.local}',
                'LANGFUSE_INIT_USER_NAME': 'Local Administrator',
                'LANGFUSE_INIT_USER_PASSWORD': '${LANGFUSE_ADMIN_PASSWORD:?Run configure}'},
            'depends_on': lf_deps, 'restart': 'unless-stopped',
            'healthcheck': health(['CMD', 'node', '-e', "fetch('http://127.0.0.1:3000/api/public/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"], '120s'),
        },
        'langfuse-worker': {
            'image': '${LANGFUSE_WORKER_IMAGE:-langfuse/langfuse-worker:3}',
            'environment': lf_env, 'depends_on': lf_deps, 'restart': 'unless-stopped',
        },
        'catalog-legacy': {
            'profiles': ['legacy'], 'build': {'context': './catalog_legacy'},
            'environment': {'ACCESS_TOKEN': '${CATALOG_ACCESS_TOKEN:?Run configure}', 'DATA_DIR': '/app/data', 'AI_ENABLED': 'false', 'CATALOG_AUTHORITY': 'excel'},
            'ports': ['127.0.0.1:${CATALOG_PORT:-8766}:8000'], 'volumes': ['legacy-catalog-data:/app/data'],
            'restart': 'unless-stopped', 'init': True,
        },
    }
    volumes = {name: {} for name in ['postgres-data', 'elasticsearch-data', 'redis-data', 'uploads', 'model-cache', 'watch', 'beat-state', 'clickhouse-data', 'langfuse-redis-data', 'minio-data', 'legacy-catalog-data', 'ai-settings']}
    return {'name': '${COMPOSE_PROJECT_NAME:-code-management-full}', 'services': services, 'volumes': volumes}


if __name__ == '__main__':
    out = ROOT / 'compose.yaml'
    out.write_text(json.dumps(build_compose(), ensure_ascii=False, indent=2) + '\n')
    print('Rendered', out)
