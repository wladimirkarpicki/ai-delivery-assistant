import os

from tenacity import retry, stop_after_attempt, wait_exponential
from config_loader import load_env
from groq import Groq


class GroqProvider:

    def __init__(self):
        load_env()

        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise ValueError("GROQ_API_KEY is missing")

        self.client = Groq(
            api_key=api_key.strip()
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
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
        if hasattr(self, '_cached_models'):
            return self._cached_models
        models = self.client.models.list()
        result = [
            model.id
            for model in models.data
        ]
        self._cached_models = result
        return result