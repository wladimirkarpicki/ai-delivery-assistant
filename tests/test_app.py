import io
import unittest

from app import create_app


class FakeRouter:
    def get_models(self, provider):
        return {
            "google": ["gemini-3.6-flash", "unsupported-model"],
            "groq": ["llama-3.3-70b-versatile"],
        }[provider]

    def generate(self, provider, model, prompt):
        return f"Analysis from {provider}:{model}"


class FlaskAppTests(unittest.TestCase):
    def setUp(self):
        app = create_app(FakeRouter())
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_home_page_lists_filtered_models(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"gemini-3.6-flash", response.data)
        self.assertNotIn(b"unsupported-model", response.data)

    def test_pasted_notes_are_analyzed(self):
        response = self.client.post(
            "/",
            data={
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "meeting_notes": "Ship the release on Friday.",
            },
        )
        self.assertIn(b"Analysis from groq:llama-3.3-70b-versatile", response.data)

    def test_text_upload_is_analyzed(self):
        response = self.client.post(
            "/",
            data={
                "provider": "google",
                "model": "gemini-3.6-flash",
                "meeting_file": (io.BytesIO(b"Team meeting notes"), "notes.txt"),
            },
            content_type="multipart/form-data",
        )
        self.assertIn(b"Analysis from google:gemini-3.6-flash", response.data)


if __name__ == "__main__":
    unittest.main()
