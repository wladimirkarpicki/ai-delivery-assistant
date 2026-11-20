# ai-delivery-assistant STATUS

**State: FROZEN (2026-11-19)** at `main` @ `761825f`, all 11 required checks green (verified 2026-11-19T20:14Z+). Frozen by freeze card t_5ca2291a after the retro-freeze audit (run 20) and the native full-stack e2e pass.

This file is the freeze state document: frozen commit, CI truth, final versions, known issues, and how to reboot the stack. It is the one repo mutation the freeze card was allowed to make; no code changed.

## Freeze program (what got us here)

- **Audit** (card t_a98bd127, run 20, at HEAD ef0fe99): verdict at the time "blockers open, not freeze-ready" — #41 pnpm-audit gate red (picomatch ReDoS, no patched version), #42 R1/R2/R8 fixes stuck on divergent unmerged branches, R1/R2/R8 themselves open on main. 13 findings filed as issues #41-#53. Full report + gate logs on the card.
- **E2E** (card t_c6d6f2e7): native full-stack pass, repo untouched. Findings: #54 (Docker host blocker), #55 (NVIDIA_API_KEY rejected for inference), #56 (SPA auth/me request loop). Evidence on the card.
- **Remediation wave**: #41-#46 and #48-#56 closed on main with evidence. PR #57 (codeql action SHA pinning) and PR #59 (schema reconcile: R1/R2/R8 + R3/R7) merged, 11/11 checks green.
- **This freeze commit**: STATUS.md only.

## Frozen state (verified 2026-11-19)

- HEAD `761825f` == `origin/main`, clean tree. All 11 required checks success: Tests (Pytest), Code Quality (Ruff), Type Checking (Mypy), Static Analysis (Bandit), Dependency Scan (Safety), Frontend Audit (pnpm audit), Migrations (Alembic), Frontend Typecheck and Build, CodeQL Analyze (python), Analyze (javascript-typescript), Analyze (actions). Workflow runs: Security Scan #183, CodeQL #6.
- Tests: backend 116 passed with a developer `.env` present (91% coverage; the harness is immune to it, see tests/conftest.py); frontend vitest 27 passed; `scripts/e2e_smoke.py` 6/6 against a live stack.
- Data layer: `schema.sql` regenerated on PostgreSQL 16 (the pg_dump 18.4 VERSION-MISMATCH header is gone), alembic head `d4e7f1a2b3c5` stamped after load, and the Dockerfile CMD runs `alembic upgrade head` before uvicorn (R8 closed).
- Security gates clean: ruff, the 12-module mypy gate, bandit (High 0), safety, pip-audit; no secrets in 230+ commits of history.

## Final versions

- Backend pins (`requirements.txt`): fastapi 0.162.7, uvicorn 0.54.0, PyJWT 2.15.1, Werkzeug 3.1.9, SQLAlchemy 2.1.8, psycopg[binary] 3.3.9, alembic 1.19.1, httpx 0.28.1, tenacity 9.1.4, pydantic 2.14.3, pydantic-settings 2.9.0, pypdf 7.1.0, python-docx 1.2.0.
- Dev/CI pins (`requirements-dev.txt`): pytest 9.1.1, pytest-cov 7.1.0, coverage 7.17.3, ruff 0.17.5, mypy 2.4.1, bandit 1.9.4, safety 3.8.1, git-filter-repo 2.47.0.
- Frontend (`frontend/package.json`): react/react-dom 19.3.x, react-router-dom 7.18.x, recharts 3.10.x, vite 8.3.8, vitest 5.1.x, typescript 7.0.x, jsdom 31.0.1, @testing-library/jest-dom 7.0.1.
- Images (`Dockerfile`, `compose.yml`): app python:3.13-slim, frontend build node:22-alpine, db postgres:16, monitoring prom/prometheus:v3.15.0 + grafana/grafana:13.2.4.
- Runtime: Python 3.13 (app image), PostgreSQL 16, Node 22 for the frontend build only.

## Known issues at freeze (open)

- **#47 [low]** coverage raise on project_memory / router / nvidia_provider / document_parser: in flight at freeze time (card t_56fc786d); **resolved after the freeze** by PR #61 on branch `47-coverage-weakest-surfaces` — 72 new tests, suite 116 -> 188 passed with a developer `.env` present, module coverage project_memory 68->99%, router 65->100%, nvidia_provider 70->98%, document_parser 73->99%, total 91->96%; production code unchanged, no coverage threshold added. The audit verdict classed this as follow-up, not a freeze blocker.
- **#50 [low]** branch protection does not require PR reviews, so direct pushes to main are possible. Owner policy decision.
- **#51 [low]** CSP `style-src` still carries 'unsafe-inline': the fix is fully specced but its card is stuck in a dispatcher crash loop (sec-profile worker transport, 18 crashes, no work ever started). The card cannot be archived from inside a worker dispatch context (the CLI refuses it), so archiving it is an operator action for the owner session. Re-dispatch the work after the transport is healthy; the full spec survives in the card thread.
- **PR #58 (open)**: documented one-advisory pnpm exception for GHSA-fc5q-39xc-vjpf. The audit gate is green at 761825f without it; keep it ready in case the advisory resurfaces.
- **Local-only branch `55-health-analysis-ready`** (5 commits, unpushed): makes `/api/health`'s analysis_ready honest (issue #55 closed on that basis; the NVIDIA key itself remains owner-side). Push / PR / archive it as a post-freeze decision.
- **Host limits**: the Docker engine is unavailable on the freeze host (WSL had no distribution, issue #54, owner-side), so the compose boot was verified natively on a real PostgreSQL 16.10; the meeting-analysis happy path cannot run end-to-end because NVIDIA_API_KEY is rejected with 401 (issue #55).

## How to reboot the stack

1. Docker engine must show a Server: on this host `wsl --install -d Ubuntu` + reboot, then start Docker Desktop (issue #54).
2. `cp .env.example .env`; generate JWT_SECRET_KEY (`python -c "import secrets; print(secrets.token_hex(32))"`) and BOOTSTRAP_TOKEN (`token_hex(16)`); set DATABASE_USER / DATABASE_PASSWORD / DATABASE_NAME and NVIDIA_API_KEY. `compose.yml` refuses to start with any of them missing.
3. `docker compose build && docker compose up -d`; app on http://127.0.0.1:8001 (loopback only, `/api/auth/setup` creates the first admin), db postgres:16 with no published port. `docker compose ps` shows both healthy; the app stamps/migrates the schema (`alembic upgrade head`) before uvicorn starts.
4. Verify: `docker compose logs -f app`, then `python scripts/e2e_smoke.py` against 127.0.0.1:8001 (6/6 checks). Monitoring (optional): `docker compose --profile monitoring up -d` (Grafana on 127.0.0.1:3001).
5. Tests without the stack: `python -m pytest -q --cov=. --cov-report=term-missing` from the repo root; a developer `.env` no longer breaks the suite (tests/conftest.py). Full runbook: `docs/DOCKER-RUNBOOK.md`.

## Archive state

The repository is NOT archived. Archiving requires owner approval; the approval ask (recommendation: hold until #47 lands and #50 is decided) is filed as a GitHub issue at freeze time. Evidence: audit card t_a98bd127 (comments + attachments), e2e card t_c6d6f2e7 (comments), board ai-delivery-assistant, freeze card t_5ca2291a.