import os

from dotenv import load_dotenv
from groq import Groq


class GroqProvider:

    def __init__(self):
        load_dotenv(override=True)

        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise ValueError("GROQ_API_KEY is missing")

        self.client = Groq(
            api_key=api_key.strip()
        )

    def generate(self, model, prompt):

        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.choices[0].message.content


    def get_models(self):
        models = self.client.models.list()
        return [
            model.id
            for model in models.data
        ]