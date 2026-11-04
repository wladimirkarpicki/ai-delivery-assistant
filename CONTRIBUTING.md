# Contributing to AI Delivery Assistant

Thanks for helping improve this project. This document describes a local development setup, the commands used day to day, and the workflow for database migrations.

## Stack

- Backend: Python 3.13, FastAPI, SQLAlchemy 2.x, Alembic, PyJWT bearer sessions (HS256), Werkzeug password hashing
- Database: PostgreSQL 16
- AI: the OpenRouter HTTP API (the Free Models Router, `openrouter/free`) through httpx, with tenacity retries and pydantic response validation
- Frontend: React 19 with TypeScript, built with Vite, charts with Recharts

## 1. Backend setup

You need Python 3.13 and PostgreSQL 16 available on your machine.

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On macOS and Linux, activate with `source venv/bin/activate` instead of the `Activate.ps1` line.

`requirements.txt` also carries the dev tooling: pytest, coverage, black, and ruff.

## 2. Configure the environment

The `.env` file must never be committed. It is already listed in `.gitignore`; keep it that way and never add a real key, password, or secret to any tracked file.

```powershell
Copy-Item .env.example .env
```

Then fill in real values in `.env`. The application loads this file centrally through `config_loader.py`. Generate a strong signing key for local use:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

If `JWT_SECRET_KEY` is left unset, the app creates an ephemeral key at startup and logs a warning, so every restart invalidates all issued tokens. `TOKEN_TTL_HOURS` (default 12) controls how long a session stays valid.

## 3. Database setup

Create an empty PostgreSQL 16 database once, then apply the version-controlled migrations:

```powershell
python -m alembic -c migrations/alembic.ini upgrade head
```

## 4. Frontend setup

Install the frontend dependencies with the lockfile, from inside `frontend/`:

```powershell
pnpm install --frozen-lockfile
```

Run from the repository root, the same install is `pnpm --dir frontend install --frozen-lockfile`.

Useful scripts:

```powershell
pnpm --dir frontend typecheck
pnpm --dir frontend build
pnpm --dir frontend dev
```

The backend serves the files produced by `build`, so run it once before starting the app locally.

## 5. Run the application

```powershell
python -m uvicorn api:create_app --factory --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. On the first run, create the initial admin account at `/setup`; the endpoint closes itself afterwards. Sign in at `/login` on later visits.

Alternative: run the whole stack with Docker Compose, which also starts PostgreSQL 16:

```powershell
docker compose up -d --build
```

The Docker stack is then available at http://127.0.0.1:8001 (host port 8001 mapped to container port 8000). It initializes its schema from `schema.sql` and does not run Alembic, so use local runs with Alembic for migration development.

## Testing

```powershell
python -m pytest -q
```

The suite currently collects 63 tests. To focus on one area, point pytest at a single file, for example `python -m pytest tests/test_matching.py`.

## Linting and typing

```powershell
ruff check .
python -m black --check .
```

The `ruff.toml` configuration ignores rule B008 because FastAPI's canonical dependency injection places `Depends()` calls in argument defaults.

`mypy` is not part of `requirements.txt`. If you want static type checking, install it separately with `pip install mypy`, then run `mypy .`. Keep new backend code annotated so this stays useful.

## Migration workflow

All schema changes go through Alembic. Never edit a migration that has already been applied anywhere, and never change a model without a matching migration.

1. Update the SQLAlchemy models first.
2. Generate a migration with a descriptive message:
   ```powershell
   python -m alembic -c migrations/alembic.ini revision --autogenerate -m "short description"
   ```
3. Review the generated file in `migrations/versions/` and correct it by hand. Autogenerate does not always cover unique indexes, partial indexes, server defaults, or data backfills.
4. Verify both directions before committing:
   ```powershell
   python -m alembic -c migrations/alembic.ini upgrade head
   python -m alembic -c migrations/alembic.ini downgrade -1
   ```
5. Commit the model change and the migration together.

## Conventions

- Keep HTTP concerns in `api.py`, response schemas in `services/`, and provider details in `providers/` and `router.py`.
- Add tests for behaviour you change, and keep existing tests passing.
- Do not hardcode a model list. The application discovers models from live provider metadata.
- Preserve the split between the AI layer and the database layer: the AI proposes a consolidation plan (CREATE, MERGE, UPDATE, CONFLICT) and `project_memory.py` applies it while recording history events.
- Business endpoints require authentication. New endpoints stay behind the bearer-token dependency unless they are deliberately public, as with `/api/health` and `/api/auth/*`.
- No emoji in code, documentation, comments, or commit messages.
