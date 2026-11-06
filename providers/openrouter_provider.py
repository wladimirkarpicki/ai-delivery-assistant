import os

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config_loader import load_env

BASE_URL = "https://openrouter.ai/api/v1"
FREE_MODELS_ROUTER = "openrouter/free"
DEFAULT_TIMEOUT = 120


class OpenRouterProvider:

    def __init__(self):
        load_env()

        api_key = os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is missing")

        self.headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # Without reraise, tenacity raises RetryError after the last
        # attempt. The API layer catches (ValueError, RuntimeError,
        # ConnectionError, TimeoutError), not RetryError, so a failing
        # upstream surfaced as a 500 instead of the documented fallback.
        reraise=True,
    )
    def generate(self, model, prompt, system_prompt=None):
        # Two roles, not one concatenated string. When the instructions
        # and user-controlled data share a single user message, the data
        # can override the instructions; separating them is what keeps a
        # meeting note from steering the analysis.
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers=self.headers,
            json={
                "model": model,
                "messages": messages,
            },
            timeout=DEFAULT_TIMEOUT,
        )

        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]

        return content

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def embed_texts(self, model, texts):
        """
        Embed a batch of texts. Returns one vector (list of floats) per
        input text, in the same order.

        A short batch is an error rather than a silent gap: the caller
        matches vectors to items positionally, so a missing vector would
        silently strip an item of its embedding.
        """
        vectors = []

        for offset in range(0, len(texts), 64):
            batch = list(texts[offset:offset + 64])

            response = httpx.post(
                f"{BASE_URL}/embeddings",
                headers=self.headers,
                json={
                    "model": model,
                    "input": batch,
                },
                timeout=DEFAULT_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()["data"]

            if len(data) != len(batch):
                raise ValueError(
                    "Embedding provider returned "
                    f"{len(data)} vectors for {len(batch)} texts."
                )

            vectors.extend(item["embedding"] for item in data)

        if len(vectors) != len(texts):
            raise ValueError(
                f"Embedding provider returned {len(vectors)} vectors "
                f"for {len(texts)} texts."
            )

        return vectors

    def get_models(self):
        if hasattr(self, '_cached_models'):
            return self._cached_models

        response = httpx.get(
            f"{BASE_URL}/models",
            headers=self.headers,
            timeout=30,
        )

        response.raise_for_status()

        # The Free Models Router first, then every free-tier model,
        # so the UI only offers models this key can actually use.
        free_model_ids = sorted(
            model["id"]
            for model in response.json()["data"]
            if model.get("pricing", {}).get("prompt") == "0"
            and model.get("pricing", {}).get("completion") == "0"
            and model["id"] != FREE_MODELS_ROUTER
        )

        self._cached_models = [FREE_MODELS_ROUTER] + free_model_ids
        return self._cached_models
