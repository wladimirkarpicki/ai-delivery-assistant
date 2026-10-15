import json
import re
import unittest

from app import create_app
from database import db
from models import ActionItem, Decision, HistoryEvent, Meeting, Project, Risk
from project_memory import apply_consolidation_plan


class FakeRouter:
    def __init__(self):
        self.responses = []

    def get_models(self, provider):
        return ["openrouter/free", "unsupported-model"]

    def generate(self, provider, model, prompt):
        return json.dumps(self.responses.pop(0))


class FlaskAppTests(unittest.TestCase):
    def setUp(self):
        self.router = FakeRouter()
        self.app = create_app(self.router, "sqlite://")
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
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

    def test_projects_page_and_add_meeting_form(self):
        response = self.client.get("/projects")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"New project", response.data)
        response = self.client.get(f"/projects/{self.create_project()}/meetings/new")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'name="model"', response.data)
        self.assertNotIn(b"AI model", response.data)
        self.assertIn(b"Analyze and save", response.data)

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
            # Deliberately invalid consolidation output: forces the app to
            # fall back to exact-title reconciliation, which is the path
            # these assertions exercise.
            "not-a-valid-consolidation-plan",
            {
                "executive_summary": "QA support confirmed.", "project_status": "on_track", "progress_summary": "Testing is staffed.",
                "completed_items": ["Find QA support"], "in_progress_items": ["Regression testing"],
                "risks": [{"title": "QA capacity", "description": "Support assigned", "impact": "low", "mitigation": "Monitor", "status": "resolved"}],
                "blockers": [], "decisions": [],
                "action_items": [{"title": "Find QA support", "details": "Support assigned", "owner": "Ava", "due_date": "2026-08-15", "status": "completed"}],
            },
        ]
        for title, notes in [("Weekly 1", "QA risk discussed"), ("Weekly 2", "QA support confirmed")]:
            response = self.client.post(f"/projects/{project_id}/meetings/new", data={"title": title, "meeting_notes": notes})
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


    def test_consolidation_guardrails(self):
        project_id = self.create_project()

        with self.app.app_context():
            project = db.session.get(Project, project_id)

            meeting = Meeting(
                project_id=project_id,
                title="Guardrails fixture",
                original_text="notes",
                analysis_text="{}",
                analysis_json={},
                provider="openrouter",
                model="openrouter/free",
            )
            db.session.add(meeting)
            db.session.flush()

            risk = Risk(
                project_id=project_id,
                title="QA capacity",
                created_in_meeting_id=meeting.id,
                updated_in_meeting_id=meeting.id,
            )
            db.session.add(risk)
            db.session.flush()

            other_project = Project(name="Other", description="")
            db.session.add(other_project)
            db.session.flush()

            other_risk = Risk(
                project_id=other_project.id,
                title="Foreign risk",
                created_in_meeting_id=meeting.id,
                updated_in_meeting_id=meeting.id,
            )
            db.session.add(other_risk)
            db.session.flush()

            plan = {
                "risks": [
                    # Lowercase decision is normalized and applied.
                    {
                        "decision": "update",
                        "existing_item_id": risk.id,
                        "new_item": {
                            "title": "QA capacity",
                            "status": "resolved",
                            "description": "Support assigned",
                        },
                        "reason": "meeting says resolved",
                    },
                    # An id from another project must never be written.
                    {
                        "decision": "UPDATE",
                        "existing_item_id": other_risk.id,
                        "new_item": {"title": "QA capacity", "status": "resolved"},
                        "reason": "hallucinated id",
                    },
                    # A resolution decision without an id is preserved.
                    {
                        "decision": "MERGE",
                        "new_item": {"title": "QA capacity"},
                        "reason": "no id",
                    },
                    # An unknown decision verb is preserved.
                    {
                        "decision": "UPSERT",
                        "new_item": {"title": "Something new"},
                        "reason": "unknown verb",
                    },
                    # A plan entry without a title is preserved.
                    {
                        "decision": "CREATE",
                        "new_item": {"description": "no title"},
                        "reason": "empty finding",
                    },
                ],
                "action_items": [],
                "blockers": [],
                "decisions": [
                    {
                        "decision": "CREATE",
                        "new_item": {"title": "Adopt flow", "details": "d"},
                    },
                    # Decision records are append-only: non-CREATE is preserved.
                    {
                        "decision": "UPDATE",
                        "existing_item_id": 1,
                        "new_item": {"title": "Rewrite"},
                        "reason": "not supported",
                    },
                ],
            }

            apply_consolidation_plan(project, meeting, plan)
            db.session.commit()

            # A valid UPDATE now stamps the resolution audit fields.
            risk = db.session.get(Risk, risk.id)
            self.assertEqual(risk.status, "resolved")
            self.assertIsNotNone(risk.resolved_at)
            self.assertEqual(risk.resolved_in_meeting_id, meeting.id)

            # The foreign risk was not touched by the hallucinated id.
            other_risk = db.session.get(Risk, other_risk.id)
            self.assertEqual(other_risk.status, "open")
            self.assertIsNone(other_risk.resolved_at)

            # The valid CREATE decision was recorded.
            self.assertIsNotNone(
                db.session.scalar(db.select(Decision).filter_by(title="Adopt flow"))
            )

            # Every unapplicable plan entry produced a needs_review event.
            review_events = HistoryEvent.query.filter_by(
                event_type="needs_review",
            ).all()
            self.assertEqual(len(review_events), 5)

            summaries = " | ".join(event.summary for event in review_events)
            self.assertIn("(foreign;", summaries)
            self.assertIn("(missing;", summaries)
            self.assertIn("(unknown_decision;", summaries)
            self.assertIn("(missing_title;", summaries)
            self.assertIn("(unsupported_decision;", summaries)


    def test_csrf_enforced_on_forms(self):
        app = create_app(self.router, "sqlite://")
        with app.app_context():
            db.create_all()
        client = app.test_client()

        # A POST without a token is rejected.
        response = client.post("/projects", data={"name": "No token"})
        self.assertEqual(response.status_code, 400)

        # The form carries a token and the same POST succeeds.
        page = client.get("/projects").get_data(as_text=True)
        token = re.search(
            r'name="csrf_token"\s+value="([^"]+)"',
            page,
        ).group(1)
        response = client.post(
            "/projects",
            data={"name": "With token", "csrf_token": token},
        )
        self.assertEqual(response.status_code, 302)

    def test_404_page(self):
        response = self.client.get("/projects/99999")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Page not found", response.data)

    def test_500_page(self):
        app = create_app(self.router, "sqlite://")
        with app.app_context():
            db.create_all()

        @app.route("/boom")
        def boom():
            raise RuntimeError("boom")

        response = app.test_client().get("/boom")
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Something went wrong", response.data)


if __name__ == "__main__":
    unittest.main()
