"""
HTTP-layer test suite for the FastAPI application (TestClient port of
the former Flask suite). The FakeRouter replaces the AI provider, and
an in-memory sqlite database keeps every test isolated.
"""

import json
import unittest

from database import db
from fastapi.testclient import TestClient

from api import create_app
from models import (
    ActionItem,
    HistoryEvent,
    Meeting,
    Project,
    Risk,
)


class FakeRouter:
    def __init__(self):
        self.responses = []
        self.embedded_texts = []
        self.prompts = []

    def get_models(self, provider):
        return ["openrouter/free", "unsupported-model"]

    def generate(self, provider, model, prompt):
        self.prompts.append(prompt)
        return json.dumps(self.responses.pop(0))

    def embed_texts(self, provider, model, texts):
        # Deterministic vectors: QA/tester-related titles map to one
        # direction, everything else to another, so tests can create
        # semantic matches with zero lexical overlap.
        self.embedded_texts.extend(texts)
        return [
            [1.0, 0.0] if ("qa" in t or "tester" in t) else [0.0, 1.0]
            for t in texts
        ]


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.router = FakeRouter()
        self.app = create_app(self.router, "sqlite://")
        db.create_all()
        self.client = TestClient(self.app)

    def tearDown(self):
        db.session.remove()
        db.drop_all()

    # ------------------------------------------------------------------
    # Helpers

    def create_project(self, name="Phoenix", description="Release project"):
        response = self.client.post(
            "/api/projects", json={"name": name, "description": description}
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def add_meeting(self, project_id, title, notes):
        return self.client.post(
            f"/api/projects/{project_id}/meetings",
            data={"title": title, "meeting_notes": notes},
        )

    ANALYSIS_ONE = {
        "executive_summary": "QA is constrained.",
        "project_status": "at_risk",
        "progress_summary": "Testing is delayed.",
        "completed_items": [],
        "in_progress_items": ["Regression testing"],
        "risks": [{
            "title": "QA capacity", "description": "One tester",
            "impact": "high", "mitigation": "Borrow support", "status": "open",
        }],
        "blockers": [],
        "decisions": [],
        "action_items": [{
            "title": "Find QA support", "details": "Ask support team",
            "owner": "Ava", "due_date": "2026-08-15", "status": "open",
        }],
    }

    PLAN_CREATE = {
        "risks": [{"decision": "CREATE", "new_item": {
            "title": "QA capacity", "description": "One tester",
            "impact": "high", "mitigation": "Borrow support", "status": "open",
        }, "reason": "no similar open risk"}],
        "blockers": [],
        "action_items": [{"decision": "CREATE", "new_item": {
            "title": "Find QA support", "details": "Ask support team",
            "owner": "Ava", "due_date": "2026-08-15", "status": "open",
        }, "reason": "no similar open action"}],
        "decisions": [],
    }

    ANALYSIS_TWO = {
        "executive_summary": "QA support confirmed.",
        "project_status": "on_track",
        "progress_summary": "Testing is staffed.",
        "completed_items": ["Find QA support"],
        "in_progress_items": ["Regression testing"],
        "risks": [{
            "title": "QA capacity", "description": "Support assigned",
            "impact": "low", "mitigation": "Monitor", "status": "resolved",
        }],
        "blockers": [],
        "decisions": [],
        "action_items": [{
            "title": "Find QA support", "details": "Support assigned",
            "owner": "Ava", "due_date": "2026-08-15", "status": "completed",
        }],
    }

    # ------------------------------------------------------------------
    # Health

    def test_health_reports_analysis_ready(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["analysis_ready"])
        self.assertIn("openrouter/free", body["model"])

    # ------------------------------------------------------------------
    # Projects

    def test_project_create_list_and_validation(self):
        project_id = self.create_project()

        response = self.client.get("/api/projects")
        self.assertEqual(response.status_code, 200)
        names = [p["name"] for p in response.json()["projects"]]
        self.assertIn("Phoenix", names)

        response = self.client.get(f"/api/projects/{project_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project"]["name"], "Phoenix")

        # Duplicate names are rejected.
        response = self.client.post(
            "/api/projects", json={"name": "Phoenix", "description": ""}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("exists", response.json()["error"].lower())

        # A blank name is rejected.
        response = self.client.post("/api/projects", json={"name": "   "})
        self.assertEqual(response.status_code, 400)

        # Unknown project -> 404.
        response = self.client.get("/api/projects/99999")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # Meetings and memory

    def test_add_meeting_creates_findings_and_history(self):
        project_id = self.create_project()
        self.router.responses = [self.ANALYSIS_ONE]

        response = self.add_meeting(project_id, "Weekly 1", "QA risk discussed")
        self.assertEqual(response.status_code, 201, response.text)
        meeting_id = response.json()["meeting_id"]

        # The router consumed exactly its planned call.
        self.assertEqual(self.router.responses, [])

        detail = self.client.get(f"/api/meetings/{meeting_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["meeting"]["original_text"], "QA risk discussed")
        self.assertEqual(
            body["meeting"]["analysis_json"]["project_status"], "at_risk"
        )

        overview = self.client.get(f"/api/projects/{project_id}").json()
        self.assertEqual(overview["meeting_count"], 1)
        self.assertEqual(
            [r["title"] for r in overview["risks"]], ["QA capacity"]
        )
        self.assertEqual(
            [a["title"] for a in overview["actions"]], ["Find QA support"]
        )
        self.assertEqual(overview["state"]["delivery_status"], "at_risk")

        events = self.client.get(f"/api/projects/{project_id}/history").json()
        summaries = [e["summary"] for e in events["events"]]
        self.assertTrue(any("QA capacity" in s for s in summaries))

    def test_add_meeting_validation(self):
        project_id = self.create_project()

        response = self.add_meeting(project_id, "Weekly 1", "   ")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Upload meeting notes", response.json()["error"])

    def test_duplicate_meeting_notes_rejected(self):
        project_id = self.create_project()
        self.router.responses = [self.ANALYSIS_ONE]

        first = self.add_meeting(project_id, "Weekly 1", "QA risk discussed")
        self.assertEqual(first.status_code, 201)

        self.router.responses = [self.ANALYSIS_ONE]
        second = self.add_meeting(project_id, "Weekly 1", "QA risk discussed")
        self.assertEqual(second.status_code, 400)
        self.assertIn("Identical meeting notes", second.json()["error"])

    def test_meeting_file_upload(self):
        project_id = self.create_project()
        self.router.responses = [self.ANALYSIS_ONE]

        response = self.client.post(
            f"/api/projects/{project_id}/meetings",
            data={"title": "Upload 1", "meeting_notes": ""},
            files={"meeting_file": ("notes.txt", b"QA risk discussed", "text/plain")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        meeting_id = response.json()["meeting_id"]

        body = self.client.get(f"/api/meetings/{meeting_id}").json()
        self.assertEqual(body["meeting"]["source_filename"], "notes.txt")
        self.assertEqual(body["meeting"]["original_text"], "QA risk discussed")

    def test_second_meeting_resolves_items_deterministically(self):
        project_id = self.create_project()
        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE, self.ANALYSIS_TWO]

        self.assertEqual(self.add_meeting(project_id, "Weekly 1", "QA risk discussed").status_code, 201)
        self.assertEqual(self.add_meeting(project_id, "Weekly 2", "QA support confirmed").status_code, 201)

        # The second analysis exact-matched by title with a status flip,
        # so it was resolved deterministically: no consolidation call.
        self.assertEqual(self.router.responses, [])

        risk = db.session.query(Risk).one()
        action = db.session.query(ActionItem).one()
        self.assertEqual(risk.status, "resolved")
        self.assertIsNotNone(risk.resolved_at)
        self.assertEqual(action.status, "completed")
        self.assertIsNotNone(action.completed_at)
        self.assertGreaterEqual(db.session.query(HistoryEvent).count(), 5)

        events = self.client.get(f"/api/projects/{project_id}/history").json()
        summaries = [e["summary"] for e in events["events"]]
        self.assertTrue(any("Updated risk" in s for s in summaries))

    def test_meeting_detail_404(self):
        response = self.client.get("/api/meetings/424242")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # Review queue

    def test_review_queue_resolve_create(self):
        project_id = self.create_project()

        # Build a meeting, then force a rejected finding into the
        # review queue by applying a CONFLICT plan decision through
        # the same pipeline the endpoint uses. The finding title is
        # new, so the review "create" action is allowed to apply it.
        self.router.responses = [self.ANALYSIS_ONE]
        self.assertEqual(self.add_meeting(project_id, "Weekly 1", "QA risk discussed").status_code, 201)

        conflict_plan = {
            "risks": [{"decision": "CONFLICT", "new_item": {
                "title": "Vendor lock-in", "description": "Contradictory info",
                "impact": "high", "mitigation": "Unknown", "status": "open",
            }, "reason": "contradicts existing memory"}],
            "blockers": [], "action_items": [], "decisions": [],
        }
        from project_memory import apply_consolidation_plan

        meeting = db.session.query(Meeting).one()
        project = db.session.get(Project, project_id)
        apply_consolidation_plan(project, meeting, conflict_plan)
        # The API request handlers commit themselves; a direct pipeline
        # call must do the same so the request-scoped sessions see it.
        db.session.commit()

        queue = self.client.get(f"/api/projects/{project_id}/review")
        self.assertEqual(queue.status_code, 200)
        items = queue.json()["queue"]
        self.assertEqual(len(items), 1)
        event_id = items[0]["event"]["id"]

        resolved = self.client.post(
            f"/api/projects/{project_id}/review/{event_id}/resolve",
            json={"action": "create"},
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertTrue(resolved.json()["ok"])

        # Resolving again is rejected: the event is no longer pending
        # (Flask flashed the same error and redirected back).
        again = self.client.post(
            f"/api/projects/{project_id}/review/{event_id}/resolve",
            json={"action": "create"},
        )
        self.assertEqual(again.status_code, 400)
        self.assertIn("already resolved", again.json()["error"])

        queue = self.client.get(f"/api/projects/{project_id}/review").json()
        self.assertEqual(queue["queue"], [])

    # ------------------------------------------------------------------
    # Manual resolution

    def test_manual_resolve_idempotent_and_reopen(self):
        project_id = self.create_project()
        self.router.responses = [self.ANALYSIS_ONE]
        self.assertEqual(self.add_meeting(project_id, "Weekly 1", "QA risk discussed").status_code, 201)

        risk = db.session.query(Risk).one()

        first = self.client.post(
            f"/api/projects/{project_id}/items/risk/{risk.id}/resolve",
            json={"action": "resolve", "note": "handled"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["level"], "success")

        # Second resolve: idempotent no-op surfaced as a warning.
        second = self.client.post(
            f"/api/projects/{project_id}/items/risk/{risk.id}/resolve",
            json={"action": "resolve"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["level"], "warning")

        reopened = self.client.post(
            f"/api/projects/{project_id}/items/risk/{risk.id}/resolve",
            json={"action": "reopen"},
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["level"], "success")

        overview = self.client.get(f"/api/projects/{project_id}").json()
        self.assertEqual(len(overview["risks"]), 1)
        self.assertEqual(len(overview["resolved_risks"]), 0)

    # ------------------------------------------------------------------
    # Report and dashboard

    def test_report_view_and_download(self):
        project_id = self.create_project()
        self.router.responses = [self.ANALYSIS_ONE]
        self.assertEqual(self.add_meeting(project_id, "Weekly 1", "QA risk discussed").status_code, 201)

        response = self.client.get(f"/api/projects/{project_id}/report")
        self.assertEqual(response.status_code, 200)
        report = response.json()["report"]
        self.assertIn("Phoenix", report)

        download = self.client.get(f"/api/projects/{project_id}/report?download=1")
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download.headers.get("content-disposition", ""))

        missing = self.client.get("/api/projects/99999/report")
        self.assertEqual(missing.status_code, 404)

    def test_dashboard_rows(self):
        project_id = self.create_project()
        self.router.responses = [self.ANALYSIS_ONE]
        self.assertEqual(self.add_meeting(project_id, "Weekly 1", "QA risk discussed").status_code, 201)

        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        row = next(r for r in rows if r["project"]["id"] == project_id)
        # The API keeps the Flask dashboard's humanized status.
        self.assertEqual(row["status"], "at risk")
        self.assertEqual(row["open_risks"], 1)
        self.assertEqual(row["open_actions"], 1)
        self.assertEqual(row["meeting_count"], 1)


if __name__ == "__main__":
    unittest.main()
