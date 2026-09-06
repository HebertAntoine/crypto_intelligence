# Crypto Intelligence - single-image web app.
#
# The React frontend is built first, then copied into the Python image, which
# serves both the API and the UI from one origin. One origin means no CORS
# configuration in production and no second web server to run.
#
# This image performs market ANALYSIS only. It never places orders.

# --- stage 1: build the frontend ----------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build
# Copy manifests first so the dependency layer is cached across code edits.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# --- stage 2: python runtime --------------------------------------------
FROM python:3.13-slim AS runtime

# Fail fast and log immediately rather than buffering behind a crash.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# curl serves the container healthcheck. No compiler is installed: every
# dependency resolves to a prebuilt wheel on linux/amd64, which keeps the
# image roughly 300 MB smaller. If you build for an architecture without
# wheels, add build-essential here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY backend/ ./backend/
RUN pip install --upgrade pip \
    && pip install . \
    && rm -rf build *.egg-info

COPY config/ ./config/
COPY --from=frontend /build/dist ./frontend/dist

# Writable state lives here. Mount a volume over it to keep data across
# rebuilds - without one, every redeploy starts from an empty database.
RUN mkdir -p data/cache data/research data/exports data/shadow data/imports knowledge

# Run as a non-root user: the container needs no privileges.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8100

# 0.0.0.0 inside the container; publish it behind a reverse proxy, not directly.
ENV API_HOST=0.0.0.0 \
    API_PORT=8100 \
    ENV=production

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8100/api/health || exit 1

CMD ["uvicorn", "crypto_intel.main:app", "--host", "0.0.0.0", "--port", "8100"]
