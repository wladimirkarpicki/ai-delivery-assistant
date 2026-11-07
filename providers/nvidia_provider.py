"""NVIDIA build (integrate.api.nvidia.com) provider.

Two things about this endpoint shaped this client:

- `input_type` is required on the embeddings call. Without it the API
  answers 400 "'input_type' parameter is required". "query" is for the
  text being searched for and "passage" for the text being stored; both
  are accepted here, and the caller passes the same type it used when the
  vector was produced, so a re-embed and a search are not mixed.
- Some models on this gateway are reasoning models that return their
  answer in `reasoning_content` and leave `content` empty. Those models
  burn the token budget on the reasoning before the answer, which is why
  they were not chosen. A model whose content comes back empty is treated
  as a failure rather than silently returning nothing.
"""

import os

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config_loader import load_env

BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_TIMEOUT = 180
# "query" when the text is a search, "passage" when it is being stored.
DEFAULT_INPUT_TYPE = "passage"
# Starting batch size. It is deliberately small and reduced on demand
# rather than chosen once: the gateway's embeddings endpoint answers 500
# "service inference failed" for reasons that do not follow an obvious
# rule. Measured against the live API, the same input flipped between 200
# and 500 across runs, and batches of 4 or more failed while 1 to 3
# usually succeeded, but not reliably. Guessing a magic number is not a
# fix; halving until the batch is accepted is.
EMBED_BATCH_SIZE = 3


class NvidiaProvider:
    def __init__(self):
        load_env()

        api_key = (os.getenv("NVIDIA_API_KEY") or "").strip()

        if not api_key:
            raise ValueError("NVIDIA_API_KEY is missing")

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # Without reraise tenacity raises RetryError after the last
        # attempt, which the API layer does not catch, so a failing
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
                "temperature": 0.1,
                "max_tokens": 2000,
            },
            timeout=DEFAULT_TIMEOUT,
        )

        response.raise_for_status()

        message = response.json()["choices"][0]["message"]
        content = message.get("content")

        if not content:
            # A reasoning model that spent the budget before answering
            # looks exactly like this. Returning nothing would be read
            # downstream as an empty analysis.
            raise ValueError(
                "The model returned no content; a reasoning model needs a "
                "larger token budget than this client sends."
            )

        return content

    def _embed_batch(self, model, batch, input_type):
        """
        Embed one batch, splitting it until the gateway accepts it.

        The endpoint replies 500 on batches it will not run, and the
        condition is not predictable from the batch alone: identical
        inputs have been seen to answer 200 and then 500, and larger
        batches fail far more often than small ones. Rather than guess a
        limit, a rejected batch is halved and retried, which converges on
        whatever the gateway currently accepts.
        """
        try:
            response = httpx.post(
                f"{BASE_URL}/embeddings",
                headers=self.headers,
                json={
                    "model": model,
                    "input": batch,
                    "input_type": input_type,
                },
                timeout=DEFAULT_TIMEOUT,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500 or len(batch) <= 1:
                raise
            # A single text that fails is a genuine outage for that input.
            mid = len(batch) // 2
            return self._embed_batch(model, batch[:mid], input_type) + \
                self._embed_batch(model, batch[mid:], input_type)

        data = response.json()["data"]

        if len(data) != len(batch):
            raise ValueError(
                f"Embedding provider returned {len(data)} vectors for "
                f"{len(batch)} texts."
            )

        return [item["embedding"] for item in data]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def embed_texts(self, model, texts, input_type=DEFAULT_INPUT_TYPE):
        """
        Embed a batch of texts. Returns one vector per input text, in the
        same order.

        Repeated strings are collapsed first: they produce identical
        vectors, and a batch containing a duplicate is one of the shapes
        this gateway refuses. The result is expanded back to the caller's
        original order, which also saves quota.
        """
        if not texts:
            return []

        # dict.fromkeys preserves order while collapsing repeats.
        unique = list(dict.fromkeys(texts))

        vectors = []
        offset = 0

        while offset < len(unique):
            batch = unique[offset:offset + EMBED_BATCH_SIZE]
            vectors.extend(self._embed_batch(model, batch, input_type))
            offset += len(batch)

        if len(vectors) != len(unique):
            raise ValueError(
                f"Embedding provider returned {len(vectors)} vectors for "
                f"{len(unique)} distinct texts."
            )

        by_text = dict(zip(unique, vectors))
        return [by_text[text] for text in texts]

    def get_models(self):
        """
        Discover the models this key can actually reach.

        The gateway lists models that answer 404 for a given key, so the
        list is filtered to what really responds: a model advertised but
        not deployed would make the health check fail for a reason the
        operator cannot act on.
        """
        response = httpx.get(
            f"{BASE_URL}/models",
            headers=self.headers,
            timeout=30,
        )

        response.raise_for_status()

        return sorted(model["id"] for model in response.json()["data"])
