import json
import re

from router import ModelRouter


def build_prompt(text):
    """
    Build prompt for meeting analysis.
    """

    return """
You are an experienced Delivery Manager.

Analyze the meeting notes below.

Return only valid JSON, with no Markdown fence or commentary. Use this schema:
{
  "executive_summary": "string",
  "project_status": "on_track|at_risk|off_track|unknown",
  "progress_summary": "string",
  "completed_items": ["string"],
  "in_progress_items": ["string"],
  "risks": [{"title": "string", "description": "string", "impact": "low|medium|high|unknown", "mitigation": "string", "status": "open|resolved"}],
  "blockers": [{"title": "string", "description": "string", "status": "open|resolved"}],
  "decisions": [{"title": "string", "details": "string"}],
  "action_items": [{"title": "string", "details": "string", "owner": "string", "due_date": "YYYY-MM-DD or null", "status": "open|completed"}]
}

Only mark an existing item resolved or completed when the meeting explicitly says so. Do not infer closure from an item being absent.

Meeting Notes:

""" + text



def analyze_document(
        text,
        provider,
        model,
        router_instance=None,
):
    """
    Analyze meeting notes using selected AI provider.

    Args:
        text (str): meeting notes
        provider (str): provider name (google/groq)
        model (str): selected model

    Returns:
        str: AI response
    """

    prompt = build_prompt(text)


    router = router_instance or ModelRouter()

    result = router.generate(
        provider=provider,
        model=model,
        prompt=prompt
    )


    return result


def parse_analysis(result):
    """Parse a model response into the project-memory analysis contract."""
    cleaned = result.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)

    try:
        analysis = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError("The AI response was not valid structured JSON.") from error

    if not isinstance(analysis, dict):
        raise ValueError("The AI response must be a JSON object.")

    return analysis
