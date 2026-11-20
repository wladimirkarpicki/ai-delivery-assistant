"""Unit tests for the provider router's dispatch and caching surface.

The router is a thin dispatch layer in front of the provider clients, and
the audit run flagged it as one of the weakest-covered modules. The real
NvidiaProvider needs an API key and a network call to construct, so these
tests replace the provider class with a recording stub: the surface under
test is the router's own routing, caching and dispatch logic, which is
what these tests exist to pin.
"""

import unittest

from providers.nvidia_provider import NvidiaProvider
from router import ModelRouter


class StubProvider(NvidiaProvider):
    """Records its calls and answers with fixed values, never touching HTTP.

    A subclass of the real provider so it satisfies the router's typed
    provider registry; __init__ is overridden so no API key or network
    call is involved.
    """

    def __init__(self):
        self.calls = []

    def generate(self, model, prompt, system_prompt=None):
        self.calls.append(("generate", model, prompt, system_prompt))
        return "generated-text"

    def get_models(self):
        self.calls.append(("get_models",))
        return ["model-a", "model-b"]

    def embed_texts(self, model, texts, input_type="passage"):
        self.calls.append(("embed_texts", model, tuple(texts), input_type))
        return [[0.0, 1.0] for _ in texts]


class ModelRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = ModelRouter()
        # The stub is registered on the instance so the real nvidia
        # provider class stays untouched for every other test.
        self.router.provider_classes["stub"] = StubProvider

    def test_unsupported_provider_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            self.router._get_provider("nope")

        self.assertIn("nope", str(ctx.exception))

    def test_provider_is_instantiated_once_and_cached(self):
        first = self.router._get_provider("stub")
        second = self.router._get_provider("stub")

        self.assertIs(first, second)

    def test_generate_dispatches_with_system_prompt_in_its_own_argument(self):
        result = self.router.generate(
            "stub",
            "model-a",
            "user-turn text",
            system_prompt="instructions",
        )

        self.assertEqual(result, "generated-text")
        self.assertEqual(
            self.router.providers["stub"].calls,
            [("generate", "model-a", "user-turn text", "instructions")],
        )

    def test_get_models_dispatches_to_the_selected_provider(self):
        self.assertEqual(self.router.get_models("stub"), ["model-a", "model-b"])
        self.assertEqual(
            self.router.providers["stub"].calls, [("get_models",)]
        )

    def test_embed_texts_dispatches_to_the_selected_provider(self):
        vectors = self.router.embed_texts("stub", "model-a", ["one", "two"])

        self.assertEqual(vectors, [[0.0, 1.0], [0.0, 1.0]])
        self.assertEqual(
            self.router.providers["stub"].calls,
            [("embed_texts", "model-a", ("one", "two"), "passage")],
        )


if __name__ == "__main__":
    unittest.main()