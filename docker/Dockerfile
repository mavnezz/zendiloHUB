# syntax=docker/dockerfile:1

# ---- web: build the Vue app
FROM node:24-bookworm-slim AS web
WORKDIR /src
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
RUN npm ci --no-audit --no-fund
COPY tsconfig.base.json ./
COPY apps/web apps/web
RUN npm run build

# ---- python: install the server (no dev tools) into a virtualenv
FROM python:3.14-slim-bookworm AS python
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
COPY pyproject.toml uv.lock .python-version ./
COPY apps/server/pyproject.toml apps/server/
# Dependencies first: this layer only changes with the lock file.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package zendilohub-server --no-install-workspace
COPY apps/server apps/server
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package zendilohub-server --no-editable

# ---- runtime: Python, the virtualenv and the web build; runs as PUID:PGID
FROM python:3.14-slim-bookworm AS runtime
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ZENDILOHUB_PORT=8080 \
    ZENDILOHUB_DATA_DIR=/data \
    ZENDILOHUB_WEB_DIR=/app/web \
    PUID=1000 \
    PGID=1000
WORKDIR /app
COPY --from=python /app/.venv /app/.venv
COPY --from=web /src/apps/web/dist /app/web
COPY docker/entrypoint.sh /usr/local/bin/zendilohub-entrypoint
RUN chmod +x /usr/local/bin/zendilohub-entrypoint && mkdir -p /data
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"ZENDILOHUB_PORT\"]}/health', timeout=4)"
ENTRYPOINT ["zendilohub-entrypoint"]
CMD ["zendilohub", "serve"]
