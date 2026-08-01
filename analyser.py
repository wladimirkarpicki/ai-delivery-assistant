import os
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def analyze_document(text):

    response = client.chat.completions.create(
        model="gpt-5.5-mini",
        messages=[
            {
                "role": "system",
                "content": """
                You are an experienced Delivery Manager.
                Analyze project documents.
                Extract:
                - project status
                - risks
                - blockers
                - decisions
                - action items
                """
            },
            {
                "role": "user",
                "content": text
            }
        ]
    )

    return response.choices[0].message.content