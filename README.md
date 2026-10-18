# AI Delivery Assistant

AI-powered meeting-notes analyzer for project and delivery management.

The application turns meeting notes into structured project intelligence вЂ” including delivery status, risks, blockers, decisions, and action items вЂ” and maintains a persistent project memory across meetings.

The project is designed around a practical delivery-management problem: **the same project information can be described differently by different AI runs or models, so extracted information needs to be reconciled before it becomes current project state.**

## Features

- AI analysis of project meeting notes
- Light and dark themes вЂ” system-aware by default, with a manual toggle
- OpenRouter provider вЂ” all analysis runs through the Free Models Router, no model selection
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
- Review queue: findings the consolidation guardrails reject are surfaced for explicit resolution (create, link to existing, or dismiss) вЂ” never silently dropped
- Meeting detail page renders the parsed AI analysis: status, executive summary, progress, milestones, and every finding with its details
- Manual item resolution: resolve/reopen risks and blockers, complete/reopen action items directly from the project overview вЂ” no meeting required; every action is recorded as a history event
- Status report export: one-click Markdown report (page view or `.md` download) covering delivery status, progress, open and resolved work, decisions, and a counts summary
- Consolidation decisions for new findings:
  - **CREATE** вЂ” genuinely new information
  - **MERGE** вЂ” same underlying information with different wording
  - **UPDATE** вЂ” existing item with changed information
  - **CONFLICT** вЂ” new information contradicts existing memory
- Immutable meeting records containing the original input and AI analysis
- Cross-project dashboard: every project at a glance - delivery status, progress, open risk/blocker/action counts, meeting count, and last meeting date
- History page with type filters (per-type counts), links from every event to its meeting, and before/after field diffs for changes
- Immutable history events for memory changes
- JSON API served by FastAPI behind the unchanged UI; validation failures surface as structured error notices
- Custom 404 and 500 error pages
- Environment-based API key configuration

## Project memory architecture

Each project has three complementary layers:

### 1. Meetings вЂ” source records

Meetings are retained as the original source of information. A meeting stores:

- uploaded or pasted meeting text
- source filename, when applicable
- provider and model used
- raw AI analysis
- parsed analysis JSON

This preserves the original AI output even when the current project state changes later.

### 2. Current project memory вЂ” operational state

The application maintains the current state of:

- open risks
- open blockers
- open action items
- project status and progress
- project decisions

### 3. History вЂ” audit trail

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

Before anything reaches the LLM, `matching.py` resolves findings that exactly match an existing item's canonical title вЂ” including resolved and completed items: unchanged duplicates become MERGE entries, explicit status changes become UPDATE entries (closing or reopening), and duplicate decisions merge into the existing append-only record, all without an LLM call. The remaining findings go to `MemoryConsolidator` annotated with a `candidate_ids` shortlist of similar existing items, which keeps the model from inventing ids. Candidates are ranked semantically: item titles carry a stored embedding (baai/bge-m3 via the OpenRouter embeddings endpoint, backfilled lazily on the next meeting after an item is created), each new meeting's finding titles are embedded in one batched call, and candidates are ordered by cosine similarity. When embeddings are unavailable the ranking falls back to lexical token overlap. After the plan returns, CREATE entries that collide with an existing canonical title are downgraded to MERGE.

Every memory item stores a `canonical_title` identity column, and partial unique indexes enforce one row per canonical title per project. Re-submitting identical meeting notes is rejected before any AI call, so repeated uploads never mutate memory twice.

`MemoryConsolidator` uses the selected AI provider/model to compare new findings with the existing project memory. Its output is then applied by `project_memory.py`, which keeps the database changes and history events separate from the AI decision layer.

This separation is intentional: the AI proposes a consolidation plan, while the application remains responsible for applying that plan to the database.

### Current limitation

Title normalization, canonical titles, fuzzy and embedding-based candidate shortlists are deterministic, but the final CREATE/MERGE/UPDATE/CONFLICT decision is still **LLM-based**. Because LLM output is probabilistic, semantically equivalent items can still occasionally be classified as `CREATE` when the model fails to recognize them as such вЂ” even when the semantic layer puts the right item in the candidate list.

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

1. Create a project.
2. Add a meeting.
3. Upload a PDF/DOCX/TXT/Markdown file or paste meeting notes.
4. Review the extracted project state and memory changes.

## Testing

Run the application test suite with:

```powershell
python -m unittest discover -s tests
```

The repository also includes independent development/testing code for the memory consolidation layer as that feature evolves.

## Design principles

The project intentionally separates three responsibilities:

1. **AI extraction** вЂ” determine what the meeting says.
2. **AI consolidation** вЂ” determine how new findings relate to existing project memory.
3. **Database application** вЂ” apply the selected decision safely and preserve an audit trail.

This separation makes the consolidation logic testable independently from the HTTP layer and database workflow, and allows the reconciliation strategy to evolve without replacing the underlying project-memory model.

## Roadmap

Planned improvements include:

- expanded automated tests for semantic duplicate scenarios

## Status

This is an actively developed project exploring practical AI-assisted project and delivery management.

The current implementation is suitable for local development and experimentation. It should not be considered production-ready without additional security, observability, reliability, and evaluation work.
