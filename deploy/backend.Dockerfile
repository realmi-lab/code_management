# Upstream application files are copied unmodified from the verified whole repository.
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/*
COPY upstream/backend /build/backend
COPY extensions/requirements.txt /build/catalog-requirements.txt
RUN pip install --no-cache-dir --prefix=/install /build/backend -r /build/catalog-requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/appuser HF_HOME=/home/appuser/.cache/huggingface \
    XDG_CACHE_HOME=/home/appuser/.cache
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home appuser
WORKDIR /app
COPY --from=builder /install /usr/local
# Haystack sentence splitting must work without downloading resources at runtime.
ADD --checksum=sha256:e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106 https://raw.githubusercontent.com/nltk/nltk_data/550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/packages/tokenizers/punkt_tab.zip /tmp/punkt_tab.zip
RUN python -m zipfile -e /tmp/punkt_tab.zip /usr/local/share/nltk_data/tokenizers && rm /tmp/punkt_tab.zip
COPY --chown=10001:10001 upstream/backend /app
COPY --chown=10001:10001 extensions/code_agent /app/code_agent
COPY deploy/patch_backend.py /tmp/patch_backend.py
RUN python /tmp/patch_backend.py /app
COPY deploy/patch_provider.py /tmp/patch_provider.py
RUN python /tmp/patch_provider.py /app
COPY deploy/patch_reranker.py /tmp/patch_reranker.py
RUN python /tmp/patch_reranker.py /app
COPY deploy/patch_local_access.py /tmp/patch_local_access.py
RUN python /tmp/patch_local_access.py /app
COPY deploy/patch_chunking.py /tmp/patch_chunking.py
RUN python /tmp/patch_chunking.py /app
COPY deploy/patch_monitoring.py /tmp/patch_monitoring.py
RUN python /tmp/patch_monitoring.py /app
RUN mkdir -p /app/uploads /app/run /watch /home/appuser/.cache /app/private-settings \
    && chown -R 10001:10001 /app/uploads /app/run /watch /home/appuser/.cache /app/private-settings
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "code_agent.entrypoint:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "30"]

# Explicit test image; no tests are claimed to have run merely by providing this stage.
FROM runtime AS test
USER root
RUN pip install --no-cache-dir '/app[dev]'
USER 10001:10001
CMD ["python", "-m", "pytest"]
