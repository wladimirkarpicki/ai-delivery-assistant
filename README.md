# AI Delivery Assistant

AI-powered meeting-notes analyzer for project and delivery management.

The application turns meeting notes into structured project intelligence — including delivery status, risks, blockers, decisions, and action items — and maintains a persistent project memory across meetings.

The project is designed around a practical delivery-management problem: **the same project information can be described differently by different AI runs or models, so extracted information needs to be reconciled before it becomes current project state.**

## Features

- AI analysis of project meeting notes
- Google Gemini and Groq provider support
- Dynamic model discovery filtered to the supported-model configuration
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
- Consolidation decisions for new findings:
  - **CREATE** — genuinely new information
  - **MERGE** — same underlying information with different wording
  - **UPDATE** — existing item with changed information
  - **CONFLICT** — new information contradicts existing memory
- Immutable meeting records containing the original input and AI analysis
- Immutable history events for memory changes
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
Existing project memory + new findings
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

`MemoryConsolidator` uses the selected AI provider/model to compare new findings with the existing project memory. Its output is then applied by `project_memory.py`, which keeps the database changes and history events separate from the AI decision layer.

This separation is intentional: the AI proposes a consolidation plan, while the application remains responsible for applying that plan to the database.

### Current limitation

The current consolidation mechanism is **LLM-based**. Because LLM output is probabilistic, semantically equivalent items can still occasionally be classified as `CREATE` when their wording is sufficiently different.

For example:

```text
Review Memory Relevance
Project Memory Relevance Review
```

These may represent the same action even when the model fails to recognize them as such.

A deterministic/semantic candidate-matching layer using normalization, fuzzy matching, and embeddings is a planned direction for making consolidation more robust and idempotent.

## Supported models

The application discovers models from each provider API and exposes only models configured in `config.py`.

### Google Gemini

- `gemini-3.6-flash`
- `gemini-3.5-flash`
- `gemma-4-31b-it`
- `gemma-4-26b-a4b-it`

### Groq

- `llama-3.3-70b-versatile`
- `qwen/qwen3.6-27b`
- `llama-3.1-8b-instant`

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
                              |         |
                         Gemini API   Groq API
                              |         |
                              +----+----+
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
config.py              Supported provider/model configuration
database.py            SQLAlchemy and migration configuration
models.py              PostgreSQL project-memory models
project_memory.py      Current-state reconciliation and database history
memory_consolidator.py AI-driven memory consolidation
document_parser.py     PDF, DOCX, TXT, and Markdown extraction
router.py              Provider routing and model discovery
providers/             Gemini and Groq client implementations
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
- **Google GenAI SDK**
- **Groq SDK**
- **python-docx** for DOCX extraction
- **pypdf** for PDF extraction

## Installation

Create and activate a virtual environment:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```text
GOOGLE_API_KEY=your_google_api_key
GROQ_API_KEY=your_groq_api_key
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
4. Select an AI provider and available model.
5. Review the extracted project state and memory changes.

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

- deterministic normalization before AI consolidation
- lexical/fuzzy candidate matching
- embedding-based semantic similarity
- stronger idempotency guarantees for repeated processing of the same meeting
- canonical titles and aliases for project-memory entities
- expanded automated tests for semantic duplicate scenarios
- improved handling of consolidation confidence and ambiguous cases

## Status

This is an actively developed project exploring practical AI-assisted project and delivery management.

The current implementation is suitable for local development and experimentation. It should not be considered production-ready without additional security, observability, reliability, and evaluation work.
