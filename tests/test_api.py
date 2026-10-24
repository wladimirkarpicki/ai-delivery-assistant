"""
HTTP-layer test suite for the FastAPI application (TestClient port of
the former Flask suite). The FakeRouter replaces the AI provider, and
an in-memory sqlite database keeps every test isolated.
"""

import json
import os
import unittest
from datetime import UTC, datetime
from typing import ClassVar

from fastapi.testclient import TestClient
from werkzeug.security import generate_password_hash

import api as api_module
from api import create_app
from database import db
from models import (
    ActionItem,
    Blocker,
    HistoryEvent,
    Meeting,
    Project,
    Risk,
    User,
)

# The JWT signing key only has to exist and stay constant for the
# process; it is read once per create_app() call below.
os.environ.setdefault("JWT_SECRET_KEY", "unit-test-secret-key-0123456789abcdef")


class FakeRouter:
    def __init__(self):
        self.responses = []
        self.embedded_texts = []
        self.prompts = []

    def get_models(self, provider):
        return ["openrouter/free", "unsupported-model"]

    def generate(self, provider, model, prompt):
        self.prompts.append(prompt)
        if not self.responses:
            # Return a minimal valid consolidation response to avoid IndexError
            return json.dumps({
                "risks": [], "blockers": [],
                "action_items": [], "decisions": [],
            })
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
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin-pass-123"
    REGULAR_USERNAME = "regular"
    REGULAR_PASSWORD = "regular-pass-123"

    def setUp(self):
        # In-process login rate limiting must not leak between tests.
        api_module._failed_logins.clear()

        self.router = FakeRouter()
        self.app = create_app(self.router, "sqlite://")
        db.create_all()
        self.client = TestClient(self.app)

        # Every business endpoint requires a signed-in account since
        # the auth feature, so the suite-wide client is an admin and a
        # regular account exists for role checks.
        self.admin_id = self.create_user_direct(
            self.ADMIN_USERNAME, self.ADMIN_PASSWORD, role="admin"
        )
        self.regular_id = self.create_user_direct(
            self.REGULAR_USERNAME, self.REGULAR_PASSWORD
        )
        self.admin_token = self.login(self.ADMIN_USERNAME, self.ADMIN_PASSWORD)
        self.client.headers["Authorization"] = f"Bearer {self.admin_token}"

    def tearDown(self):
        db.session.remove()
        db.drop_all()

    # ------------------------------------------------------------------
    # Helpers

    def create_user_direct(self, username, password, role="user"):
        """Create an account straight in the test database."""
        account = User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
        )
        db.session.add(account)
        db.session.commit()
        return account.id

    def login(self, username, password):
        response = self.client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["access_token"]

    def authed_client(self, token):
        """A fresh client carrying the given bearer token."""
        client = TestClient(self.app)
        client.headers["Authorization"] = f"Bearer {token}"
        return client

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

    ANALYSIS_ONE: ClassVar[dict] = {
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

    PLAN_CREATE: ClassVar[dict] = {
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

    ANALYSIS_TWO: ClassVar[dict] = {
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
        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE]

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
        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE]

        first = self.add_meeting(project_id, "Weekly 1", "QA risk discussed")
        self.assertEqual(first.status_code, 201)

        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE]
        second = self.add_meeting(project_id, "Weekly 1", "QA risk discussed")
        self.assertEqual(second.status_code, 400)
        self.assertIn("Identical meeting notes", second.json()["error"])

    def test_meeting_file_upload(self):
        project_id = self.create_project()
        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE]

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
        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE]
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
        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE]
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
        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE]
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
        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE]
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

    # ------------------------------------------------------------------
    # Metrics

    def test_metrics_totals_mix_status_and_per_project(self):
        project_id = self.create_project()
        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE]
        self.assertEqual(self.add_meeting(project_id, "Weekly 1", "QA risk discussed").status_code, 201)

        response = self.client.get("/api/metrics")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["totals"]["projects"], 1)
        self.assertEqual(body["totals"]["meetings"], 1)
        self.assertEqual(body["totals"]["decisions"], 0)
        self.assertEqual(body["totals"]["open_risks"], 1)
        self.assertEqual(body["totals"]["open_blockers"], 0)
        self.assertEqual(body["totals"]["open_actions"], 1)
        self.assertGreaterEqual(body["totals"]["history_events"], 3)

        # The mix mirrors the open totals, one entry per kind.
        self.assertEqual(
            {entry["kind"]: entry["count"] for entry in body["open_items_mix"]},
            {"risks": 1, "blockers": 0, "actions": 1},
        )

        # The only project has an analyzed state: "at_risk" -> "at risk".
        self.assertEqual(body["status_distribution"], [{"status": "at risk", "count": 1}])

        per_project = next(p for p in body["per_project"] if p["project_id"] == project_id)
        self.assertEqual(
            per_project,
            {
                "project_id": project_id,
                "name": "Phoenix",
                "meetings": 1,
                "open_risks": 1,
                "open_blockers": 0,
                "open_actions": 1,
            },
        )

    def test_metrics_counts_projects_without_state_as_unknown(self):
        project_id = self.create_project()
        self.router.responses = [self.ANALYSIS_ONE, self.PLAN_CREATE]
        self.assertEqual(self.add_meeting(project_id, "Weekly 1", "QA risk discussed").status_code, 201)
        self.create_project("Ghost", "Never had a meeting")

        body = self.client.get("/api/metrics").json()

        distribution = {entry["status"]: entry["count"] for entry in body["status_distribution"]}
        self.assertEqual(distribution.get("at risk"), 1)
        self.assertEqual(distribution.get("unknown"), 1)

        # Every project appears in per_project, analyzed or not.
        self.assertEqual(len(body["per_project"]), 2)
        ghost = next(p for p in body["per_project"] if p["name"] == "Ghost")
        self.assertEqual(
            ghost,
            {
                "project_id": ghost["project_id"],
                "name": "Ghost",
                "meetings": 0,
                "open_risks": 0,
                "open_blockers": 0,
                "open_actions": 0,
            },
        )

    def test_metrics_risk_impacts_owners_and_timeline(self):
        # Direct fixtures (not the AI pipeline): precise impacts,
        # owners, statuses, and created_at months to aggregate against.
        project_id = self.create_project("Atlas")

        august = Meeting(
            project_id=project_id,
            title="Weekly 1",
            original_text="text",
            analysis_text="analysis",
            analysis_json={},
            provider="openrouter",
            model="openrouter/free",
            created_at=datetime(2026, 8, 15, tzinfo=UTC),
        )
        db.session.add(august)
        db.session.flush()

        september = Meeting(
            project_id=project_id,
            title="Weekly 2",
            original_text="text two",
            analysis_text="analysis",
            analysis_json={},
            provider="openrouter",
            model="openrouter/free",
            created_at=datetime(2026, 9, 20, tzinfo=UTC),
        )
        db.session.add(september)
        db.session.flush()

        db.session.add_all([
            Risk(project_id=project_id, title="R1", impact="high", status="open",
                 created_in_meeting_id=august.id, updated_in_meeting_id=august.id),
            Risk(project_id=project_id, title="R2", impact="high", status="resolved",
                 created_in_meeting_id=august.id, updated_in_meeting_id=august.id),
            Risk(project_id=project_id, title="R3", impact="unknown", status="open",
                 created_in_meeting_id=august.id, updated_in_meeting_id=august.id),
            Blocker(project_id=project_id, title="B1", status="open",
                    created_in_meeting_id=august.id, updated_in_meeting_id=august.id),
            ActionItem(project_id=project_id, title="A1", owner="Ava", status="open",
                       created_in_meeting_id=august.id, updated_in_meeting_id=august.id),
            ActionItem(project_id=project_id, title="A2", owner="Ava", status="completed",
                       created_in_meeting_id=august.id, updated_in_meeting_id=august.id),
            ActionItem(project_id=project_id, title="A3", owner=None, status="open",
                       created_in_meeting_id=september.id, updated_in_meeting_id=september.id),
            HistoryEvent(project_id=project_id, meeting_id=august.id,
                         entity_type="risk", event_type="created",
                         summary="R1 created",
                         created_at=datetime(2026, 8, 20, tzinfo=UTC)),
            HistoryEvent(project_id=project_id, meeting_id=september.id,
                         entity_type="action_item", event_type="created",
                         summary="A3 created",
                         created_at=datetime(2026, 9, 22, tzinfo=UTC)),
            HistoryEvent(project_id=project_id, meeting_id=september.id,
                         entity_type="blocker", event_type="created",
                         summary="B1 created",
                         created_at=datetime(2026, 9, 25, tzinfo=UTC)),
        ])
        db.session.commit()

        body = self.client.get("/api/metrics").json()

        self.assertEqual(
            {entry["kind"]: entry["count"] for entry in body["open_items_mix"]},
            {"risks": 2, "blockers": 1, "actions": 2},
        )

        impacts = {entry["impact"]: entry for entry in body["risk_impacts"]}
        self.assertEqual(
            impacts["high"], {"impact": "high", "open": 1, "resolved": 1}
        )
        self.assertEqual(
            impacts["unknown"], {"impact": "unknown", "open": 1, "resolved": 0}
        )
        # High-severity impacts lead the breakdown.
        self.assertEqual(body["risk_impacts"][0]["impact"], "high")

        owners = body["action_owners"]
        self.assertEqual(
            owners[0], {"owner": "Ava", "open": 1, "completed": 1}
        )
        self.assertEqual(
            owners[1], {"owner": "unassigned", "open": 1, "completed": 0}
        )

        # Every month with data, ascending, with both series merged.
        self.assertEqual(
            body["activity_timeline"],
            [
                {"month": "2026-08", "meetings": 1, "events": 1},
                {"month": "2026-09", "meetings": 1, "events": 2},
            ],
        )

    def test_metrics_on_empty_database(self):
        body = self.client.get("/api/metrics").json()

        self.assertEqual(
            body["totals"],
            {
                "projects": 0,
                "meetings": 0,
                "decisions": 0,
                "history_events": 0,
                "open_risks": 0,
                "open_blockers": 0,
                "open_actions": 0,
            },
        )
        self.assertEqual(
            body["open_items_mix"],
            [
                {"kind": "risks", "count": 0},
                {"kind": "blockers", "count": 0},
                {"kind": "actions", "count": 0},
            ],
        )
        self.assertEqual(body["status_distribution"], [])
        self.assertEqual(body["per_project"], [])
        self.assertEqual(body["risk_impacts"], [])
        self.assertEqual(body["activity_timeline"], [])
        self.assertEqual(body["action_owners"], [])


    # ------------------------------------------------------------------
    # Authentication

    def test_setup_bootstraps_first_admin_only_once(self):
        db.session.query(User).delete()
        db.session.commit()

        first = self.client.post(
            "/api/auth/setup",
            json={"username": "founder", "password": "founder-pass-123"},
        )
        self.assertEqual(first.status_code, 200, first.text)
        body = first.json()
        self.assertEqual(body["user"]["role"], "admin")
        self.assertTrue(body["access_token"])

        # A second bootstrap is refused while any user exists.
        second = self.client.post(
            "/api/auth/setup",
            json={"username": "other", "password": "other-pass-123"},
        )
        self.assertEqual(second.status_code, 400)
        self.assertIn("already completed", second.json()["detail"])

    def test_setup_rejects_short_password(self):
        db.session.query(User).delete()
        db.session.commit()

        response = self.client.post(
            "/api/auth/setup",
            json={"username": "founder", "password": "short"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("at least 8 characters", response.json()["detail"])

    def test_login_ok_wrong_password_and_unknown_user(self):
        wrong = self.client.post(
            "/api/auth/login",
            json={"username": self.REGULAR_USERNAME, "password": "wrong-pass"},
        )
        self.assertEqual(wrong.status_code, 401)

        unknown = self.client.post(
            "/api/auth/login",
            json={"username": "ghost", "password": "whatever-pass"},
        )
        self.assertEqual(unknown.status_code, 401)

        ok = self.client.post(
            "/api/auth/login",
            json={"username": self.REGULAR_USERNAME, "password": self.REGULAR_PASSWORD},
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        body = ok.json()
        self.assertEqual(body["user"]["username"], self.REGULAR_USERNAME)
        self.assertEqual(body["user"]["role"], "user")
        self.assertTrue(body["access_token"])

    def test_login_locks_after_five_failures(self):
        for _ in range(5):
            response = self.client.post(
                "/api/auth/login",
                json={"username": self.REGULAR_USERNAME, "password": "wrong-pass"},
            )
            self.assertEqual(response.status_code, 401)

        # Even the correct password is locked out now.
        locked = self.client.post(
            "/api/auth/login",
            json={"username": self.REGULAR_USERNAME, "password": self.REGULAR_PASSWORD},
        )
        self.assertEqual(locked.status_code, 429)
        self.assertIn("15 minutes", locked.json()["detail"])

        # The lockout only affects the targeted username.
        other = self.client.post(
            "/api/auth/login",
            json={"username": self.ADMIN_USERNAME, "password": self.ADMIN_PASSWORD},
        )
        self.assertEqual(other.status_code, 200)

    def test_me_requires_a_valid_token(self):
        anonymous = TestClient(self.app)
        self.assertEqual(anonymous.get("/api/auth/me").status_code, 401)

        garbage = TestClient(self.app)
        garbage.headers["Authorization"] = "Bearer not-a-jwt"
        self.assertEqual(garbage.get("/api/auth/me").status_code, 401)

        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], self.ADMIN_USERNAME)
        self.assertEqual(response.json()["role"], "admin")

    def test_token_of_deleted_account_is_rejected(self):
        token = self.login(self.REGULAR_USERNAME, self.REGULAR_PASSWORD)
        client = self.authed_client(token)
        self.assertEqual(client.get("/api/auth/me").status_code, 200)

        self.assertEqual(self.client.delete(f"/api/users/{self.regular_id}").status_code, 200)
        self.assertEqual(client.get("/api/auth/me").status_code, 401)

    def test_self_service_password_change(self):
        response = self.client.post(
            "/api/auth/password",
            json={
                "current_password": self.ADMIN_PASSWORD,
                "password": "brand-new-pass-1",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)

        old = self.client.post(
            "/api/auth/login",
            json={"username": self.ADMIN_USERNAME, "password": self.ADMIN_PASSWORD},
        )
        self.assertEqual(old.status_code, 401)

        new = self.client.post(
            "/api/auth/login",
            json={"username": self.ADMIN_USERNAME, "password": "brand-new-pass-1"},
        )
        self.assertEqual(new.status_code, 200)

    def test_password_change_requires_current_password(self):
        response = self.client.post(
            "/api/auth/password",
            json={"current_password": "wrong-pass", "password": "brand-new-pass-1"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Current password is incorrect", response.json()["detail"])

    # ------------------------------------------------------------------
    # Users (admin management)

    def test_users_endpoints_require_admin(self):
        anonymous = TestClient(self.app)
        self.assertEqual(anonymous.get("/api/users").status_code, 401)

        user_client = self.authed_client(
            self.login(self.REGULAR_USERNAME, self.REGULAR_PASSWORD)
        )
        self.assertEqual(user_client.get("/api/users").status_code, 403)

        response = self.client.get("/api/users")
        self.assertEqual(response.status_code, 200)
        users = response.json()
        self.assertEqual(
            [u["username"] for u in users],
            [self.ADMIN_USERNAME, self.REGULAR_USERNAME],
        )
        you = [u for u in users if u["is_you"]]
        self.assertEqual(len(you), 1)
        self.assertEqual(you[0]["username"], self.ADMIN_USERNAME)

    def test_users_crud(self):
        created = self.client.post(
            "/api/users",
            json={"username": "newbie", "password": "newbie-pass-123", "role": "user"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        new_id = created.json()["id"]
        self.assertEqual(created.json()["is_you"], False)

        # Duplicate usernames are rejected.
        duplicate = self.client.post(
            "/api/users",
            json={"username": "newbie", "password": "other-pass-123", "role": "user"},
        )
        self.assertEqual(duplicate.status_code, 400)

        # Unknown roles are rejected.
        bad_role = self.client.post(
            "/api/users",
            json={"username": "hacker", "password": "other-pass-123", "role": "root"},
        )
        self.assertEqual(bad_role.status_code, 400)
        bad_patch = self.client.patch(f"/api/users/{new_id}", json={"role": "root"})
        self.assertEqual(bad_patch.status_code, 400)

        # Role change.
        patched = self.client.patch(f"/api/users/{new_id}", json={"role": "admin"})
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["role"], "admin")

        # Password change through the admin patch endpoint.
        patched = self.client.patch(f"/api/users/{new_id}", json={"password": "patched-pass-123"})
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"username": "newbie", "password": "patched-pass-123"},
            ).status_code,
            200,
        )

        # Missing records -> 404.
        self.assertEqual(
            self.client.patch("/api/users/99999", json={"role": "user"}).status_code, 404
        )
        self.assertEqual(self.client.delete("/api/users/99999").status_code, 404)
        self.assertEqual(
            self.client.post("/api/users/99999/password", json={"password": "reset-pass-123"}).status_code,
            404,
        )

        # Admin password reset gives access with the new password.
        reset = self.client.post(
            f"/api/users/{new_id}/password", json={"password": "reset-pass-123"}
        )
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"username": "newbie", "password": "reset-pass-123"},
            ).status_code,
            200,
        )

        # Delete.
        self.assertEqual(self.client.delete(f"/api/users/{new_id}").status_code, 200)
        self.assertEqual(len(self.client.get("/api/users").json()), 2)

    def test_last_admin_protections(self):
        demote = self.client.patch(f"/api/users/{self.admin_id}", json={"role": "user"})
        self.assertEqual(demote.status_code, 400)
        self.assertIn("last remaining admin", demote.json()["detail"])

        # Self-delete is its own refusal, checked before last-admin.
        self_delete = self.client.delete(f"/api/users/{self.admin_id}")
        self.assertEqual(self_delete.status_code, 400)
        self.assertIn("delete yourself", self_delete.json()["detail"])

        # A second admin can be demoted and deleted while one remains.
        second = self.client.post(
            "/api/users",
            json={"username": "second-admin", "password": "second-pass-123", "role": "admin"},
        )
        self.assertEqual(second.status_code, 200)
        second_id = second.json()["id"]

        self.assertEqual(
            self.client.patch(f"/api/users/{second_id}", json={"role": "user"}).status_code,
            200,
        )
        self.assertEqual(
            self.client.delete(f"/api/users/{second_id}").status_code, 200
        )

    # ------------------------------------------------------------------
    # Route protection

    def test_health_stays_public_business_requires_auth(self):
        anonymous = TestClient(self.app)

        # The Docker healthcheck depends on this staying public.
        self.assertEqual(anonymous.get("/api/health").status_code, 200)

        for path in ("/api/dashboard", "/api/metrics", "/api/projects"):
            self.assertEqual(anonymous.get(path).status_code, 401, path)

        self.assertEqual(
            anonymous.post("/api/projects", json={"name": "X"}).status_code, 401
        )

    def test_regular_user_can_read_business_endpoints(self):
        user_client = self.authed_client(
            self.login(self.REGULAR_USERNAME, self.REGULAR_PASSWORD)
        )

        self.assertEqual(user_client.get("/api/dashboard").status_code, 200)
        self.assertEqual(user_client.get("/api/metrics").status_code, 200)
        self.assertEqual(user_client.get("/api/projects").status_code, 200)


if __name__ == "__main__":
    unittest.main()
