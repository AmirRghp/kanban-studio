# ---------------------------------------------------------------- frontend
FROM node:24-alpine AS frontend-deps
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM frontend-deps AS frontend-test
COPY frontend/ ./
CMD ["npm", "run", "test:unit"]

FROM frontend-deps AS frontend-build
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- e2e
# The image ships browsers matching @playwright/test, so nothing is downloaded at run
# time. The version here must track the one in frontend/package.json.
FROM mcr.microsoft.com/playwright:v1.58.0-noble AS e2e
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
CMD ["npx", "playwright", "test"]

# ---------------------------------------------------------------- backend
FROM python:3.13-slim AS backend-base
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./

FROM backend-base AS backend-test
RUN uv sync --frozen
COPY backend/app ./app
COPY backend/tests ./tests
CMD ["uv", "run", "--no-sync", "pytest"]

# ---------------------------------------------------------------- app (default)
FROM backend-base AS app
RUN uv sync --frozen --no-dev
COPY backend/app ./app
COPY --from=frontend-build /build/out ./app/static

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
