import json
import re
import unittest

from app import create_app
from database import db
from models import (
    ActionItem,
    Decision,
    HistoryEvent,
    Meeting,
    Project,
    ReviewResolution,
    Risk,
)
from project_memory import apply_consolidation_plan


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
        # Meeting 1: the LLM plan creates the first risk and action
        # item. Meeting 2: both findings exact-match by title with a
        # status flip, so they are resolved deterministically without
        # a second LLM consolidation call.
        self.router.responses = [
            {
                "executive_summary": "QA is constrained.", "project_status": "at_risk", "progress_summary": "Testing is delayed.",
                "completed_items": [], "in_progress_items": ["Regression testing"],
                "risks": [{"title": "QA capacity", "description": "One tester", "impact": "high", "mitigation": "Borrow support", "status": "open"}],
                "blockers": [], "decisions": [],
                "action_items": [{"title": "Find QA support", "details": "Ask support team", "owner": "Ava", "due_date": "2026-08-15", "status": "open"}],
            },
            {
                "risks": [{"decision": "CREATE", "new_item": {"title": "QA capacity", "description": "One tester", "impact": "high", "mitigation": "Borrow support", "status": "open"}, "reason": "no similar open risk"}],
                "blockers": [],
                "action_items": [{"decision": "CREATE", "new_item": {"title": "Find QA support", "details": "Ask support team", "owner": "Ava", "due_date": "2026-08-15", "status": "open"}, "reason": "no similar open action"}],
                "decisions": [],
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
            response = self.client.post(f"/projects/{project_id}/meetings/new", data={"title": title, "meeting_notes": notes})
            self.assertEqual(response.status_code, 302)

        # Both meetings consumed exactly their planned LLM calls: the
        # second meeting was resolved deterministically.
        self.assertEqual(self.router.responses, [])

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
        self.assertIn(b"Updated risk: QA capacity", self.client.get(f"/projects/{project_id}/history").data)


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


    def test_consolidation_fallback_applies_state_and_items(self):
        project_id = self.create_project()
        self.router.responses = [
            {
                "executive_summary": "Blocked.", "project_status": "off_track", "progress_summary": "Nothing moved.",
                "completed_items": [], "in_progress_items": [],
                "risks": [{"title": "Deployment risk", "description": "No credentials", "impact": "high", "mitigation": "Request access", "status": "open"}],
                "blockers": [], "decisions": [],
                "action_items": [],
            },
            "not-a-valid-consolidation-plan",
        ]

        response = self.client.post(
            f"/projects/{project_id}/meetings/new",
            data={"title": "Weekly", "meeting_notes": "Deployment risk discussed"},
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            risk = Risk.query.one()
            self.assertEqual(risk.title, "Deployment risk")
            self.assertEqual(risk.canonical_title, "deployment risk")

            # The fallback path still applies the project state.
            project = db.session.get(Project, project_id)
            self.assertEqual(project.state.delivery_status, "off_track")

            summaries = [event.summary for event in HistoryEvent.query.all()]
            self.assertTrue(
                any("Recorded risk: Deployment risk" in s for s in summaries)
            )

    def test_exact_duplicate_title_merged_without_second_llm_call(self):
        project_id = self.create_project()
        self.router.responses = [
            {
                "executive_summary": "API unstable.", "project_status": "at_risk", "progress_summary": "Flaky tests.",
                "completed_items": [], "in_progress_items": [],
                "risks": [{"title": "API instability", "description": "Flaky responses", "impact": "medium", "mitigation": "Investigate", "status": "open"}],
                "blockers": [], "decisions": [],
                "action_items": [],
            },
            {
                "risks": [{"decision": "CREATE", "new_item": {"title": "API instability", "description": "Flaky responses", "impact": "medium", "mitigation": "Investigate", "status": "open"}, "reason": "new risk"}],
                "blockers": [],
                "action_items": [],
                "decisions": [],
            },
            {
                "executive_summary": "Still unstable.", "project_status": "at_risk", "progress_summary": "Flaky tests.",
                "completed_items": [], "in_progress_items": [],
                "risks": [{"title": "API Instability", "description": "Mentioned again", "impact": "medium", "mitigation": "Investigate", "status": "open"}],
                "blockers": [], "decisions": [],
                "action_items": [],
            },
        ]

        for title, notes in (
            ("Weekly 1", "API instability raised"),
            ("Weekly 2", "API instability follow-up"),
        ):
            response = self.client.post(
                f"/projects/{project_id}/meetings/new",
                data={"title": title, "meeting_notes": notes},
            )
            self.assertEqual(response.status_code, 302)

        # The second meeting exact-matched deterministically: only the
        # two planned LLM calls were made.
        self.assertEqual(self.router.responses, [])

        with self.app.app_context():
            self.assertEqual(Risk.query.count(), 1)

            # The merge kept the original description, and the duplicate
            # merge is visible in history.
            risk = Risk.query.one()
            self.assertEqual(risk.description, "Flaky responses")

            summaries = [event.summary for event in HistoryEvent.query.all()]
            self.assertTrue(any("Merged duplicate risk" in s for s in summaries))


    def test_duplicate_creates_within_one_plan_are_merged(self):
        project_id = self.create_project()

        with self.app.app_context():
            project = db.session.get(Project, project_id)

            meeting = Meeting(
                project_id=project_id,
                title="Duplicate CREATE fixture",
                original_text="notes",
                analysis_text="{}",
                analysis_json={},
                provider="openrouter",
                model="openrouter/free",
            )
            db.session.add(meeting)
            db.session.flush()

            plan = {
                "risks": [
                    {
                        "decision": "CREATE",
                        "new_item": {"title": "QA capacity", "status": "open"},
                        "reason": "first",
                    },
                    {
                        "decision": "CREATE",
                        "new_item": {"title": "QA Capacity", "status": "open"},
                        "reason": "second",
                    },
                ],
                "blockers": [],
                "action_items": [],
                "decisions": [
                    {
                        "decision": "CREATE",
                        "new_item": {"title": "Adopt flow"},
                        "reason": "first",
                    },
                    {
                        "decision": "CREATE",
                        "new_item": {"title": "Adopt Flow"},
                        "reason": "second",
                    },
                ],
            }

            apply_consolidation_plan(project, meeting, plan)
            db.session.commit()

            self.assertEqual(Risk.query.count(), 1)
            self.assertEqual(Decision.query.count(), 1)

            summaries = " | ".join(
                event.summary for event in HistoryEvent.query.all()
            )
            self.assertIn("duplicate CREATE within the same plan", summaries)


    def test_identical_meeting_notes_are_rejected(self):
        project_id = self.create_project()
        self.router.responses = [
            {
                "executive_summary": "QA constrained.", "project_status": "at_risk", "progress_summary": "Tight.",
                "completed_items": [], "in_progress_items": [],
                "risks": [{"title": "QA capacity", "status": "open"}],
                "blockers": [], "decisions": [], "action_items": [],
            },
            {
                "risks": [{"decision": "CREATE", "new_item": {"title": "QA capacity", "status": "open"}, "reason": "new"}],
                "blockers": [], "action_items": [], "decisions": [],
            },
        ]

        first = self.client.post(
            f"/projects/{project_id}/meetings/new",
            data={"title": "Weekly", "meeting_notes": "QA capacity discussed"},
        )
        self.assertEqual(first.status_code, 302)

        second = self.client.post(
            f"/projects/{project_id}/meetings/new",
            data={"title": "Weekly again", "meeting_notes": "QA capacity discussed"},
        )

        # Re-submitting identical notes is rejected without an LLM call.
        self.assertEqual(second.status_code, 200)
        self.assertIn(b"Identical meeting notes already exist", second.data)
        self.assertEqual(self.router.responses, [])

        with self.app.app_context():
            self.assertEqual(Meeting.query.count(), 1)
            self.assertEqual(Risk.query.count(), 1)
            self.assertEqual(HistoryEvent.query.count(), 2)

    def test_resolved_risk_reopened_without_duplicate(self):
        project_id = self.create_project()
        self.router.responses = [
            {
                "executive_summary": "QA constrained.", "project_status": "at_risk", "progress_summary": "Tight.",
                "completed_items": [], "in_progress_items": [],
                "risks": [{"title": "QA capacity", "status": "open"}],
                "blockers": [], "decisions": [], "action_items": [],
            },
            {
                "risks": [{"decision": "CREATE", "new_item": {"title": "QA capacity", "status": "open"}, "reason": "new"}],
                "blockers": [], "action_items": [], "decisions": [],
            },
            {
                "executive_summary": "QA resolved.", "project_status": "on_track", "progress_summary": "Staffed.",
                "completed_items": [], "in_progress_items": [],
                "risks": [{"title": "QA capacity", "status": "resolved"}],
                "blockers": [], "decisions": [], "action_items": [],
            },
            {
                "executive_summary": "QA slipped again.", "project_status": "at_risk", "progress_summary": "Tight.",
                "completed_items": [], "in_progress_items": [],
                "risks": [{"title": "QA capacity", "status": "open"}],
                "blockers": [], "decisions": [], "action_items": [],
            },
        ]

        for title, notes in (
            ("Weekly 1", "QA capacity raised"),
            ("Weekly 2", "QA capacity resolved"),
            ("Weekly 3", "QA capacity reopened"),
        ):
            response = self.client.post(
                f"/projects/{project_id}/meetings/new",
                data={"title": title, "meeting_notes": notes},
            )
            self.assertEqual(response.status_code, 302)

        # Both flips were deterministic: only the first meeting used
        # the LLM for consolidation.
        self.assertEqual(self.router.responses, [])

        with self.app.app_context():
            # One canonical row across open -> resolved -> reopened.
            self.assertEqual(Risk.query.count(), 1)

            risk = Risk.query.one()
            self.assertEqual(risk.status, "open")
            self.assertIsNone(risk.resolved_at)
            self.assertEqual(risk.canonical_title, "qa capacity")

            summaries = " | ".join(
                event.summary for event in HistoryEvent.query.all()
            )
            self.assertEqual(
                summaries.count("Updated risk: QA capacity"), 2
            )

    def test_duplicate_decision_across_meetings_merged(self):
        project_id = self.create_project()
        self.router.responses = [
            {
                "executive_summary": "Flow agreed.", "project_status": "on_track", "progress_summary": "Steady.",
                "completed_items": [], "in_progress_items": [],
                "risks": [], "blockers": [],
                "decisions": [{"title": "Adopt flow", "details": "official"}],
                "action_items": [],
            },
            {
                "risks": [], "blockers": [], "action_items": [],
                "decisions": [{"decision": "CREATE", "new_item": {"title": "Adopt flow", "details": "official"}, "reason": "new decision"}],
            },
            {
                "executive_summary": "Flow confirmed.", "project_status": "on_track", "progress_summary": "Steady.",
                "completed_items": [], "in_progress_items": [],
                "risks": [], "blockers": [],
                "decisions": [{"title": "Adopt Flow", "details": "repeated"}],
                "action_items": [],
            },
        ]

        for title, notes in (
            ("Weekly 1", "decision recorded"),
            ("Weekly 2", "decision confirmed"),
        ):
            response = self.client.post(
                f"/projects/{project_id}/meetings/new",
                data={"title": title, "meeting_notes": notes},
            )
            self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertEqual(Decision.query.count(), 1)

            decision = Decision.query.one()
            self.assertEqual(decision.canonical_title, "adopt flow")

            summaries = " | ".join(
                event.summary for event in HistoryEvent.query.all()
            )
            self.assertIn(
                "Merged duplicate decision: Adopt flow. "
                "Reason: deterministic pre-match: duplicate decision title",
                summaries,
            )


    def _seed_review_events(self, project_id):
        """
        Create needs_review events via a crafted invalid plan.

        Returns the (meeting id, risk event id, decision event id).
        """
        with self.app.app_context():
            project = db.session.get(Project, project_id)

            meeting = Meeting(
                project_id=project_id,
                title="Review fixture",
                original_text="notes",
                analysis_text="{}",
                analysis_json={},
                provider="openrouter",
                model="openrouter/free",
            )
            db.session.add(meeting)
            db.session.flush()

            plan = {
                "risks": [
                    {
                        "decision": "MERGE",
                        "existing_item_id": 999,
                        "new_item": {"title": "Vendor risk", "status": "open"},
                        "reason": "bogus id",
                    },
                ],
                "blockers": [],
                "action_items": [],
                "decisions": [
                    {
                        "decision": "UPDATE",
                        "existing_item_id": 1,
                        "new_item": {"title": "Pick flow"},
                        "reason": "not supported",
                    },
                ],
            }

            apply_consolidation_plan(project, meeting, plan)
            db.session.commit()

            events = HistoryEvent.query.filter_by(
                project_id=project_id,
                event_type="needs_review",
            ).order_by(HistoryEvent.id).all()

            risk_event = next(e for e in events if e.entity_type == "risk")
            decision_event = next(
                e for e in events if e.entity_type == "decision"
            )

            return meeting.id, risk_event.id, decision_event.id

    def test_review_queue_lists_and_resolves_via_create(self):
        project_id = self.create_project()
        meeting_id, risk_event_id, decision_event_id = (
            self._seed_review_events(project_id)
        )

        # The overview badge shows the unresolved count.
        overview = self.client.get(f"/projects/{project_id}")
        self.assertIn(b"Review (2)", overview.data)

        # The queue lists both findings.
        queue = self.client.get(f"/projects/{project_id}/review")
        self.assertEqual(queue.status_code, 200)
        self.assertIn(b"Vendor risk", queue.data)
        self.assertIn(b"Pick flow", queue.data)

        # Resolve the risk finding by creating the item.
        response = self.client.post(
            f"/projects/{project_id}/review/{risk_event_id}/resolve",
            data={"action": "create"},
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            risk = Risk.query.one()
            self.assertEqual(risk.title, "Vendor risk")
            self.assertEqual(risk.canonical_title, "vendor risk")
            self.assertEqual(risk.created_in_meeting_id, meeting_id)

            resolution = ReviewResolution.query.one()
            self.assertEqual(resolution.action, "applied_create")
            self.assertEqual(resolution.target_item_id, risk.id)

            summaries = " | ".join(
                event.summary
                for event in HistoryEvent.query.order_by(HistoryEvent.id).all()
            )
            self.assertIn(
                "Created risk: Vendor risk (from review queue)", summaries
            )

        # One finding left in the queue.
        queue = self.client.get(f"/projects/{project_id}/review")
        self.assertIn(b"Pick flow", queue.data)
        self.assertNotIn(b"Vendor risk", queue.data)

    def test_review_queue_resolves_via_link(self):
        project_id = self.create_project()
        meeting_id, risk_event_id, decision_event_id = (
            self._seed_review_events(project_id)
        )

        with self.app.app_context():
            decision = Decision(
                project_id=project_id,
                title="Pick flow",
                canonical_title="pick flow",
                details="",
                created_in_meeting_id=meeting_id,
            )
            db.session.add(decision)
            db.session.commit()
            decision_id = decision.id

        response = self.client.post(
            f"/projects/{project_id}/review/{decision_event_id}/resolve",
            data={"action": "link", "target_item_id": str(decision_id)},
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            # No duplicate decision was created.
            self.assertEqual(Decision.query.count(), 1)

            resolution = ReviewResolution.query.one()
            self.assertEqual(resolution.action, "applied_merge")
            self.assertEqual(resolution.target_item_id, decision_id)

            summaries = " | ".join(
                event.summary
                for event in HistoryEvent.query.order_by(HistoryEvent.id).all()
            )
            self.assertIn(
                "Merged duplicate decision: Pick flow -> Pick flow "
                "(from review queue)",
                summaries,
            )

        # The risk finding remains; the badge shows one.
        overview = self.client.get(f"/projects/{project_id}")
        self.assertIn(b"Review (1)", overview.data)

    def test_review_queue_dismiss_and_reopen_guard(self):
        project_id = self.create_project()
        meeting_id, risk_event_id, decision_event_id = (
            self._seed_review_events(project_id)
        )

        response = self.client.post(
            f"/projects/{project_id}/review/{risk_event_id}/resolve",
            data={"action": "dismiss", "note": "not relevant"},
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            resolution = ReviewResolution.query.one()
            self.assertEqual(resolution.action, "acknowledged")
            self.assertEqual(resolution.note, "not relevant")

            # Nothing was created for the dismissed finding.
            self.assertEqual(Risk.query.count(), 0)

        # Double resolution is rejected with a flash, not an error.
        response = self.client.post(
            f"/projects/{project_id}/review/{risk_event_id}/resolve",
            data={"action": "dismiss"},
            follow_redirects=True,
        )
        self.assertIn(b"already resolved", response.data)

    def test_review_create_refuses_duplicate_title(self):
        project_id = self.create_project()
        meeting_id, risk_event_id, decision_event_id = (
            self._seed_review_events(project_id)
        )

        with self.app.app_context():
            existing = Risk(
                project_id=project_id,
                title="Vendor risk",
                canonical_title="vendor risk",
                created_in_meeting_id=meeting_id,
                updated_in_meeting_id=meeting_id,
            )
            db.session.add(existing)
            db.session.commit()

        response = self.client.post(
            f"/projects/{project_id}/review/{risk_event_id}/resolve",
            data={"action": "create"},
            follow_redirects=True,
        )

        self.assertIn(b"already exists", response.data)

        with self.app.app_context():
            # Still one risk, no resolution recorded, event still open.
            self.assertEqual(Risk.query.count(), 1)
            self.assertEqual(ReviewResolution.query.count(), 0)

        overview = self.client.get(f"/projects/{project_id}")
        self.assertIn(b"Review (2)", overview.data)


    def test_semantic_paraphrase_reaches_llm_as_candidate(self):
        project_id = self.create_project()

        # Meeting 1 creates the risk "QA capacity". Meeting 2 mentions
        # the same risk with a paraphrase that shares no word with the
        # stored title: only the semantic layer can make it a
        # candidate for the LLM.
        self.router.responses = [
            {
                "executive_summary": "QA is constrained.",
                "project_status": "at_risk",
                "progress_summary": "Testing is delayed.",
                "completed_items": [],
                "in_progress_items": [],
                "risks": [{
                    "title": "QA capacity",
                    "description": "One tester",
                    "impact": "high",
                    "mitigation": "Borrow support",
                    "status": "open",
                }],
                "blockers": [], "decisions": [], "action_items": [],
            },
            {
                "risks": [{
                    "decision": "CREATE",
                    "new_item": {
                        "title": "QA capacity",
                        "description": "One tester",
                        "impact": "high",
                        "mitigation": "Borrow support",
                        "status": "open",
                    },
                    "reason": "no similar open risk",
                }],
                "blockers": [], "action_items": [], "decisions": [],
            },
            {
                "executive_summary": "Still short on testers.",
                "project_status": "at_risk",
                "progress_summary": "Hiring is slow.",
                "completed_items": [],
                "in_progress_items": [],
                "risks": [{
                    "title": "Insufficient tester headcount",
                    "status": "open",
                }],
                "blockers": [], "decisions": [], "action_items": [],
            },
            {
                "risks": [{
                    "decision": "MERGE",
                    "existing_item_id": 1,
                    "new_item": {"title": "Insufficient tester headcount"},
                    "reason": "same risk, reworded",
                }],
                "blockers": [], "action_items": [], "decisions": [],
            },
        ]

        for title, notes in [
            ("Weekly 1", "QA capacity discussed"),
            ("Weekly 2", "Not enough testers on the team"),
        ]:
            response = self.client.post(
                f"/projects/{project_id}/meetings/new",
                data={"title": title, "meeting_notes": notes},
            )
            self.assertEqual(response.status_code, 302)

        self.assertEqual(self.router.responses, [])

        with self.app.app_context():
            # The paraphrase merged into the existing risk instead of
            # duplicating it.
            self.assertEqual(Risk.query.count(), 1)
            risk = Risk.query.one()
            self.assertEqual(risk.title, "QA capacity")

            # The lazy backfill persisted the item's embedding.
            self.assertEqual(risk.title_embedding, [1.0, 0.0])

        # The consolidation prompt for meeting 2 carried the risk as a
        # semantic candidate of the zero-overlap paraphrase.
        consolidation_prompt = self.router.prompts[3]
        self.assertIn("candidate_ids", consolidation_prompt)
        self.assertRegex(consolidation_prompt, r'"candidate_ids": \[\s*1')

    def test_embedding_outage_falls_back_silently(self):
        project_id = self.create_project()

        def broken_embed(provider, model, texts):
            raise RuntimeError("embeddings endpoint down")

        self.router.embed_texts = broken_embed

        self.router.responses = [
            {
                "executive_summary": "QA is constrained.",
                "project_status": "at_risk",
                "progress_summary": "Testing is delayed.",
                "completed_items": [],
                "in_progress_items": [],
                "risks": [{
                    "title": "QA capacity",
                    "description": "One tester",
                    "impact": "high",
                    "mitigation": "Borrow support",
                    "status": "open",
                }],
                "blockers": [], "decisions": [], "action_items": [],
            },
            {
                "risks": [{
                    "decision": "CREATE",
                    "new_item": {"title": "QA capacity", "status": "open"},
                    "reason": "no similar open risk",
                }],
                "blockers": [], "action_items": [], "decisions": [],
            },
        ]

        response = self.client.post(
            f"/projects/{project_id}/meetings/new",
            data={"title": "Weekly 1", "meeting_notes": "QA risk discussed"},
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            risk = Risk.query.one()
            self.assertEqual(risk.title, "QA capacity")
            self.assertIsNone(risk.title_embedding)

    def _seed_meeting(self, project_id, analysis_json):
        """Insert a meeting row directly with a known analysis payload."""
        with self.app.app_context():
            meeting = Meeting(
                project_id=project_id,
                title="Analysis fixture",
                original_text="notes",
                analysis_text="{}",
                analysis_json=analysis_json,
                provider="openrouter",
                model="openrouter/free",
            )
            db.session.add(meeting)
            db.session.commit()
            return meeting.id

    def test_meeting_page_renders_parsed_analysis(self):
        project_id = self.create_project()
        analysis = {
            "executive_summary": "Delivery slowed by vendor delays.",
            "project_status": "at_risk",
            "progress_summary": "Two of five milestones done.",
            "completed_items": ["Spec sign-off"],
            "in_progress_items": ["Vendor onboarding"],
            "risks": [{
                "title": "Vendor API quota exhaustion",
                "description": "Rate limit hit.",
                "impact": "high",
                "mitigation": "Request increase",
                "status": "open",
            }],
            "blockers": [],
            "action_items": [{
                "title": "Chase vendor",
                "details": "Email support",
                "owner": "Ava",
                "due_date": "2026-08-15",
                "status": "open",
            }],
            "decisions": [{
                "title": "Postpone marketing campaign",
                "details": "Until beta",
            }],
        }
        meeting_id = self._seed_meeting(project_id, analysis)

        page = self.client.get(f"/meetings/{meeting_id}")

        self.assertEqual(page.status_code, 200)
        self.assertIn(b"AI analysis", page.data)
        self.assertIn(b"At Risk", page.data)
        self.assertIn(b"Delivery slowed by vendor delays.", page.data)
        self.assertIn(b"Two of five milestones done.", page.data)
        self.assertIn(b"Spec sign-off", page.data)
        self.assertIn(b"Vendor onboarding", page.data)
        self.assertIn(b"Vendor API quota exhaustion", page.data)
        self.assertIn(b"Impact: high", page.data)
        self.assertIn(b"Chase vendor", page.data)
        self.assertIn(b"Due: 2026-08-15", page.data)
        self.assertIn(b"Postpone marketing campaign", page.data)

    def test_meeting_page_without_analysis(self):
        project_id = self.create_project()
        meeting_id = self._seed_meeting(project_id, {})

        page = self.client.get(f"/meetings/{meeting_id}")

        self.assertEqual(page.status_code, 200)
        self.assertIn(b"No structured analysis stored", page.data)


if __name__ == "__main__":
    unittest.main()
