FROM node:22-alpine AS builder
WORKDIR /app
COPY upstream/frontend/package.json upstream/frontend/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY upstream/frontend ./
COPY extensions/frontend ./
COPY deploy/patch_frontend.mjs /tmp/patch_frontend.mjs
RUN node /tmp/patch_frontend.mjs
COPY deploy/patch_provider_frontend.mjs /tmp/patch_provider_frontend.mjs
RUN node /tmp/patch_provider_frontend.mjs
COPY deploy/patch_experience.mjs /tmp/patch_experience.mjs
RUN node /tmp/patch_experience.mjs
COPY deploy/patch_local_access_frontend.mjs /tmp/patch_local_access_frontend.mjs
RUN node /tmp/patch_local_access_frontend.mjs
COPY deploy/patch_settings_availability_frontend.mjs /tmp/patch_settings_availability_frontend.mjs
RUN node /tmp/patch_settings_availability_frontend.mjs
COPY deploy/patch_settings_selection_frontend.mjs /tmp/patch_settings_selection_frontend.mjs
RUN node /tmp/patch_settings_selection_frontend.mjs
COPY deploy/patch_chunking_frontend.mjs /tmp/patch_chunking_frontend.mjs
RUN node /tmp/patch_chunking_frontend.mjs
COPY deploy/patch_watcher_frontend.mjs /tmp/patch_watcher_frontend.mjs
RUN node /tmp/patch_watcher_frontend.mjs
COPY deploy/patch_evaluation_frontend.mjs /tmp/patch_evaluation_frontend.mjs
RUN node /tmp/patch_evaluation_frontend.mjs
COPY deploy/patch_proxy_timeout_frontend.mjs /tmp/patch_proxy_timeout_frontend.mjs
RUN node /tmp/patch_proxy_timeout_frontend.mjs
COPY deploy/patch_catalog_surfaces.mjs /tmp/patch_catalog_surfaces.mjs
RUN node /tmp/patch_catalog_surfaces.mjs
COPY deploy/patch_search_persistence.mjs /tmp/patch_search_persistence.mjs
RUN node /tmp/patch_search_persistence.mjs
COPY deploy/patch_monitoring_frontend.mjs /tmp/patch_monitoring_frontend.mjs
RUN node /tmp/patch_monitoring_frontend.mjs
# next.config.ts evaluates rewrites at build time; runtime-only env is insufficient.
ARG NEXT_PUBLIC_API_URL=http://rag-api:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} NEXT_TELEMETRY_DISABLED=1
RUN mkdir -p public && pnpm build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder --chown=appuser:appgroup /app/.next/standalone ./
COPY --from=builder --chown=appuser:appgroup /app/.next/static ./.next/static
COPY --from=builder --chown=appuser:appgroup /app/public ./public
USER appuser
EXPOSE 3000
CMD ["node", "server.js"]
