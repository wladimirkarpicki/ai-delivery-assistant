# Docker runbook — ai-delivery-assistant

Everything needed to build, run, and end-to-end test the dockerized stack on
this host (Windows, 8 GB RAM, i7-3615QM). Written 2026-11-14 for task
t_bdb15fb3; complements the repo README (features) and the audit report
(reports/ai-delivery-assistant-audit.md).

## 0. Prerequisites — the engine must be running

`docker version` must show a **Client** *and* a **Server** section. On this
host the Docker client was installed but WSL had no distribution, so Docker
Desktop could not start ("Docker Desktop is unable to start"). Owner-side fix:

```powershell
wsl --install -d Ubuntu      # elevated shell, then reboot if asked
# start Docker Desktop, wait for the engine
docker version               # must show a Server section
```

`docker compose config` (YAML validation) works without the daemon; every
build/run command below needs it.

## 1. Environment

`.env` is gitignored and never committed; `.env.example` documents every
variable. This clone already has a working `.env` (verified: `docker compose
config` exits 0 with it). On a clean clone:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_hex(16))"   # BOOTSTRAP_TOKEN
# paste generated values; fill NVIDIA_API_KEY from https://build.nvidia.com/
```

`compose.yml` refuses to start with missing required variables
(`${VAR:?...}`): DATABASE_USER / DATABASE_PASSWORD / DATABASE_NAME,
JWT_SECRET_KEY, NVIDIA_API_KEY. BOOTSTRAP_TOKEN gates POST /api/auth/setup
(read it from the app logs when unset).

## 2. Build and run

```bash
docker compose build          # one project at a time on this 8 GB host
docker compose up -d
docker compose ps             # db and app must both be healthy
docker compose logs -f app    # watch startup
```

- App: http://127.0.0.1:8001 (loopback only — /api/auth/setup creates the
  first admin, so the port must not be reachable off-machine).
- Database: postgres:16, no published port (container-to-container only).
  Read it with `docker compose exec db psql -U "$DATABASE_USER" "$DATABASE_NAME"`.
- Health: the image HEALTHCHECK probes http://localhost:8000/api/health
  inside the container; `docker compose ps` shows `State: healthy`.
- Monitoring (opt-in): `docker compose --profile monitoring up -d`
  (Prometheus + Grafana on 127.0.0.1:3001, needs GRAFANA_ADMIN_PASSWORD).

## 3. End-to-end test

The app test suite (tests/) runs on an in-memory SQLite harness — it does not
need the stack (113 passed with a stray `.env` moved aside; see the audit).
E2E means exercising the *running dockerized stack* over HTTP:

```bash
# 0. stack from §2 must be up and healthy
# 1. app-side unit suite (host, no stack needed) — run once per change
python -m pytest -q
# 2. HTTP smoke against the running stack (BOOTSTRAP_TOKEN from .env)
set -a && . ./.env && set +a
python scripts/e2e_smoke.py
# expect: 6 PASS lines and "ALL CHECKS PASSED", exit 0
```

`scripts/e2e_smoke.py` checks, in order: GET /api/health →
POST /api/auth/setup (first admin) → POST /api/auth/login →
GET /api/auth/me → GET /api/projects (authenticated, hits the stack's real
PostgreSQL) → GET / (built SPA served). Stdlib only. `analysis_ready: false`
in the health body is reported, not failed — it only means the NVIDIA route
is not usable and the analysis form degrades.

Extra evidence to capture on a full run:

```bash
docker compose ps                              # healthy state
docker compose logs app | tail -50             # startup, no tracebacks
docker compose exec db psql -U "$DATABASE_USER" "$DATABASE_NAME" -c '\dt'   # schema loaded
```

## 4. Known risks to watch on first boot (from the audit)

1. **schema.sql provenance**: it is a pg_dump **18.4** dump loaded by the
   postgres:16 init mount. No PG18-only syntax was found in it (no jsonb /
   generated / identity / procedure constructs — the `\restrict` line is a
   SQL comment), so it is expected to load, but it is unverified against 16.
   If the `db` container exits during first init, regenerate on PostgreSQL 16:
   dump the schema from the running container and commit the result.
2. **Alembic is orphaned**: schema.sql creates alembic_version with no row and
   the app never runs migrations at startup. Treat schema.sql as the source of
   truth until this is decided (audit work-plan item 3).
3. **A developer `.env` on the host changes test results** — config_loader's
   load_dotenv(override=True) replaces test tokens. For the unit suite, run
   with .env moved aside (that is the 113-pass run, not a defect).

## 5. Teardown / reset

```bash
docker compose down          # stop, keep data
docker compose down -v       # nuclear: drop pgdata_ai2 (first init re-runs schema.sql)
```

## 6. Files

- `Dockerfile` — 2 stages: node:22-alpine builds the SPA (pnpm 11.7, vite
  build), python:3.13-slim serves it via uvicorn (non-root appuser).
  Frontend COPY includes pnpm-workspace.yaml — pnpm 11 reads it for build
  settings and the frozen-lockfile install was generated with it present.
  (Verified natively 2026-11-14: `pnpm install --frozen-lockfile` +
  `pnpm exec vite build` both exit 0.)
- `compose.yml` — db + app + opt-in monitoring profile, pinned project name.
- `scripts/e2e_smoke.py` — the HTTP smoke from §3.