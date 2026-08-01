import os
from dotenv import load_dotenv
import google.generativeai as genai


load_dotenv()

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)


model = genai.GenerativeModel(
    "gemini-2.5-flash"
)


def analyze_document(text):

    prompt = """
You are an experienced Delivery Manager.

Analyze the project meeting notes below.

Extract:

1. Overall project status
2. Key risks
3. Blockers
4. Decisions made
5. Action items with owners and deadlines
6. Executive summary

Format the answer clearly.

Meeting notes:

""" + text


    response = model.generate_content(prompt)

    return response.text