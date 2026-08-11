import json
import unittest

from app import create_app
from database import db
from models import ActionItem, HistoryEvent, Meeting, Project, Risk


class FakeRouter:
    def __init__(self):
        self.responses = []

    def get_models(self, provider):
        return {"google": ["gemini-3.6-flash", "unsupported-model"], "groq": ["llama-3.3-70b-versatile"]}[provider]

    def generate(self, provider, model, prompt):
        return json.dumps(self.responses.pop(0))


class FlaskAppTests(unittest.TestCase):
    def setUp(self):
        self.router = FakeRouter()
        self.app = create_app(self.router, "sqlite://")
        self.app.config.update(TESTING=True)
        with self.app.app_context():
            db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def create_project(self):
        self.client.post("/projects", data={"name": "Phoenix", "description": "Release project"})
        with self.app.app_context():
            return db.session.scalar(db.select(Project).filter_by(name="Phoenix")).id

    def test_projects_page_and_filtered_models(self):
        response = self.client.get("/projects")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"New project", response.data)
        response = self.client.get("/models/google")
        self.assertEqual(response.get_json()["models"], ["gemini-3.6-flash"])

    def test_meetings_preserve_input_and_history_while_resolving_items(self):
        project_id = self.create_project()
        self.router.responses = [
            {
                "executive_summary": "QA is constrained.", "project_status": "at_risk", "progress_summary": "Testing is delayed.",
                "completed_items": [], "in_progress_items": ["Regression testing"],
                "risks": [{"title": "QA capacity", "description": "One tester", "impact": "high", "mitigation": "Borrow support", "status": "open"}],
                "blockers": [], "decisions": [],
                "action_items": [{"title": "Find QA support", "details": "Ask support team", "owner": "Ava", "due_date": "2026-08-15", "status": "open"}],
            },
            {
                "executive_summary": "QA support confirmed.", "project_status": "on_track", "progress_summary": "Testing is staffed.",
                "completed_items": ["Find QA support"], "in_progress_items": ["Regression testing"],
                "risks": [{"title": "QA capacity", "description": "Support assigned", "impact": "low", "mitigation": "Monitor", "status": "resolved"}],
                "blockers": [], "decisions": [],
                "action_items": [{"title": "Find QA support", "details": "Support assigned", "owner": "Ava", "due_date": "2026-08-15", "status": "completed"}],
            },
        ]
        for title, notes in [("Weekly 1", "QA risk discussed"), ("Weekly 2", "QA support confirmed")]:
            response = self.client.post(f"/projects/{project_id}/meetings/new", data={"title": title, "provider": "groq", "model": "llama-3.3-70b-versatile", "meeting_notes": notes})
            self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertEqual(Meeting.query.count(), 2)
            self.assertEqual(Meeting.query.first().original_text, "QA risk discussed")
            risk = Risk.query.one()
            action = ActionItem.query.one()
            self.assertEqual(risk.status, "resolved")
            self.assertIsNotNone(risk.resolved_at)
            self.assertEqual(action.status, "completed")
            self.assertIsNotNone(action.completed_at)
            self.assertGreaterEqual(HistoryEvent.query.count(), 5)

        self.assertIn(b"QA risk discussed", self.client.get("/meetings/1").data)
        self.assertIn(b"Resolved risk: QA capacity", self.client.get(f"/projects/{project_id}/history").data)


if __name__ == "__main__":
    unittest.main()
