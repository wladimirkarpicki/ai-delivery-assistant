# AI Delivery Assistant

![Security Scan](https://github.com/wladimirkarpicki/ai-delivery-assistant/actions/workflows/security.yml/badge.svg)

AI-powered meeting-notes analyzer for project and delivery management.

The application turns meeting notes into structured project intelligence — including delivery status, risks, blockers, decisions, and action items — and maintains a persistent project memory across meetings.

The project is designed around a practical delivery-management problem: **the same project information can be described differently by different AI runs or models, so extracted information needs to be reconciled before it becomes current project state.**

## Screenshots

The cross-project dashboard, in both themes:

<p align="center">
  <img src="docs/dashboard-light.png" width="49%" alt="The metrics dashboard in the light theme">
  <img src="docs/dashboard-dark.png" width="49%" alt="The metrics dashboard in the dark theme">
</p>

## Features

- AI analysis of project meeting notes
- Light and dark themes — system-aware by default, with a manual toggle
- OpenRouter provider — all analysis runs through the Free Models Router, no model selection
- AI provider retry (3 attempts with exponential backoff) via `tenacity`
- Dynamic model discovery from live provider APIs (no hardcoded model list)
- Environment-based API key configuration (centralized loader)
- PDF, DOCX, TXT, and Markdown uploads
- Pasted meeting notes
- Structured analysis of:
  - project status
  - progress
  - risks
  - blockers
  - decisions
  - action items
- Persistent project memory backed by PostgreSQL
- AI-driven memory consolidation
- Deterministic pre-matching: exact title duplicates are resolved without the LLM; remaining findings carry a candidate shortlist
- Semantic candidate matching: item and finding title embeddings (bge-m3 via OpenRouter) rank candidates by cosine similarity, so paraphrases with no shared words still reach the LLM as candidates; falls back to lexical similarity if embeddings are unavailable
- Canonical titles as item identity: one row per title per project (enforced by unique indexes); resolved items reopen instead of duplicating
- Idempotent uploads: submitting identical meeting notes is a no-op with an explicit warning
- Review queue: findings the consolidation guardrails reject are surfaced for explicit resolution (create, link to existing, or dismiss) — never silently dropped
- Meeting detail page renders the parsed AI analysis: status, executive summary, progress, milestones, and every finding with its details
- Manual item resolution: resolve/reopen risks and blockers, complete/reopen action items directly from the project overview — no meeting required; every action is recorded as a history event
- Status report export: one-click Markdown report (page view or `.md` download) covering delivery status, progress, open and resolved work, decisions, and a counts summary
- Consolidation decisions for new findings:
  - **CREATE** — genuinely new information
  - **MERGE** — same underlying information with different wording
  - **UPDATE** — existing item with changed information
  - **CONFLICT** — new information contradicts existing memory
- Immutable meeting records containing the original input and AI analysis
- Cross-project dashboard: every project at a glance - delivery status, progress, open risk/blocker/action counts, meeting count, and last meeting date
- Cross-project metrics dashboard: KPI totals (projects, meetings, decisions, open work) and charts built with recharts - projects by delivery status, open items mix, meetings and open work per project, risks by impact (open vs resolved), a monthly activity timeline, and action items by owner, themed light/dark like the rest of the app
- History page with type filters (per-type counts), links from every event to its meeting, and before/after field diffs for changes
- Immutable history events for memory changes
- JSON API served by FastAPI behind the unchanged UI; validation failures surface as structured error notices
- Custom 404 and 500 error pages
- Environment-based API key configuration

## Project memory architecture

Each project has three complementary layers:

### 1. Meetings — source records

Meetings are retained as the original source of information. A meeting stores:

- uploaded or pasted meeting text
- source filename, when applicable
- provider and model used
- raw AI analysis
- parsed analysis JSON

This preserves the original AI output even when the current project state changes later.

### 2. Current project memory — operational state

The application maintains the current state of:

- open risks
- open blockers
- open action items
- project status and progress
- project decisions

### 3. History — audit trail

Memory changes are recorded as immutable history events linked to the meeting that caused them.

Events can record creation, updates, completion/resolution, merges, and conflicts.

The goal is to keep the current project state useful for delivery management without losing the historical context that produced it.

## AI memory consolidation

When new meeting notes are processed, the application does not simply append every extracted item to the database.

The current flow is:

```text
Meeting notes
     |
     v
AI analysis
     |
     v
Deterministic pre-match
(exact title duplicates resolved)
     |
     v
Existing memory + findings
with candidate shortlists
     |
     v
MemoryConsolidator
     |
     +---- CREATE ----> create new memory item
     |
     +---- MERGE -----> keep existing item, record merge
     |
     +---- UPDATE ----> update existing item
     |
     +---- CONFLICT --> preserve existing item, record conflict
     |
     v
Project memory + history
```

Before anything reaches the LLM, `matching.py` resolves findings that exactly match an existing item's canonical title — including resolved and completed items: unchanged duplicates become MERGE entries, explicit status changes become UPDATE entries (closing or reopening), and duplicate decisions merge into the existing append-only record, all without an LLM call. The remaining findings go to `MemoryConsolidator` annotated with a `candidate_ids` shortlist of similar existing items, which keeps the model from inventing ids. Candidates are ranked semantically: item titles carry a stored embedding (baai/bge-m3 via the OpenRouter embeddings endpoint, backfilled lazily on the next meeting after an item is created), each new meeting's finding titles are embedded in one batched call, and candidates are ordered by cosine similarity. When embeddings are unavailable the ranking falls back to lexical token overlap. After the plan returns, CREATE entries that collide with an existing canonical title are downgraded to MERGE.

Every memory item stores a `canonical_title` identity column, and partial unique indexes enforce one row per canonical title per project. Re-submitting identical meeting notes is rejected before any AI call, so repeated uploads never mutate memory twice.

`MemoryConsolidator` uses the selected AI provider/model to compare new findings with the existing project memory. Its output is then applied by `project_memory.py`, which keeps the database changes and history events separate from the AI decision layer.

This separation is intentional: the AI proposes a consolidation plan, while the application remains responsible for applying that plan to the database.

### Current limitation

Title normalization, canonical titles, fuzzy and embedding-based candidate shortlists are deterministic, but the final CREATE/MERGE/UPDATE/CONFLICT decision is still **LLM-based**. Because LLM output is probabilistic, semantically equivalent items can still occasionally be classified as `CREATE` when the model fails to recognize them as such — even when the semantic layer puts the right item in the candidate list.

For example:

```text
Review Memory Relevance
Project Memory Relevance Review
```

These may represent the same action even when the model fails to recognize them as such.

## Supported models

The application always analyzes meetings with the **Free Models Router** (`openrouter/free`), which automatically selects a suitable free model for each request. There is no model selection in the interface.

### Dynamic model discovery

Free-tier models are fetched live from the OpenRouter API (`router.get_models()`), but only as a health check: the add-meeting form warns early if the provider or the router is unavailable. No hardcoded model list is used.

## Architecture

```text
                         +------------------+
                         |  React SPA (Vite)|
                          +---------+--------+
                                    |
                                    v
                          +------------------+
                          | FastAPI JSON API |
                         +---------+--------+
                                   |
                                   v
                         +------------------+
                         | Meeting ingestion|
                         +---------+--------+
                                   |
                                   v
                         +------------------+
                         | Document parser  |
                         +---------+--------+
                                   |
                                   v
                         +------------------+
                         | AI Analyzer       |
                         +---------+--------+
                                   |
                                   v
                         +------------------+
                         | ModelRouter       |
                         +----+---------+----+
                                   |
                                   v
                         +------------------+
                         |  OpenRouter API  |
                         +---------+--------+
                                   |
                                   v
                         +------------------+
                         | MemoryConsolidator|
                         +---------+--------+
                                   |
                         CREATE / MERGE /
                         UPDATE / CONFLICT
                                   |
                                   v
                         +------------------+
                         | Project memory   |
                         | PostgreSQL       |
                         +---------+--------+
                                   |
                                   v
                         +------------------+
                         | History events   |
                         +------------------+
```

## Project structure

```text
api.py                 FastAPI application: JSON API, static assets, SPA fallback
frontend/              React + TypeScript SPA (Vite) rendering the same UI
analyzer.py            Meeting-note analysis prompt and orchestration
config.py              Default provider and model configuration
database.py            SQLAlchemy and migration configuration
models.py              PostgreSQL project-memory models
project_memory.py      Current-state reconciliation and database history
memory_consolidator.py AI-driven memory consolidation
matching.py           Deterministic pre-matching, semantic and lexical candidate shortlists
document_parser.py     PDF, DOCX, TXT, and Markdown extraction
config_loader.py       Centralized .env loader
services/              AI response schemas (`schema_models.py`)
router.py              Provider routing and model discovery
providers/             OpenRouter client implementation
static/                Untouched design assets (tokens.css, styles.css)

migrations/            Alembic database migrations
tests/                 Application tests
```

## Technology stack

- **Python**
- **FastAPI** (JSON API, static assets, SPA fallback)
- **SQLAlchemy** 2.x
- **React 19 + TypeScript** (Vite build; no UI framework - pages render the original markup and classes)
- **Geist / Geist Mono** - the UI typefaces, self-hosted as woff2 in `static/fonts/` (no external font CDN)

- **Alembic**
- **PostgreSQL**
- **httpx** for the OpenRouter REST API
- **python-docx** for DOCX extraction
- **pypdf** for PDF extraction
- **tenacity** for AI provider retry logic
- **pydantic** for AI response schema validation

## Installation

Create and activate a virtual environment:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

Install dependencies (including dev: `black`, `ruff`, `pytest`, `coverage`, ``):

```powershell
pip install -r requirements.txt
# Or install dev tools separately
pip install black ruff pytest coverage 
```

Create `.env` file (loaded centrally via `config_loader.py`):

```text
OPENROUTER_API_KEY=your_openrouter_api_key
DATABASE_URL=postgresql+psycopg://user:password@localhost/ai-delivery-assistant

```

Do not commit `.env` or API keys.

## Database setup

Create the PostgreSQL database once if it does not already exist.

Apply the version-controlled schema migrations:

```powershell
python -m alembic -c migrations/alembic.ini upgrade head
```

## Docker quickstart

The fastest way to run the full stack (FastAPI + built React SPA + PostgreSQL):

```powershell
docker compose up -d --build
```

Open http://127.0.0.1:8001

- `db`: PostgreSQL 16 with the persistent `pgdata_ai2` volume; the schema is created from `schema.sql` on first start
- `app`: the FastAPI application serving the JSON API, the untouched static/ design assets, and the built React SPA on host port 8001, with a container healthcheck on `/api/health`

The Alembic migrations in `migrations/` are for local runs without Docker (see [Database setup](#database-setup)); the Docker stack initializes its schema from `schema.sql` and does not run Alembic.

## Run locally

Build the frontend once (pnpm): see frontend/ (pnpm --dir frontend install, then pnpm --dir frontend build).

Start the FastAPI application (it serves the JSON API, the untouched static/ design assets, and the built React bundle):

```powershell
python -m uvicorn api:create_app --factory --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Then:

1. On first run, create the initial admin account on the setup page (see [Authentication](#authentication)); afterwards sign in.
2. Create a project.
3. Add a meeting.
4. Upload a PDF/DOCX/TXT/Markdown file or paste meeting notes.
5. Review the extracted project state and memory changes.

## Authentication

Every business endpoint requires a signed-in account; sessions are stateless JWTs (HS256, PyJWT) carried as `Authorization: Bearer <token>` headers.

**First-time setup.** While the `users` table is empty, `POST /api/auth/setup` (the `/setup` page in the UI) creates the initial admin account and closes itself afterwards — a second bootstrap attempt is refused with `400 Setup is already completed.` The setup page then sends the visitor to `/login` if it is ever opened again.

**Roles.** Two roles exist: `admin` and `user`.

- Both roles read and write the delivery workspace (projects, meetings, history, reports, review queue, metrics).
- Only admins manage accounts: `GET/POST /api/users`, `PATCH/DELETE /api/users/{id}`, `POST /api/users/{id}/password` (403 for regular users). The admin area is the `/users` page.
- Guardrails: you cannot delete yourself, and the last remaining admin cannot be demoted or deleted (400).
- Everyone can change their own password via `POST /api/auth/password` (`/password` page); the current password is required.

**Sessions and security.**

- Tokens embed `sub`/`username`/`exp` and live `TOKEN_TTL_HOURS` (default 12). The account is re-read from the database on every request, so deleting an account revokes its tokens immediately (ghost sessions are impossible).
- Passwords are stored as Werkzeug hashes (`generate_password_hash`/`check_password_hash`); the raw password is never stored or logged.
- Login rate limiting: 5 failed attempts per username lock that username for 15 minutes (HTTP 429). In-memory, per process.
- `JWT_SECRET_KEY` (from `.env` / environment) signs the tokens; set a strong random value in production (`python -c "import secrets; print(secrets.token_hex(32))"`). If it is not set, the app generates an ephemeral key at startup and logs a warning — the API keeps working (the Docker healthcheck does not depend on `.env`), but tokens reset on every restart.
- Public endpoints without authentication: `/api/health` (the Docker healthcheck) and `/api/auth/*` (setup/login/me/password). Everything else answers `401` without a valid token; admin-only endpoints answer `403` for regular users.

## Testing

Run the application test suite with:

```powershell
python -m pytest tests/test_api.py
```

The repository also includes independent development/testing code for the memory consolidation layer as that feature evolves.

## Demo data

An idempotent seed script fills the Docker dev database with demo delivery data, so the dashboard has something meaningful to show:

```powershell
Get-Content -Raw scripts\seed_demo_data.py | docker compose exec -T app python -
```

```sh
docker compose exec -T app python - < scripts/seed_demo_data.py
```

What it does:

- Creates three `Demo ·` projects — **Customer Portal Redesign** (on track), **Data Platform Migration** (at risk), and **Mobile App Launch** (blocked) — each with 5-7 meetings spread evenly over May-October 2026, risks by impact (roughly 60% open / 40% resolved), blockers, action items with owners and due dates, decisions, and the matching creation history events.
- Upserts a `ProjectState` (delivery status, progress summary, completed/in-progress items) for the five smoke-test projects: *OpenRouter Smoke Test* and *Pre-Match Smoke Test* → delivered, *Duplicate Scenarios Test* and *C4 Semantic Test* → on track, *Test Project* → at risk.
- Re-running is safe: previously seeded `Demo ·` rows are deleted first (history events → items → states → meetings → projects) and then recreated; the smoke-test projects keep their existing rows and only get a refreshed state.
- Real projects (e.g. `inventory-management-system`, `ai-delivery-assistant`) are never touched.

## Design principles

The project intentionally separates three responsibilities:

1. **AI extraction** — determine what the meeting says.
2. **AI consolidation** — determine how new findings relate to existing project memory.
3. **Database application** — apply the selected decision safely and preserve an audit trail.

This separation makes the consolidation logic testable independently from the HTTP layer and database workflow, and allows the reconciliation strategy to evolve without replacing the underlying project-memory model.

## Roadmap

Planned improvements include:

- expanded automated tests for semantic duplicate scenarios

## Status

This is an actively developed project exploring practical AI-assisted project and delivery management.

The current implementation is suitable for local development and experimentation. It should not be considered production-ready without additional security, observability, reliability, and evaluation work.
