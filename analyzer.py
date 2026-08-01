import os
from dotenv import load_dotenv
from google import genai


load_dotenv()


client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)


def analyze_document(text):

    prompt = f"""
You are an experienced Delivery Manager.

Analyze the project meeting notes below.

Extract:

1. Overall project status
2. Key risks
3. Blockers
4. Decisions made
5. Action items with owners and deadlines
6. Executive summary

Provide a clear structured response.

Meeting notes:

{text}
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )

    return response.text