# syntax=docker/dockerfile:1
FROM python:3.14-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app/apps/backend/server

COPY apps/backend/server/pyproject.toml apps/backend/server/uv.lock ./
RUN --mount=type=cache,id=metalmax-uv,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

FROM python:3.14-slim-bookworm AS runtime

ENV PATH="/app/apps/backend/server/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/apps/backend/server

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app
COPY --from=builder --chown=app:app /app/apps/backend/server/.venv ./.venv
COPY --chown=app:app apps/backend/server/app ./app
COPY --chown=app:app apps/backend/server/migrations ./migrations
COPY --chown=app:app apps/backend/server/alembic.ini ./alembic.ini

USER app
EXPOSE 8000
# 进程内限流要求单 worker；仅信任不对宿主机发布端口的容器代理链。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
