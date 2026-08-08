# AI Delivery Assistant

AI-powered meeting notes analyzer for project and delivery management.

The application analyzes meeting notes and extracts structured delivery insights such as project status, risks, blockers, decisions, and action items.

## Features

- 🤖 Multiple AI providers:
  - Google Gemini
  - Groq
- 🔽 Model selection through the UI
- 🎯 Supported-model filtering
- 📄 Upload meeting notes:
  - PDF
  - DOCX
  - TXT
  - Markdown
- 📝 Paste meeting notes directly
- 📊 Structured delivery analysis
- ⚡ Streamlit web interface
- 🔐 API keys stored in environment variables

## Supported Models

### Google Gemini

- `gemini-3.6-flash`
- `gemini-3.5-flash`
- `gemma-4-31b-it`
- `gemma-4-26b-a4b-it`

### Groq

- `llama-3.3-70b-versatile`
- `qwen/qwen3.6-27b`
- `llama-3.1-8b-instant`

The application discovers available models through the provider APIs and filters them against the application's supported-model configuration.

## Analysis

The assistant produces:

- Executive Summary
- Project Status
- Completed Items
- Items in Progress
- Risks
- Blockers
- Decisions Made
- Action Items
- Owners and Deadlines

## Architecture

```text
Streamlit UI
     │
     ├── File Upload / Text Input
     │          │
     │          ▼
     │   Document Parser
     │          │
     │          ▼
     │   Meeting Notes Text
     │          │
     │          ▼
     │   Model Router
     │       /      \
     │      /        \
     ▼               ▼
  Gemini            Groq
     │               │
     └───────┬───────┘
             ▼
       AI Analysis

Project Structure

ai-delivery-assistant/
│
├── app.py
├── analyzer.py
├── config.py
├── router.py
├── document_parser.py
│
├── providers/
│   ├── google_provider.py
│   └── groq_provider.py
│
├── requirements.txt
├── .env
└── .gitignore


### Installation

Clone the repository:
git clone https://github.com/wladimirkarpicki/ai-delivery-assistant.git
cd ai-delivery-assistant

Create a virtual environment:
python -m venv venv

Activate it on Windows PowerShell:
venv\Scripts\Activate.ps1

Install dependencies:
pip install -r requirements.txt


### Configuration

Create a .env file in the project root:
GOOGLE_API_KEY=your_google_api_key
GROQ_API_KEY=your_groq_api_key

Never commit .env or API keys to Git.


### Run

Start the application:
python -m streamlit run app.py

Then open:
http://localhost:8501


### Usage

-Select an AI provider.
-Select an available model.
-Upload a meeting document or paste meeting notes.
-Click Analyze.
-Review the generated delivery analysis.


### Technology Stack

Python
Streamlit
Google Gemini API
Groq API
pypdf
python-docx


### Project Status

🚧 Active development

Planned improvements include additional document formats, improved document processing, and further delivery-management analysis capabilities.