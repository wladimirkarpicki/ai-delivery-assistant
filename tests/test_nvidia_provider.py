"""Unit tests for the NVIDIA provider client's retry and error mapping.

Everything that talks to the gateway goes through httpx.post/get, which
are replaced with a recording mock: no test here opens a socket. The
surfaces pinned are the ones the audit run flagged — the two-role
system/user split on generate, the empty-content guard for reasoning
models, the retry contract (retries, then reraises the ORIGINAL error),
the batch-halving recovery on 5xx, and get_models' sorted discovery.

The API key is pinned to a unit-test value in setUp and restored in
tearDown; tests/conftest.py neutralises load_dotenv, so no developer
env file can supply a different value mid-test.
"""

import os
import unittest
from unittest.mock import patch

import httpx

from providers.nvidia_provider import NvidiaProvider


class FakeResponse:
    """The two methods the client actually calls on an httpx response."""

    def __init__(self, json_data=None, status_error=None):
        self._json_data = json_data
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def json(self):
        return self._json_data


def status_error(status_code):
    """A real httpx.HTTPStatusError, built the way httpx builds it."""

    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/x")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"{status_code} error", request=request, response=response
    )


class ProviderTestCase(unittest.TestCase):
    def setUp(self):
        self._saved_key = os.environ.get("NVIDIA_API_KEY")
        os.environ["NVIDIA_API_KEY"] = "unit-test-nvidia-key"
        self.provider = NvidiaProvider()

    def tearDown(self):
        if self._saved_key is None:
            os.environ.pop("NVIDIA_API_KEY", None)
        else:
            os.environ["NVIDIA_API_KEY"] = self._saved_key


class GenerateTests(ProviderTestCase):
    @patch("providers.nvidia_provider.httpx.post")
    def test_generate_returns_content_and_separates_the_system_role(self, mock_post):
        mock_post.return_value = FakeResponse(
            {"choices": [{"message": {"content": "the answer"}}]}
        )

        result = self.provider.generate(
            "model-a", "user-turn text", system_prompt="instructions"
        )

        self.assertEqual(result, "the answer")
        payload = mock_post.call_args.kwargs["json"]
        # The instructions travel in the system role and the user data in
        # the user role; concatenating them in one message is the shape
        # that lets a document steer the analysis.
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": "instructions"},
                {"role": "user", "content": "user-turn text"},
            ],
        )
        self.assertEqual(payload["model"], "model-a")

    @patch("providers.nvidia_provider.httpx.post")
    def test_generate_without_a_system_prompt_sends_only_the_user_turn(self, mock_post):
        mock_post.return_value = FakeResponse(
            {"choices": [{"message": {"content": "the answer"}}]}
        )

        self.provider.generate("model-a", "user-turn text")

        self.assertEqual(
            mock_post.call_args.kwargs["json"]["messages"],
            [{"role": "user", "content": "user-turn text"}],
        )

    @patch("providers.nvidia_provider.httpx.post")
    def test_generate_raises_when_the_model_returns_no_content(self, mock_post):
        # A reasoning model that spent the token budget before answering
        # looks exactly like this; returning nothing would be read
        # downstream as an empty analysis.
        mock_post.return_value = FakeResponse({"choices": [{"message": {}}]})

        with self.assertRaises(ValueError) as ctx:
            self.provider.generate("model-a", "user-turn text")

        self.assertIn("no content", str(ctx.exception))

    @patch("providers.nvidia_provider.httpx.post")
    def test_generate_retries_a_transient_failure_and_recovers(self, mock_post):
        mock_post.side_effect = [
            httpx.ConnectError("boom"),
            FakeResponse({"choices": [{"message": {"content": "the answer"}}]}),
        ]

        result = self.provider.generate("model-a", "user-turn text")

        self.assertEqual(result, "the answer")
        self.assertEqual(mock_post.call_count, 2)

    @patch("providers.nvidia_provider.httpx.post")
    def test_generate_reraises_the_original_error_after_three_attempts(self, mock_post):
        # reraise=True is documented on the decorator: without it tenacity
        # wraps the failure in RetryError and the API layer does not catch
        # it, so a failing upstream surfaced as a 500 instead of the
        # documented fallback.
        mock_post.side_effect = httpx.ConnectError("boom")

        with self.assertRaises(httpx.ConnectError):
            self.provider.generate("model-a", "user-turn text")

        self.assertEqual(mock_post.call_count, 3)


class EmbedBatchTests(ProviderTestCase):
    @patch("providers.nvidia_provider.httpx.post")
    def test_a_rejected_batch_is_halved_until_the_gateway_accepts_it(self, mock_post):
        # The 5xx is not predictable from the batch shape: the recovery is
        # to split it, not to guess a limit.
        mock_post.side_effect = [
            FakeResponse(status_error=status_error(500)),
            FakeResponse({"data": [{"embedding": [0.1]}]}),
            FakeResponse(
                {"data": [{"embedding": [0.2]}, {"embedding": [0.3]}]}
            ),
        ]

        vectors = self.provider._embed_batch("model-a", ["a", "b", "c"], "passage")

        self.assertEqual(vectors, [[0.1], [0.2], [0.3]])
        self.assertEqual(mock_post.call_count, 3)

    @patch("providers.nvidia_provider.httpx.post")
    def test_a_single_failing_text_is_not_split_further(self, mock_post):
        mock_post.return_value = FakeResponse(status_error=status_error(500))

        with self.assertRaises(httpx.HTTPStatusError):
            self.provider._embed_batch("model-a", ["a"], "passage")

    @patch("providers.nvidia_provider.httpx.post")
    def test_a_client_error_is_not_retried_into_a_split(self, mock_post):
        mock_post.return_value = FakeResponse(status_error=status_error(400))

        with self.assertRaises(httpx.HTTPStatusError):
            self.provider._embed_batch("model-a", ["a", "b"], "passage")

        self.assertEqual(mock_post.call_count, 1)

    @patch("providers.nvidia_provider.httpx.post")
    def test_a_vector_count_that_does_not_match_the_batch_raises(self, mock_post):
        mock_post.return_value = FakeResponse({"data": []})

        with self.assertRaises(ValueError) as ctx:
            self.provider._embed_batch("model-a", ["a"], "passage")

        self.assertIn("vectors for", str(ctx.exception))


class EmbedTextsTests(ProviderTestCase):
    @patch("providers.nvidia_provider.httpx.post")
    def test_no_texts_returns_no_vectors(self, mock_post):
        self.assertEqual(self.provider.embed_texts("model-a", []), [])
        mock_post.assert_not_called()


class GetModelsTests(ProviderTestCase):
    @patch("providers.nvidia_provider.httpx.get")
    def test_get_models_returns_the_ids_sorted(self, mock_get):
        mock_get.return_value = FakeResponse(
            {"data": [{"id": "model-b"}, {"id": "model-a"}]}
        )

        self.assertEqual(
            self.provider.get_models(), ["model-a", "model-b"]
        )
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://integrate.api.nvidia.com/v1/models",
        )


if __name__ == "__main__":
    unittest.main()