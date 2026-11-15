# ---- stage 1: build the React SPA ----
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend

# corepack's bundled signature keys cannot verify recent pnpm releases
# ("Cannot find matching keyid" after the signing-key rotation), so
# install pnpm directly with npm instead.
RUN npm install -g pnpm@11.7.0

# Lockfile-first layer for dependency caching. pnpm-workspace.yaml travels
# with the pair: pnpm 11 reads it for build settings (allowBuilds), and the
# frozen-lockfile install was generated with it present, so the install fails
# without it in the build context. ai-inventory-management's Dockerfile
# copies the same trio for the same reason.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
# vite build only (tsc causes false-positive JSX type errors in Docker env)
RUN pnpm exec vite build

# ---- stage 2: FastAPI runtime serving the built SPA ----
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# psycopg (non-binary) talks to PostgreSQL through libpq.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ./*.py ./
COPY providers/ ./providers/
COPY services/ ./services/
# api.py mounts /static at startup; StaticFiles raises if the dir is absent.
COPY static/ ./static/
# The migration chain ships in the image so the container reconciles its own
# schema at startup (R8): schema.sql only runs on a first init, so a volume
# that predates it would otherwise stay behind forever. .dockerignore used to
# exclude migrations/, which is why the running container could not run
# alembic at all.
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app

USER appuser

# python:3.13-slim has no curl; use stdlib urllib for the health probe.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=5)" || exit 1

EXPOSE 8000

# One schema source of truth at startup: the alembic chain (R8). On a fresh
# volume, schema.sql already built the schema and stamped alembic_version at
# the head (d4e7f1a2b3c5), so this step is a no-op - the fresh-boot proof is
# on card t_873e9e73. On an older volume it applies exactly the missing
# revisions instead of leaving the schema silently behind. PYTHONPATH is
# needed because alembic is a console script: its sys.path does not include
# the working directory (uvicorn's does).
CMD ["bash", "-c", "PYTHONPATH=/app alembic upgrade head && exec uvicorn api:create_app --factory --host 0.0.0.0 --port 8000"]
