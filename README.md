# AI Delivery Assistant

AI-powered assistant for Project Managers and Delivery Managers that transforms meeting notes into structured delivery insights.

The application uses Large Language Models (LLMs) to analyze project discussions and generate:

- Executive summaries
- Project status updates
- Risks and blockers
- Decisions
- Action items with owners and deadlines

Built with a modular AI provider architecture that allows switching between different LLM providers and models.

---

## ✨ Features

### AI Meeting Analysis

Convert unstructured meeting notes into structured delivery documentation.

Generated insights:

- 📌 Executive Summary
- 📊 Project Status
- ⚠️ Risks
- 🚧 Blockers
- ✅ Decisions Made
- 📋 Action Items

---

### Multi-Model AI Support

The application supports multiple AI providers through a unified routing layer.

Currently supported:

#### Google Gemini

- Gemini 3.6 Flash

#### Groq

Available models include:

- Llama 3.3 70B
- Llama 3.1 8B Instant
- Qwen
- Other available Groq models

Models can be selected dynamically from the application UI.

---

# 🏗️ Architecture
Streamlit UI
                 |
                 v
          Analyzer Layer
                 |
                 v
           Model Router
                 |
      +----------+----------+
      |                     |
      v                     v
   Google Provider        Groq Provider
          |                     |
          v                     v
     Google API             Groq API


The provider abstraction allows adding new AI backends without changing application logic.

Future integrations:

- OpenRouter
- Anthropic Claude
- Azure OpenAI
- Local LLMs

---

# 🛠️ Tech Stack

## Application

- Python
- Streamlit
- python-dotenv

## AI APIs

- Google API
- Groq API

## Development

- VS Code
- Git
- Python virtual environment

---

# 📂 Project Structure

ai-delivery-assistant/
├── app.py                     # Streamlit interface
├── analyzer.py                # Prompt generation and analysis logic
├── router.py                  # LLM provider routing
├── config.py                  # Environment configuration
│
├── providers/
│   ├── init.py
│   ├── google_provider.py     # Gemini integration
│   └── groq_provider.py       # Groq integration
│
├── requirements.txt
├── .env
└── README.md



---

# 🚀 Installation

## 1. Clone repository

```bash
git clone <repository-url>

cd ai-delivery-assistant

2. Create virtual environment

python -m venv venv

Activate:

Windows PowerShell
.\venv\Scripts\Activate.ps1

3. Install dependencies

pip install -r requirements.txt

Configuration

Create .env file:
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key

Never commit .env to GitHub.

▶️ Run Application

Start Streamlit:
python -m streamlit run app.py

Open:
http://localhost:8501

💡 Usage

Select AI provider:

Google Gemini
or
Groq

Select AI model.

Paste meeting notes.

Click Analyze.

Review generated delivery insights.


Example


Input:

#Backend API migration is delayed because authentication service is not ready.

#Beta release moved from September 10 to September 24.

#John will complete API integration by September 15.
#Maria will prepare regression tests by September 18.


Output:

#Executive Summary

#Project Phoenix is progressing with backend migration delayed
#due to authentication dependencies.

#Risks

#- Third-party authentication dependency

#Blockers

#- Authentication service unavailable

#Action Items

#John:
#Complete API integration
#Deadline: September 15

#Maria:
#Prepare regression tests
#Deadline: September 18

🗺️ Roadmap

Completed

✅ Streamlit UI
✅ Google integration
✅ Groq integration
✅ Dynamic model selection
✅ Provider-based architecture  


Planned

Document Processing
-PDF upload
-DOCX support
-Meeting transcription

Integrations
-Jira
-Azure DevOps
-Confluence

AI Enhancements
-RAG knowledge base
-Project history analysis
-Custom PM templates

🎯 Project Goals
AI Delivery Assistant demonstrates:
Practical AI integration
LLM provider abstraction
Software architecture design
AI-assisted project management workflows


License
MIT License

For GitHub, I would also add:

.gitignore
requirements.txt
README.md
LICENSE

and **do not upload**:

.env
venv/
pycache/

After adding this:

```bash
git add README.md
git commit -m "Add GitHub project documentation"
git push origin feature/multi-model-support
