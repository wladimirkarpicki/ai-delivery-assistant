# AI Delivery Assistant

AI-powered meeting-notes analyzer for project and delivery management. It turns meeting notes into a structured summary of status, risks, blockers, decisions, and action items.

## Features

- Google Gemini and Groq provider support
- Dynamic model discovery filtered to the supported-model configuration
- PDF, DOCX, TXT, and Markdown uploads
- Pasted meeting notes
- Structured delivery analysis
- Flask project workspace with persistent project memory
- API keys loaded from environment variables

## Project memory

Each project has three complementary layers:

- **Meetings** are immutable source records. They retain the extracted document text, provider/model, raw AI response, and parsed analysis.
- **Current state** tracks the latest delivery status, progress summary, open risks, blockers, and actions.
- **History events** are immutable audit records. Each event references the meeting that created, updated, resolved, or completed an item.

Risks, blockers, and action items are never deleted because they are no longer current. An explicit resolution or completion records its timestamp and the meeting that caused it.

## Supported models

The application discovers models from each provider API and offers only models configured in `config.py`.

- Google Gemini: `gemini-3.6-flash`, `gemini-3.5-flash`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`
- Groq: `llama-3.3-70b-versatile`, `qwen/qwen3.6-27b`, `llama-3.1-8b-instant`

## Structure

```text
app.py                 Flask routes and web UI entry point
analyzer.py            Meeting-note analysis prompt and orchestration
database.py            SQLAlchemy and migration configuration
models.py              PostgreSQL project-memory models
project_memory.py      Structured-analysis reconciliation and event history
document_parser.py     PDF, DOCX, TXT, and Markdown extraction
router.py              Provider routing and lazy provider creation
providers/             Gemini and Groq client implementations
templates/             Flask HTML template
static/                CSS
tests/                 Flask route tests
migrations/            Alembic database migrations
```

## Installation

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
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

Create the PostgreSQL database itself once if it does not already exist, then apply the version-controlled schema migration:

```powershell
flask --app app db upgrade
```

## Run

```powershell
python app.py
```

Open `http://127.0.0.1:5000`, create a project, then add meeting notes through that project. Every original input and AI analysis is retained; current items are updated only when a meeting explicitly records a resolution or completion.

## Test

```powershell
python -m unittest discover -s tests
```
