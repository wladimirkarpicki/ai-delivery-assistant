# AI Delivery Assistant

AI-powered meeting-notes analyzer for project and delivery management.

The application turns meeting notes into structured project intelligence — including delivery status, risks, blockers, decisions, and action items — and maintains a persistent project memory across meetings.

The project is designed around a practical delivery-management problem: **the same project information can be described differently by different AI runs or models, so extracted information needs to be reconciled before it becomes current project state.**

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
- Canonical titles as item identity: one row per title per project (enforced by unique indexes); resolved items reopen instead of duplicating
- Idempotent uploads: submitting identical meeting notes is a no-op with an explicit warning
- Review queue: findings the consolidation guardrails reject are surfaced for explicit resolution (create, link to existing, or dismiss) — never silently dropped
- Consolidation decisions for new findings:
  - **CREATE** — genuinely new information
  - **MERGE** — same underlying information with different wording
  - **UPDATE** — existing item with changed information
  - **CONFLICT** — new information contradicts existing memory
- Immutable meeting records containing the original input and AI analysis
- Immutable history events for memory changes
- CSRF protection on all forms (Flask-WTF)
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

Before anything reaches the LLM, `matching.py` resolves findings that exactly match an existing item's canonical title — including resolved and completed items: unchanged duplicates become MERGE entries, explicit status changes become UPDATE entries (closing or reopening), and duplicate decisions merge into the existing append-only record, all without an LLM call. The remaining findings go to `MemoryConsolidator` annotated with a `candidate_ids` shortlist of similar existing items, which keeps the model from inventing ids. After the plan returns, CREATE entries that collide with an existing canonical title are downgraded to MERGE.

Every memory item stores a `canonical_title` identity column, and partial unique indexes enforce one row per canonical title per project. Re-submitting identical meeting notes is rejected before any AI call, so repeated uploads never mutate memory twice.

`MemoryConsolidator` uses the selected AI provider/model to compare new findings with the existing project memory. Its output is then applied by `project_memory.py`, which keeps the database changes and history events separate from the AI decision layer.

This separation is intentional: the AI proposes a consolidation plan, while the application remains responsible for applying that plan to the database.

### Current limitation

Title normalization, canonical titles, and fuzzy candidate shortlists are deterministic and already catch exact duplicates, but the final CREATE/MERGE/UPDATE/CONFLICT decision is still **LLM-based**. Because LLM output is probabilistic, semantically equivalent items can still occasionally be classified as `CREATE` when their wording is sufficiently different.

For example:

```text
Review Memory Relevance
Project Memory Relevance Review
```

These may represent the same action even when the model fails to recognize them as such.

An embedding-based semantic similarity layer is a planned direction for making consolidation more robust and idempotent.

## Supported models

The application always analyzes meetings with the **Free Models Router** (`openrouter/free`), which automatically selects a suitable free model for each request. There is no model selection in the interface.

### Dynamic model discovery

Free-tier models are fetched live from the OpenRouter API (`router.get_models()`), but only as a health check: the add-meeting form warns early if the provider or the router is unavailable. No hardcoded model list is used.

## Architecture

```text
                         +------------------+
                         |   Flask Web UI   |
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
app.py                 Flask routes and web UI entry point
analyzer.py            Meeting-note analysis prompt and orchestration
config.py              Default provider and model configuration
database.py            SQLAlchemy and migration configuration
models.py              PostgreSQL project-memory models
project_memory.py      Current-state reconciliation and database history
memory_consolidator.py AI-driven memory consolidation
matching.py           Deterministic pre-matching and candidate shortlists
document_parser.py     PDF, DOCX, TXT, and Markdown extraction
config_loader.py       Centralized .env loader
services/              AI response schemas (`schema_models.py`)
router.py              Provider routing and model discovery
providers/             OpenRouter client implementation
templates/             Flask HTML templates
static/                CSS
migrations/            Alembic database migrations
tests/                 Application tests
```

## Technology stack

- **Python**
- **Flask**
- **Flask-SQLAlchemy**
- **Flask-Migrate / Alembic**
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

Install dependencies (including dev: `black`, `ruff`, `pytest`, `coverage`, `flask-wtf`):

```powershell
pip install -r requirements.txt
# Or install dev tools separately
pip install black ruff pytest coverage flask-wtf
```

Create `.env` file (loaded centrally via `config_loader.py`):

```text
OPENROUTER_API_KEY=your_openrouter_api_key
DATABASE_URL=postgresql+psycopg://user:password@localhost/ai-delivery-assistant
FLASK_SECRET_KEY=replace-this-in-production
```

Do not commit `.env` or API keys.

## Database setup

Create the PostgreSQL database once if it does not already exist.

Apply the version-controlled schema migrations:

```powershell
flask --app app db upgrade
```

## Run locally

Start the Flask application:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000
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

1. **AI extraction** — determine what the meeting says.
2. **AI consolidation** — determine how new findings relate to existing project memory.
3. **Database application** — apply the selected decision safely and preserve an audit trail.

This separation makes the consolidation logic testable independently from the Flask UI and database workflow, and allows the reconciliation strategy to evolve without replacing the underlying project-memory model.

## Roadmap

Planned improvements include:

- embedding-based semantic similarity
- expanded automated tests for semantic duplicate scenarios

## Status

This is an actively developed project exploring practical AI-assisted project and delivery management.

The current implementation is suitable for local development and experimentation. It should not be considered production-ready without additional security, observability, reliability, and evaluation work.
