import os

from tenacity import retry, stop_after_attempt, wait_exponential
from config_loader import load_env
from google import genai


class GoogleProvider:

    def __init__(self):
        load_env()

        api_key = os.getenv("GOOGLE_API_KEY")

        if not api_key:
            raise ValueError("GOOGLE_API_KEY is missing")

        self.client = genai.Client(
            api_key=api_key.strip()
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate(self, model, prompt):

        response = self.client.models.generate_content(
            model=model,
            contents=prompt
        )

        return response.text

    def get_models(self):
        if hasattr(self, '_cached_models'):
            return self._cached_models
        models = self.client.models.list()
        result = [
            model.name.removeprefix("models/")
            for model in models
            if "generateContent" in model.supported_actions
        ]
        self._cached_models = result
        return result