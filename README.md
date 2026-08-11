# AI Delivery Assistant

AI-powered meeting-notes analyzer for project and delivery management. It turns meeting notes into a structured summary of status, risks, blockers, decisions, and action items.

## Features

- Google Gemini and Groq provider support
- Dynamic model discovery filtered to the supported-model configuration
- PDF, DOCX, TXT, and Markdown uploads
- Pasted meeting notes
- Structured delivery analysis
- Minimal Flask web interface
- API keys loaded from environment variables

## Supported models

The application discovers models from each provider API and offers only models configured in `config.py`.

- Google Gemini: `gemini-3.6-flash`, `gemini-3.5-flash`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`
- Groq: `llama-3.3-70b-versatile`, `qwen/qwen3.6-27b`, `llama-3.1-8b-instant`

## Structure

```text
app.py                 Flask routes and web UI entry point
analyzer.py            Meeting-note analysis prompt and orchestration
document_parser.py     PDF, DOCX, TXT, and Markdown extraction
router.py              Provider routing and lazy provider creation
providers/             Gemini and Groq client implementations
templates/             Flask HTML template
static/                CSS
tests/                 Flask route tests
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
```

Do not commit `.env` or API keys.

## Run

```powershell
python app.py
```

Open `http://127.0.0.1:5000`, select a provider and model, then upload notes or paste them into the form.

## Test

```powershell
python -m unittest discover -s tests
```
