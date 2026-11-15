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
need the stack (116 passed with a developer `.env` in place; the harness keeps
it out of the test process, see tests/conftest.py).
E2E means exercising the *running dockerized stack* over HTTP:

```bash
# 0. stack from §2 must be up and healthy
# 1. app-side unit suite — run once per change. The host path only works if
#    the host python has the requirements installed (the Hermes-managed
#    python does not ship pytest). Verified path, no host deps: run inside
#    the image — requirements.txt ships pytest itself:
docker compose cp tests app:/tmp/aida-tests
docker compose cp frontend/index.html app:/app/frontend/index.html
docker compose exec -T -w /app app python -m pytest /tmp/aida-tests -q -p no:cacheprovider
#    Use a fresh path (/tmp/aida-tests), NOT /app/tests: an earlier in-container
#    test pass leaves /app/tests behind, and `docker compose cp tests
#    app:/app/tests` then nests into /app/tests/tests — pytest collection dies
#    with "import file mismatch". Verified 2026-11-15 (run 50): 116 passed,
#    exit 0 via the /tmp path.
#    One test (test_csp_pins_the_one_inline_script_by_hash) reads
#    frontend/index.html, which the image does not ship by design; without
#    the second cp it fails with FileNotFoundError. That failure is an
#    image-content gap, not a code defect (it passes on the host and with
#    the source copied in).
# 2. HTTP smoke against the running stack (BOOTSTRAP_TOKEN from .env)
set -a && . ./.env && set +a
python scripts/e2e_smoke.py
# expect: 6 PASS lines and "ALL CHECKS PASSED", exit 0
```

**The smoke assumes a fresh database.** POST /api/auth/setup is
first-user-wins: if the `users` table already has a row (a previous run, or
another probe — e.g. owner-side W1 probe admins named
`admin_w1-<timestamp>`), setup correctly answers `400 Setup is already
completed` and the smoke's login then 401s for the nonexistent smoke user.
That is correct app behavior, not a smoke failure; to re-verify fresh-boot
behavior deliberately, reset with `docker compose down -v` (drops
pgdata_ai2 — the data in it goes away).

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

1. **schema.sql provenance — REGENERATED on PG16 2026-11-15 (card t_873e9e73,
   finding R1)**. The old file was a pg_dump 18.4 dump (VERSION-MISMATCH
   header) loaded by the postgres:16 init mount; it also created
   `revoked_tokens` without the model's primary key and left
   `alembic_version` empty. It is now a pg_dump 16.16 of head state built
   from the app's own migration chain, and it carries exactly one
   `alembic_version` row — the head `d4e7f1a2b3c5` (finding R2). Verified
   by a clean-volume boot (`docker compose down -v`, `up -d`): the db logs
   the `running /docker-entrypoint-initdb.d/schema.sql` first-init, every
   CREATE TABLE/SEQUENCE follows, and the stack comes up healthy.
2. **Schema bootstrap at startup (finding R8)**: the app container runs
   `alembic upgrade head` before uvicorn (Dockerfile CMD; `migrations/`
   and `alembic.ini` ship in the image — `.dockerignore` used to exclude
   them). On a fresh volume the step is a no-op (the dump already stamped
   the head — `alembic current` reports `d4e7f1a2b3c5 (head)` and
   `alembic upgrade head` replays 0 revisions); on an older volume it
   applies the missing revisions instead of leaving the schema behind.
   Never wire `Base.metadata.create_all` as well: two bootstrap paths
   drift apart silently, and a dump/migration mismatch is exactly how
   `revoked_tokens` lost its PK.
3. **A developer `.env` on the host no longer changes test results** — tests/
   conftest.py neutralises the loader for the test process so the pinned
   tokens survive, the production override path is unchanged, and the
   contract is pinned by tests/test_config_loader.py.

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
- The image does NOT ship `tests/` or `frontend/index.html` (production
  runtime needs neither) — see §3 for the in-container test path.
- Verified on this host 2026-11-15 (task t_bdb15fb3): `docker compose build`
  exit 0 (frontend vite build + backend pip install), `docker compose up -d`
  → db + app healthy, e2e smoke 6/6 PASS against the running stack, pytest
  in-container green with the tests copied in. Re-verified live in run 50
  (2026-11-15): stack still up and healthy (app + db, 0 tracebacks in logs),
  HTTP probes 200 on / /health /api/health /docs /openapi.json, in-container
  pytest 116 passed via the /tmp copy path above.