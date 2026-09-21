#!/bin/sh
set -eu
# Secrets are supplied as environment variables, not embedded in source files.
mc alias set storage http://langfuse-minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing storage/langfuse
# Do not make the bucket public.
