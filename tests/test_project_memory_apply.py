"""Unit tests for project_memory's consolidation and review branches.

These target the apply-side layer that turns an AI consolidation plan
(or a review-queue resolution) into rows and history events. The audit
run flagged this module as the weakest-covered surface in the codebase,
and the uncovered ground was almost entirely the MERGE/UPDATE/CONFLICT
branches, the decisions loop, and the review-queue path.

Every test runs against the same in-memory sqlite database and app
factory as the API suite; only the router is a stub, because nothing
here may reach an LLM provider.
"""

import unittest
import uuid
from datetime import UTC, date, datetime

import project_memory
from api import create_app
from database import db
from matching import normalize_title
from models import (
    ActionItem,
    Blocker,
    Decision,
    HistoryEvent,
    Meeting,
    Project,
    Risk,
)


class StubRouter:
    """Stands in for ModelRouter; no test here may reach a provider."""

    def generate(self, provider, model, prompt, system_prompt=None):
        raise AssertionError("the router must not be reached from these tests")

    def get_models(self, provider):
        return []

    def embed_texts(self, provider, model, texts):
        raise AssertionError("the router must not be reached from these tests")


class ProjectMemoryTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(StubRouter(), "sqlite://")
        db.create_all()
        self.project, self.meeting = self._make_project_and_meeting()

    def tearDown(self):
        db.session.remove()
        db.drop_all()

    # ------------------------------------------------------------------
    # Fixtures

    def _make_project_and_meeting(self):
        project = Project(name=f"proj-{uuid.uuid4().hex[:8]}")
        db.session.add(project)
        db.session.flush()

        meeting = Meeting(
            project_id=project.id,
            title="Weekly sync",
            source_filename="notes.txt",
            original_text="transcript text",
            analysis_text="{}",
            analysis_json={},
            provider="nvidia",
            model="test-model",
        )
        db.session.add(meeting)
        db.session.flush()
        return project, meeting

    def _add_risk(self, title, project=None, **overrides):
        record = Risk(
            project_id=(project or self.project).id,
            title=title,
            canonical_title=normalize_title(title),
            created_in_meeting_id=self.meeting.id,
            updated_in_meeting_id=self.meeting.id,
            **overrides,
        )
        db.session.add(record)
        db.session.flush()
        return record

    def _add_action(self, title, **overrides):
        record = ActionItem(
            project_id=self.project.id,
            title=title,
            canonical_title=normalize_title(title),
            created_in_meeting_id=self.meeting.id,
            updated_in_meeting_id=self.meeting.id,
            **overrides,
        )
        db.session.add(record)
        db.session.flush()
        return record

    def _add_decision(self, title, **overrides):
        record = Decision(
            project_id=self.project.id,
            title=title,
            canonical_title=normalize_title(title),
            created_in_meeting_id=self.meeting.id,
            **overrides,
        )
        db.session.add(record)
        db.session.flush()
        return record

    def _events(self, event_type=None):
        query = db.session.query(HistoryEvent).filter_by(
            project_id=self.project.id
        )
        if event_type is not None:
            query = query.filter_by(event_type=event_type)
        return query.order_by(HistoryEvent.id).all()

    def _plan(self, **sections):
        return {
            "action_items": [],
            "risks": [],
            "blockers": [],
            "decisions": [],
            **sections,
        }

    # ------------------------------------------------------------------
    # _plan_existing_item, via the MERGE branch's guardrails

    def test_merge_without_an_existing_id_is_routed_to_review(self):
        # A MERGE without existing_item_id cannot be applied; the entry
        # is preserved as needs_review instead of being dropped.
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                action_items=[
                    {
                        "decision": "MERGE",
                        "new_item": {"title": "Launch blocker"},
                    }
                ]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("missing", events[0].summary)

    def test_merge_with_a_non_numeric_id_is_routed_to_review(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                action_items=[
                    {
                        "decision": "MERGE",
                        "existing_item_id": "abc",
                        "new_item": {"title": "Launch blocker"},
                    }
                ]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("invalid", events[0].summary)

    def test_merge_with_an_unknown_id_is_routed_to_review(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                action_items=[
                    {
                        "decision": "MERGE",
                        "existing_item_id": 999,
                        "new_item": {"title": "Launch blocker"},
                    }
                ]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("not_found", events[0].summary)

    def test_merge_with_another_project_s_item_is_routed_to_review(self):
        other_project = Project(name=f"proj-{uuid.uuid4().hex[:8]}")
        db.session.add(other_project)
        db.session.flush()
        foreign = self._add_risk("Shared title", project=other_project)

        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                risks=[
                    {
                        "decision": "MERGE",
                        "existing_item_id": foreign.id,
                        "new_item": {"title": "Shared title"},
                    }
                ]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("foreign", events[0].summary)

    def test_merge_into_the_existing_item_records_a_merged_event(self):
        risk = self._add_risk("Shared title")

        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                risks=[
                    {
                        "decision": "MERGE",
                        "existing_item_id": risk.id,
                        "new_item": {"title": "Shared title again"},
                        "reason": "same risk",
                    }
                ]
            ),
        )

        events = self._events("merged")
        self.assertEqual(len(events), 1)
        self.assertEqual(db.session.query(Risk).count(), 1)

    # ------------------------------------------------------------------
    # _apply_consolidation_item's guardrails and dispatch

    def test_a_plan_item_without_a_title_is_routed_to_review(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                blockers=[{"decision": "CREATE", "new_item": {"description": "d"}}]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("missing_title", events[0].summary)

    def test_an_unknown_decision_type_is_routed_to_review(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                blockers=[
                    {
                        "decision": "archive",
                        "new_item": {"title": "Launch blocker"},
                    }
                ]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("unknown_decision", events[0].summary)

    def test_an_unsupported_model_class_is_ignored_without_an_event(self):
        # Decision is deliberately absent from _PLAN_ITEM_SPECS: the
        # decisions loop handles it inline, so the generic dispatcher
        # must not fabricate a plan item for it.
        result = project_memory._apply_consolidation_item(
            self.project,
            self.meeting,
            {"decision": "CREATE", "new_item": {"title": "A decision"}},
            "CREATE",
            Decision,
            {},
        )

        self.assertIsNone(result)
        self.assertEqual(self._events(), [])
        self.assertEqual(db.session.query(Decision).count(), 0)

    # ------------------------------------------------------------------
    # _apply_create

    def test_a_duplicate_create_within_one_plan_merges(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                action_items=[
                    {
                        "decision": "CREATE",
                        "new_item": {"title": "Write the report"},
                    },
                    {
                        "decision": "CREATE",
                        "new_item": {"title": "Write the report"},
                    },
                ]
            ),
        )

        self.assertEqual(db.session.query(ActionItem).count(), 1)
        merged = self._events("merged")
        self.assertEqual(len(merged), 1)
        self.assertIn("duplicate CREATE", merged[0].summary)

    def test_a_created_item_whose_status_is_done_is_stamped(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                action_items=[
                    {
                        "decision": "CREATE",
                        "new_item": {
                            "title": "Write the report",
                            "status": "completed",
                        },
                    }
                ]
            ),
        )

        action = db.session.query(ActionItem).one()
        self.assertEqual(action.status, "completed")
        self.assertIsNotNone(action.completed_at)
        self.assertEqual(
            action.completed_in_meeting_id, self.meeting.id
        )

    def test_a_created_item_with_an_unparseable_due_date_stores_none(self):
        # A due date that will not parse falls back to None on create:
        # the alternative is a 500 from the database driver.
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                action_items=[
                    {
                        "decision": "CREATE",
                        "new_item": {
                            "title": "Write the report",
                            "due_date": "next friday",
                        },
                    }
                ]
            ),
        )

        action = db.session.query(ActionItem).one()
        self.assertIsNone(action.due_date)

    # ------------------------------------------------------------------
    # _apply_update and _stamp_done

    def test_update_without_an_existing_id_is_routed_to_review(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                risks=[{"decision": "UPDATE", "new_item": {"title": "A risk"}}]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("missing", events[0].summary)

    def test_update_with_an_unknown_id_is_routed_to_review(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                risks=[
                    {
                        "decision": "UPDATE",
                        "existing_item_id": 999,
                        "new_item": {"title": "A risk"},
                    }
                ]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("not_found", events[0].summary)

    def test_update_writes_the_plan_fields_and_keeps_unmentioned_ones(self):
        risk = self._add_risk(
            "Budget risk", description="tight", impact="high"
        )

        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                risks=[
                    {
                        "decision": "UPDATE",
                        "existing_item_id": risk.id,
                        "new_item": {"title": "Budget risk",
                                     "mitigation": "hire contractor"},
                        "reason": "new information",
                    }
                ]
            ),
        )

        # The apply helpers leave the session dirty. Commit is what the
        # request-teardown path does, and it also makes the assertions
        # below read database truth rather than pending session state.
        db.session.commit()
        # The mitigation is written; the fields the plan never mentioned
        # keep their stored values instead of being erased to "".
        self.assertEqual(risk.mitigation, "hire contractor")
        self.assertEqual(risk.description, "tight")
        self.assertEqual(risk.impact, "high")
        updated = self._events("updated")
        self.assertEqual(len(updated), 1)
        self.assertIn("new information", updated[0].summary)

    def test_reopening_an_item_clears_its_stale_resolution_stamp(self):
        # A status that drifts back to open must not leave resolved_at
        # claiming the item is still resolved.
        risk = self._add_risk(
            "Budget risk",
            status="resolved",
            resolved_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        )
        self.assertIsNotNone(risk.resolved_at)

        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                risks=[
                    {
                        "decision": "UPDATE",
                        "existing_item_id": risk.id,
                        "new_item": {"title": "Budget risk", "status": "open"},
                    }
                ]
            ),
        )

        db.session.commit()
        self.assertIsNone(risk.resolved_at)
        self.assertIsNone(risk.resolved_in_meeting_id)

    def test_update_with_an_unparseable_due_date_keeps_the_stored_one(self):
        action = self._add_action(
            "Write the report", due_date=date(2026, 1, 15)
        )

        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                action_items=[
                    {
                        "decision": "UPDATE",
                        "existing_item_id": action.id,
                        "new_item": {
                            "title": "Write the report",
                            "due_date": "soon",
                        },
                    }
                ]
            ),
        )

        db.session.commit()
        self.assertEqual(action.due_date, date(2026, 1, 15))

    # ------------------------------------------------------------------
    # _apply_conflict

    def test_conflict_without_an_existing_id_is_routed_to_review(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                risks=[{"decision": "CONFLICT", "new_item": {"title": "A risk"}}]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("missing", events[0].summary)

    def test_conflict_with_an_unknown_id_is_routed_to_review(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                risks=[
                    {
                        "decision": "CONFLICT",
                        "existing_item_id": 999,
                        "new_item": {"title": "A risk"},
                    }
                ]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("not_found", events[0].summary)

    def test_conflict_preserves_the_existing_item_and_records_both_sides(self):
        risk = self._add_risk("Budget risk", status="open")

        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                risks=[
                    {
                        "decision": "CONFLICT",
                        "existing_item_id": risk.id,
                        "new_item": {"title": "Budget risk", "status": "resolved"},
                        "reason": "disagree on the resolution",
                    }
                ]
            ),
        )

        db.session.commit()
        # The existing item is preserved untouched.
        self.assertEqual(risk.status, "open")
        conflicts = self._events("conflict")
        self.assertEqual(len(conflicts), 1)
        self.assertIn("Existing preserved", conflicts[0].summary)

    # ------------------------------------------------------------------
    # apply_consolidation_plan's decisions loop

    def test_decisions_merge_records_a_merged_event(self):
        decision = self._add_decision("Go live in March")

        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                decisions=[
                    {
                        "decision": "MERGE",
                        "existing_item_id": decision.id,
                        "new_item": {"title": "Go live in March"},
                        "reason": "same decision",
                    }
                ]
            ),
        )

        merged = self._events("merged")
        self.assertEqual(len(merged), 1)
        self.assertEqual(db.session.query(Decision).count(), 1)

    def test_decisions_merge_without_an_existing_id_is_routed_to_review(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(decisions=[{"decision": "MERGE", "new_item": {}}]),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("missing", events[0].summary)

    def test_decisions_are_append_only_so_other_decisions_are_reviewed(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                decisions=[
                    {
                        "decision": "update",
                        "existing_item_id": 999,
                        "new_item": {"title": "A decision"},
                    }
                ]
            ),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("unsupported_decision", events[0].summary)
        self.assertEqual(db.session.query(Decision).count(), 0)

    def test_a_decision_create_without_a_title_is_routed_to_review(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(decisions=[{"decision": "CREATE", "new_item": {}}]),
        )

        events = self._events("needs_review")
        self.assertEqual(len(events), 1)
        self.assertIn("missing_title", events[0].summary)

    def test_a_duplicate_decision_create_within_one_plan_merges(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                decisions=[
                    {"decision": "CREATE", "new_item": {"title": "A decision"}},
                    {"decision": "CREATE", "new_item": {"title": "A decision"}},
                ]
            ),
        )

        self.assertEqual(db.session.query(Decision).count(), 1)
        merged = self._events("merged")
        self.assertEqual(len(merged), 1)
        self.assertIn("duplicate CREATE", merged[0].summary)

    def test_a_decision_create_records_the_row_and_the_event(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                decisions=[
                    {
                        "decision": "create",
                        "new_item": {
                            "title": "Go live in March",
                            "details": "weather permitting",
                        },
                    }
                ]
            ),
        )

        decision = db.session.query(Decision).one()
        self.assertEqual(decision.details, "weather permitting")
        created = self._events("created")
        self.assertEqual(len(created), 1)
        self.assertIn("Go live in March", created[0].summary)

    def test_blockers_are_applied_through_the_plan_loop(self):
        project_memory.apply_consolidation_plan(
            self.project,
            self.meeting,
            self._plan(
                blockers=[
                    {
                        "decision": "CREATE",
                        "new_item": {"title": "CI is red"},
                    }
                ]
            ),
        )

        self.assertEqual(db.session.query(Blocker).count(), 1)

    # ------------------------------------------------------------------
    # review_model_class

    def test_a_non_string_entity_type_has_no_model(self):
        self.assertIsNone(project_memory.review_model_class(None))
        self.assertIsNone(project_memory.review_model_class(42))

    # ------------------------------------------------------------------
    # apply_review_create

    def test_an_unknown_entity_type_raises(self):
        with self.assertRaises(ValueError) as ctx:
            project_memory.apply_review_create(
                self.project, self.meeting, "banana", {"new_item": {}}
            )

        self.assertIn("banana", str(ctx.exception))

    def test_a_plan_item_without_a_title_raises(self):
        with self.assertRaises(ValueError) as ctx:
            project_memory.apply_review_create(
                self.project, self.meeting, "risk", {"new_item": {}}
            )

        self.assertIn("no title", str(ctx.exception))

    def test_creating_an_existing_title_raises(self):
        self._add_risk("Known risk")

        with self.assertRaises(ValueError) as ctx:
            project_memory.apply_review_create(
                self.project,
                self.meeting,
                "risk",
                {"new_item": {"title": "Known risk"}},
            )

        self.assertIn("already exists", str(ctx.exception))
        self.assertEqual(db.session.query(Risk).count(), 1)

    def test_a_decision_is_created_from_the_review_queue(self):
        record = project_memory.apply_review_create(
            self.project,
            self.meeting,
            "decision",
            {"new_item": {"title": "Go live in March", "details": "soon"}},
        )

        self.assertIsInstance(record, Decision)
        self.assertEqual(record.details, "soon")
        created = self._events("created")
        self.assertEqual(len(created), 1)

    def test_an_action_item_with_an_unparseable_due_date_stores_none(self):
        record = project_memory.apply_review_create(
            self.project,
            self.meeting,
            "action_item",
            {"new_item": {"title": "Do it", "due_date": "whenever"}},
        )

        self.assertIsNone(record.due_date)

    def test_a_completed_action_item_is_stamped_when_created(self):
        record = project_memory.apply_review_create(
            self.project,
            self.meeting,
            "action_item",
            {"new_item": {"title": "Do it", "status": "completed"}},
        )

        self.assertEqual(record.status, "completed")
        self.assertIsNotNone(record.completed_at)
        self.assertEqual(record.completed_in_meeting_id, self.meeting.id)

    def test_a_resolved_risk_is_stamped_when_created(self):
        record = project_memory.apply_review_create(
            self.project,
            self.meeting,
            "risk",
            {"new_item": {"title": "Risk it", "status": "resolved"}},
        )

        self.assertEqual(record.status, "resolved")
        self.assertIsNotNone(record.resolved_at)

    def test_an_unrecognized_status_falls_back_to_open_with_a_warning(self):
        # An unknown status is invisible to the reports and the
        # resolution-rate metric; it must become the fallback visibly.
        with self.assertLogs("ai-delivery-assistant.memory", level="WARNING"):
            record = project_memory.apply_review_create(
                self.project,
                self.meeting,
                "risk",
                {"new_item": {"title": "Risk it", "status": "bogus-status"}},
            )

        self.assertEqual(record.status, "open")

    def test_apply_review_merge_records_the_merge_and_returns_the_target(self):
        risk = self._add_risk("Known risk")

        result = project_memory.apply_review_merge(
            self.project,
            self.meeting,
            "risk",
            {"new_item": {"title": "Known risk"}, "reason": "same finding"},
            risk,
        )

        self.assertIs(result, risk)
        merged = self._events("merged")
        self.assertEqual(len(merged), 1)
        self.assertIn("from review queue", merged[0].summary)

    # ------------------------------------------------------------------
    # apply_meeting_analysis's decisions loop

    def _analysis(self, **sections):
        return {"project_status": "on_track", "progress_summary": "p", **sections}

    def test_a_null_decisions_section_behaves_like_an_absent_one(self):
        # "decisions": null used to reach iteration as None and raise
        # TypeError, which the API layer's except tuple does not catch.
        project_memory.apply_meeting_analysis(
            self.project,
            self.meeting,
            self._analysis(decisions=None),
        )

        self.assertEqual(db.session.query(Decision).count(), 0)
        self.assertEqual(self._events("created"), [])

    def test_a_decision_is_recorded_from_the_analysis(self):
        project_memory.apply_meeting_analysis(
            self.project,
            self.meeting,
            self._analysis(
                decisions=[{"title": "Go live in March", "details": "d"}]
            ),
        )

        decision = db.session.query(Decision).one()
        self.assertEqual(decision.details, "d")
        created = self._events("created")
        self.assertEqual(len(created), 1)

    def test_a_duplicate_decision_from_the_analysis_merges(self):
        self._add_decision("Go live in March")

        project_memory.apply_meeting_analysis(
            self.project,
            self.meeting,
            self._analysis(
                decisions=[{"title": "Go live in March", "details": "d"}]
            ),
        )

        self.assertEqual(db.session.query(Decision).count(), 1)
        merged = self._events("merged")
        self.assertEqual(len(merged), 1)

    def test_a_finding_without_a_title_is_skipped(self):
        project_memory.apply_meeting_analysis(
            self.project,
            self.meeting,
            self._analysis(risks=[{"impact": "high"}]),
        )

        self.assertEqual(db.session.query(Risk).count(), 0)

    def test_a_new_finding_marked_done_is_stamped(self):
        project_memory.apply_meeting_analysis(
            self.project,
            self.meeting,
            self._analysis(risks=[{"title": "Budget risk",
                                   "status": "resolved"}]),
        )

        risk = db.session.query(Risk).one()
        self.assertEqual(risk.status, "resolved")
        self.assertIsNotNone(risk.resolved_at)
        self.assertEqual(risk.resolved_in_meeting_id, self.meeting.id)

    def test_updating_a_finding_without_a_done_mark_uses_the_updated_action(self):
        self._add_risk("Budget risk")

        project_memory.apply_meeting_analysis(
            self.project,
            self.meeting,
            self._analysis(
                risks=[{"title": "Budget risk", "mitigation": "contractor"}]
            ),
        )

        # The analysis path also stamps a project_state "updated" event;
        # the event for this risk is the one labelled with its label.
        updated = [
            event
            for event in self._events("updated")
            if event.entity_type == "risk"
        ]
        self.assertEqual(len(updated), 1)
        self.assertIn("Updated risk: Budget risk", updated[0].summary)