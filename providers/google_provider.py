import os

from dotenv import load_dotenv
from google import genai


class GoogleProvider:

    def __init__(self):
        load_dotenv(override=True)

        api_key = os.getenv("GOOGLE_API_KEY")

        if not api_key:
            raise ValueError("GOOGLE_API_KEY is missing")

        self.client = genai.Client(
            api_key=api_key.strip()
        )

    def generate(self, model, prompt):

        response = self.client.models.generate_content(
            model=model,
            contents=prompt
        )

        return response.text

    def get_models(self):

        models = self.client.models.list()

        return [
            model.name.removeprefix("models/")
            for model in models
            if "generateContent" in model.supported_actions
        ]