# syntax=docker/dockerfile:1
FROM node:22.18.0-bookworm-slim AS dependencies

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

RUN npm install --global pnpm@12.4.2
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/frontend/client/package.json ./apps/frontend/client/package.json
RUN --mount=type=cache,id=metalmax-pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir /pnpm/store

FROM dependencies AS builder

# rewrites 在构建时写入产物，必须使用生产容器的内部服务地址。
ARG API_BASE_URL=http://server:8000
ENV API_BASE_URL=${API_BASE_URL}
COPY apps/frontend/client ./apps/frontend/client
COPY data/interim ./data/interim
COPY data/processed ./data/processed
RUN mkdir -p apps/frontend/client/public \
    && pnpm --filter @metalmax-wiki/client build

FROM node:22.18.0-bookworm-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    API_BASE_URL=http://server:8000
WORKDIR /app

COPY --from=builder --chown=node:node /app/apps/frontend/client/.next/standalone ./
COPY --from=builder --chown=node:node /app/apps/frontend/client/.next/static ./apps/frontend/client/.next/static
COPY --from=builder --chown=node:node /app/apps/frontend/client/public ./apps/frontend/client/public

USER node
EXPOSE 3000
CMD ["node", "apps/frontend/client/server.js"]
