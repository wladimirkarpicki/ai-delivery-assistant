"""Seed the dev database with demo delivery data for the dashboard.

Runs INSIDE the app container (where models/database and DATABASE_URL
are available), against the configured PostgreSQL database:

    PowerShell:
        Get-Content -Raw scripts\\seed_demo_data.py | docker compose exec -T app python -

    sh:
        docker compose exec -T app python - < scripts/seed_demo_data.py

Idempotency:
- The three "Demo \u00b7 " projects are owned by this script: any
  previous demo rows are deleted first, in dependency order
  (history_events -> risks/blockers/action_items/decisions ->
  project_states -> meetings -> projects), then recreated.
- The five named smoke-test projects keep their existing rows and
  meetings; only their ProjectState is upserted (created if missing,
  refreshed otherwise). Missing projects are created with a
  [demo-seed] marker in the description.
- Real projects (inventory-management-system, ai-delivery-assistant)
  and their data are never touched.

No create_app, no create_all: the schema already exists in the Docker
database; the script only writes rows through the same models the
application uses.
"""

from datetime import UTC, date, datetime, timedelta

from database import configure_database, db
from models import (
    ActionItem,
    Blocker,
    Decision,
    HistoryEvent,
    Meeting,
    Project,
    ProjectState,
    ReviewResolution,
    Risk,
    utcnow,
)

DEMO_PREFIX = "Demo \u00b7 "
PROVIDER = "demo"
MODEL = "seed"


def when(month, day, hour=10, minute=0):
    """A timezone-aware UTC datetime on the 2026 demo timeline."""
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


# ---------------------------------------------------------------------------
# The five smoke-test projects: only their ProjectState is upserted.

TEST_PROJECT_STATES = [
    {
        "name": "OpenRouter Smoke Test",
        "delivery_status": "delivered",
        "progress_summary": (
            "Smoke checks against the live Free Models Router passed end to end."
        ),
        "completed_items": [
            "Router reachable and model discovery verified",
            "Analysis JSON schema validated against live responses",
        ],
        "in_progress_items": [
            "Archive smoke-run artifacts for future reference",
        ],
    },
    {
        "name": "Pre-Match Smoke Test",
        "delivery_status": "delivered",
        "progress_summary": (
            "Deterministic pre-match smoke scenarios confirmed duplicate handling."
        ),
        "completed_items": [
            "Exact-title duplicate merged without an LLM call",
            "Status-change findings reopened resolved items correctly",
        ],
        "in_progress_items": [
            "Extend the smoke script to semantic candidates",
        ],
    },
    {
        "name": "Duplicate Scenarios Test",
        "delivery_status": "on_track",
        "progress_summary": (
            "Duplicate-handling scenarios behave as specified; edge cases "
            "are still being exercised."
        ),
        "completed_items": [
            "Identical notes rejected as a no-op with a warning",
            "Duplicate decisions merged into the append-only record",
        ],
        "in_progress_items": [
            "Exercise conflicting duplicate titles across runs",
            "Cover reopened items in duplicate scenarios",
        ],
    },
    {
        "name": "C4 Semantic Test",
        "delivery_status": "on_track",
        "progress_summary": (
            "Semantic candidate matching produces sensible shortlists for review."
        ),
        "completed_items": [
            "Embeddings ranked paraphrased titles by cosine similarity",
            "Lexical fallback verified with embeddings disabled",
        ],
        "in_progress_items": [
            "Collect more paraphrase pairs for the evaluation set",
        ],
    },
    {
        "name": "Test Project",
        "delivery_status": "at_risk",
        "progress_summary": (
            "Manual end-to-end walkthroughs are behind; findings still need "
            "consolidation."
        ),
        "completed_items": [
            "Project creation and meeting upload verified",
            "History trail renders before/after diffs",
        ],
        "in_progress_items": [
            "Review queue resolution flows",
            "Status report export checks",
        ],
    },
]


# ---------------------------------------------------------------------------
# The three demo projects, seeded from scratch on every run.
# Meeting indices are 0-based positions in the project's meeting list.

DEMO_PROJECTS = [
    {
        "name": DEMO_PREFIX + "Customer Portal Redesign",
        "description": (
            "Redesign of the customer-facing portal: new information "
            "architecture, self-service flows, and a refreshed interface on "
            "the existing backend."
        ),
        "state": {
            "delivery_status": "on_track",
            "progress_summary": (
                "Design system rollout on track: the checkout flow is in "
                "usability testing and launch content is in progress."
            ),
            "completed_items": [
                "New information architecture signed off",
                "Account overview redesign shipped behind a flag",
                "Usability testing on the checkout prototype completed",
            ],
            "in_progress_items": [
                "Checkout flow polish",
                "Self-service help center articles",
            ],
        },
        "meetings": [
            ("Kickoff - Portal Redesign", when(5, 6)),
            ("Sprint 12 Planning", when(6, 3)),
            ("Design Review - Checkout Flow", when(7, 1)),
            ("Weekly Delivery Check-in", when(8, 5)),
            ("Sprint 14 Planning", when(9, 2)),
            ("Release Readiness Review", when(10, 7)),
        ],
        "risks": [
            {
                "title": "Legacy CSS conflicts with the new design system",
                "impact": "medium",
                "description": "Old page-level styles override design-system tokens.",
                "mitigation": "Isolate legacy screens behind scoped overrides.",
                "status": "open",
                "created_in": 1,
                "updated_in": 4,
            },
            {
                "title": "Search relevance drops after content migration",
                "impact": "high",
                "description": "Early samples show worse results for top queries.",
                "mitigation": "Tune the ranking model before cutover.",
                "status": "open",
                "created_in": 2,
                "updated_in": 5,
            },
            {
                "title": "Support team unprepared for the new self-service flows",
                "impact": "low",
                "description": "Training has not started yet.",
                "mitigation": "Schedule training before public rollout.",
                "status": "open",
                "created_in": 4,
                "updated_in": 4,
            },
            {
                "title": "Accessibility audit finds contrast issues in mockups",
                "impact": "low",
                "description": "Several grey-on-grey combinations failed AA checks.",
                "mitigation": "Adjust the palette and re-run the audit.",
                "status": "resolved",
                "created_in": 1,
                "updated_in": 3,
                "resolved_in": 3,
            },
            {
                "title": "Checkout redesign slips behind the API contract",
                "impact": "high",
                "description": "The API team changed the payment endpoints mid-sprint.",
                "mitigation": "Weekly contract sync until the flow ships.",
                "status": "resolved",
                "created_in": 2,
                "updated_in": 5,
                "resolved_in": 5,
            },
        ],
        "blockers": [
            {
                "title": "Sign-off on the new information architecture missing",
                "description": "Waiting on the product owner's approval.",
                "status": "open",
                "created_in": 1,
                "updated_in": 5,
            },
            {
                "title": "Design tokens blocked by brand guidelines update",
                "description": "Brand team is finalizing the updated palette.",
                "status": "resolved",
                "created_in": 1,
                "updated_in": 2,
                "resolved_in": 2,
            },
        ],
        "actions": [
            {
                "title": "Wireframe the redesigned account overview",
                "owner": "Anna",
                "details": "Cover profile, billing, and notifications screens.",
                "status": "completed",
                "created_in": 0,
                "updated_in": 2,
                "completed_in": 2,
                "due_date": date(2026, 6, 15),
            },
            {
                "title": "Run usability testing on the checkout prototype",
                "owner": "Maria",
                "details": "Five moderated sessions with existing customers.",
                "status": "completed",
                "created_in": 2,
                "updated_in": 4,
                "completed_in": 4,
                "due_date": date(2026, 8, 20),
            },
            {
                "title": "Draft self-service help center articles",
                "owner": "Elena",
                "details": "Start with account and checkout topics.",
                "status": "completed",
                "created_in": 3,
                "updated_in": 5,
                "completed_in": 5,
                "due_date": date(2026, 10, 1),
            },
            {
                "title": "Instrument funnel analytics for the new flows",
                "owner": "Max",
                "details": "Track drop-off per checkout step.",
                "status": "open",
                "created_in": 4,
                "updated_in": 4,
                "due_date": date(2026, 10, 30),
            },
            {
                "title": "Prepare the support team training deck",
                "owner": "Team",
                "details": "Include the new self-service scenarios.",
                "status": "open",
                "created_in": 4,
                "updated_in": 4,
            },
            {
                "title": "Set up feature flags for the phased rollout",
                "owner": "Dmitri",
                "details": "Flags for account overview and checkout.",
                "status": "open",
                "created_in": 5,
                "updated_in": 5,
                "due_date": date(2026, 11, 5),
            },
        ],
        "decisions": [
            {
                "title": "Adopt the existing design system for all portal screens",
                "details": "Reuse the shared design system instead of bespoke components.",
                "created_in": 0,
            },
            {
                "title": "Ship checkout in two phases behind a feature flag",
                "details": "Payments first, then the confirmation flow.",
                "created_in": 2,
            },
            {
                "title": "Keep the legacy search index until relevance parity is proven",
                "details": "Re-evaluate after the ranking tuning round.",
                "created_in": 4,
            },
        ],
    },
    {
        "name": DEMO_PREFIX + "Data Platform Migration",
        "description": (
            "Migration of legacy reporting to the cloud data platform: "
            "pipeline rewrites, historical backfill, and cutover of consumer "
            "dashboards."
        ),
        "state": {
            "delivery_status": "at_risk",
            "progress_summary": (
                "Pipelines are rewritten on schedule, but the cutover window is "
                "at risk: backfill runs long and consumer dashboards are not "
                "migrated yet."
            ),
            "completed_items": [
                "Legacy reports inventoried with owners",
                "Revenue pipeline rewritten on the new platform",
                "Rollback plan documented",
            ],
            "in_progress_items": [
                "Consumer dashboard migration",
                "Data quality monitors for migrated tables",
            ],
        },
        "meetings": [
            ("Migration Kickoff", when(5, 5)),
            ("Weekly Delivery Check-in", when(6, 2)),
            ("Architecture Review - Pipeline Rewrites", when(6, 30)),
            ("Sprint 8 Retrospective", when(7, 28)),
            ("Cutover Planning Workshop", when(8, 25)),
            ("Weekly Delivery Check-in", when(9, 22)),
            ("Stakeholder Status Review", when(10, 13)),
        ],
        "risks": [
            {
                "title": "Historical backfill takes longer than the cutover window",
                "impact": "high",
                "description": "Current throughput misses the planned window by days.",
                "mitigation": "Parallelize backfill partitions.",
                "status": "open",
                "created_in": 2,
                "updated_in": 6,
            },
            {
                "title": "Consumer dashboards break on schema renames",
                "impact": "high",
                "description": "Several dashboards reference old column names.",
                "mitigation": "Publish a rename list and agree with consumers.",
                "status": "open",
                "created_in": 3,
                "updated_in": 5,
            },
            {
                "title": "Legacy ETL jobs double-write during the transition",
                "impact": "medium",
                "description": "Both pipelines run until cutover completes.",
                "mitigation": "Freeze legacy changes and diff outputs weekly.",
                "status": "open",
                "created_in": 4,
                "updated_in": 5,
            },
            {
                "title": "Data quality checks not ready for the first cutover rehearsal",
                "impact": "medium",
                "description": "Monitors exist only for the revenue pipeline.",
                "mitigation": "Extend the monitor set before the rehearsal.",
                "status": "open",
                "created_in": 5,
                "updated_in": 6,
            },
            {
                "title": "Cloud costs exceed the migration budget",
                "impact": "low",
                "description": "Compute-heavy backfill pushed the monthly bill up.",
                "mitigation": "Reserved capacity and off-peak scheduling.",
                "status": "resolved",
                "created_in": 1,
                "updated_in": 4,
                "resolved_in": 4,
            },
            {
                "title": "Vendor connector lacks the needed CDC support",
                "impact": "low",
                "description": "The connector drops updates on schema changes.",
                "mitigation": "Switch to the managed streaming service.",
                "status": "resolved",
                "created_in": 2,
                "updated_in": 3,
                "resolved_in": 3,
            },
        ],
        "blockers": [
            {
                "title": "Security review of the new platform pending",
                "description": "Waiting for the security team's slot.",
                "status": "open",
                "created_in": 4,
                "updated_in": 6,
            },
            {
                "title": "Warehouse permissions model not approved",
                "description": "Row-level access rules are still in discussion.",
                "status": "open",
                "created_in": 5,
                "updated_in": 5,
            },
            {
                "title": "Backfill dataset stuck in export approval",
                "description": "Data governance sign-off took three weeks.",
                "status": "resolved",
                "created_in": 1,
                "updated_in": 3,
                "resolved_in": 3,
            },
        ],
        "actions": [
            {
                "title": "Inventory legacy reports and their owners",
                "owner": "Maria",
                "details": "Every scheduled report with its consumer list.",
                "status": "completed",
                "created_in": 0,
                "updated_in": 1,
                "completed_in": 1,
                "due_date": date(2026, 6, 10),
            },
            {
                "title": "Rewrite the revenue pipeline on the new platform",
                "owner": "Max",
                "details": "Keep parity checks against the legacy output.",
                "status": "completed",
                "created_in": 2,
                "updated_in": 5,
                "completed_in": 5,
                "due_date": date(2026, 9, 15),
            },
            {
                "title": "Document the cutover rollback plan",
                "owner": "Anna",
                "details": "Steps, owners, and the go/no-go criteria.",
                "status": "completed",
                "created_in": 4,
                "updated_in": 6,
                "completed_in": 6,
                "due_date": date(2026, 10, 10),
            },
            {
                "title": "Rehearse the production cutover on staging",
                "owner": "Dmitri",
                "details": "Full run with backfill and dashboard smoke tests.",
                "status": "open",
                "created_in": 5,
                "updated_in": 5,
                "due_date": date(2026, 11, 8),
            },
            {
                "title": "Migrate finance dashboards to the new warehouse",
                "owner": "Elena",
                "details": "Coordinate with the finance analysts.",
                "status": "open",
                "created_in": 5,
                "updated_in": 5,
            },
            {
                "title": "Set up data quality monitors for migrated tables",
                "owner": "Max",
                "details": "Row counts, freshness, and null-rate checks.",
                "status": "open",
                "created_in": 6,
                "updated_in": 6,
                "due_date": date(2026, 11, 15),
            },
            {
                "title": "Agree the schema rename list with consumers",
                "owner": "Team",
                "details": "One review session per consumer team.",
                "status": "open",
                "created_in": 6,
                "updated_in": 6,
            },
        ],
        "decisions": [
            {
                "title": "Migrate pipelines team by team, not big-bang",
                "details": "Revenue first, then finance, then marketing.",
                "created_in": 1,
            },
            {
                "title": "Keep the legacy warehouse read-only during transition",
                "details": "No new pipelines on the legacy stack.",
                "created_in": 2,
            },
            {
                "title": "Standardize on the managed streaming service for CDC",
                "details": "Replaces the vendor connector that missed schema changes.",
                "created_in": 3,
            },
            {
                "title": "Cutover rehearsals run monthly until go-live",
                "details": "Each rehearsal ends with a go/no-go checkpoint.",
                "created_in": 4,
            },
        ],
    },
    {
        "name": DEMO_PREFIX + "Mobile App Launch",
        "description": (
            "Preparation for the public mobile app launch: store submissions, "
            "onboarding content, and launch instrumentation."
        ),
        "state": {
            "delivery_status": "blocked",
            "progress_summary": (
                "Launch is blocked: the store submission is rejected until the "
                "Android 12 crash is fixed and legal signs off the privacy policy."
            ),
            "completed_items": [
                "Store listing assets completed",
                "Launch dashboards and alerts live",
            ],
            "in_progress_items": [
                "Android 12 crash fix",
                "Pre-launch regression suite",
            ],
        },
        "meetings": [
            ("Launch Readiness Kickoff", when(5, 12)),
            ("Weekly Delivery Check-in", when(6, 16)),
            ("Store Submission Review", when(7, 14)),
            ("Weekly Delivery Check-in", when(8, 18)),
            ("Launch Readiness Review", when(9, 15)),
        ],
        "risks": [
            {
                "title": "App store review rejects the age-rating declaration",
                "impact": "high",
                "description": "The declared rating conflicts with the content survey.",
                "mitigation": "Refile with the corrected questionnaire.",
                "status": "open",
                "created_in": 2,
                "updated_in": 4,
            },
            {
                "title": "Crash-free sessions below the launch threshold on Android",
                "impact": "high",
                "description": "97.1% against a 99.5% launch bar.",
                "mitigation": "Fix the checkout crash before resubmission.",
                "status": "open",
                "created_in": 3,
                "updated_in": 4,
            },
            {
                "title": "Onboarding content not localized for launch markets",
                "impact": "medium",
                "description": "Two launch markets have English-only onboarding.",
                "mitigation": "Ship the localized strings in the next build.",
                "status": "resolved",
                "created_in": 1,
                "updated_in": 3,
                "resolved_in": 3,
            },
            {
                "title": "Push notification permission opt-in lower than expected",
                "impact": "low",
                "description": "Early cohorts opt in at 38% instead of 50%.",
                "mitigation": "Rework the permission primer copy.",
                "status": "resolved",
                "created_in": 1,
                "updated_in": 2,
                "resolved_in": 2,
            },
        ],
        "blockers": [
            {
                "title": "Privacy policy sign-off from legal pending",
                "description": "Blocks the store resubmission.",
                "status": "open",
                "created_in": 3,
                "updated_in": 4,
            },
            {
                "title": "Crash on Android 12 devices blocks the submission",
                "description": "Reproduced on checkout with Google Pay.",
                "status": "open",
                "created_in": 3,
                "updated_in": 4,
            },
            {
                "title": "Payment provider sandbox credentials missing",
                "description": "QA could not test purchases for two weeks.",
                "status": "resolved",
                "created_in": 1,
                "updated_in": 2,
                "resolved_in": 2,
            },
        ],
        "actions": [
            {
                "title": "Complete the store listing assets",
                "owner": "Elena",
                "details": "Screenshots, descriptions, and the promo video.",
                "status": "completed",
                "created_in": 0,
                "updated_in": 2,
                "completed_in": 2,
                "due_date": date(2026, 7, 10),
            },
            {
                "title": "Set up launch dashboards and alerts",
                "owner": "Max",
                "details": "Crash-free rate, activations, and funnel drop-off.",
                "status": "completed",
                "created_in": 1,
                "updated_in": 3,
                "completed_in": 3,
                "due_date": date(2026, 8, 30),
            },
            {
                "title": "Fix the Android 12 crash in checkout",
                "owner": "Dmitri",
                "details": "Google Pay sheet dismissal path.",
                "status": "open",
                "created_in": 3,
                "updated_in": 4,
                "due_date": date(2026, 10, 20),
            },
            {
                "title": "Run the pre-launch regression suite",
                "owner": "Team",
                "details": "Both platforms, purchase flows included.",
                "status": "open",
                "created_in": 4,
                "updated_in": 4,
            },
            {
                "title": "Prepare the phased rollout plan for stores",
                "owner": "Anna",
                "details": "10% for the first week, then 50% and full.",
                "status": "open",
                "created_in": 4,
                "updated_in": 4,
                "due_date": date(2026, 10, 28),
            },
        ],
        "decisions": [
            {
                "title": "Launch on iOS first, Android follows after the crash fix",
                "details": "iOS review is already passed.",
                "created_in": 2,
            },
            {
                "title": "Use the existing payment provider, no new integration",
                "details": "No new vendor review before launch.",
                "created_in": 1,
            },
            {
                "title": "Phased rollout: 10% of users for the first week",
                "details": "Hold at 10% unless crash-free rate stays above 99.5%.",
                "created_in": 4,
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Teardown and creation


def purge_demo_projects():
    """Delete every previous 'Demo \u00b7' project, children first."""
    ids = [
        project_id
        for (project_id,) in db.session.query(Project.id)
        .filter(Project.name.like(DEMO_PREFIX + "%"))
        .all()
    ]

    if not ids:
        return 0

    # Review resolutions can only hang off demo history events if someone
    # resolved a demo review item manually; drop them before the events.
    db.session.query(ReviewResolution).filter(
        ReviewResolution.history_event_id.in_(
            db.session.query(HistoryEvent.id).filter(
                HistoryEvent.project_id.in_(ids)
            )
        )
    ).delete(synchronize_session=False)

    db.session.query(HistoryEvent).filter(
        HistoryEvent.project_id.in_(ids)
    ).delete(synchronize_session=False)

    for model in (Risk, Blocker, ActionItem, Decision):
        db.session.query(model).filter(model.project_id.in_(ids)).delete(
            synchronize_session=False
        )

    # ProjectState.updated_in_meeting_id also references meetings: if a
    # demo project was ever analyzed through the app between two seed
    # runs, its state points at a demo meeting, so the states must go
    # before the meetings they reference (plain FKs, no ON DELETE rule).
    db.session.query(ProjectState).filter(ProjectState.project_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(Meeting).filter(Meeting.project_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(Project).filter(Project.id.in_(ids)).delete(
        synchronize_session=False
    )

    return len(ids)


def seed_demo_project(spec):
    """Create one demo project with meetings, items, events, and state."""
    project = Project(name=spec["name"], description=spec["description"])
    db.session.add(project)
    db.session.flush()

    short_name = spec["name"][len(DEMO_PREFIX):]
    meetings = []

    for title, created_at in spec["meetings"]:
        meeting = Meeting(
            project_id=project.id,
            title=title,
            original_text=f"Demo notes for {short_name} - {title}.",
            analysis_text=(
                "Demo analysis: project status, risks, and actions recorded "
                "for the seed dataset."
            ),
            analysis_json={},
            provider=PROVIDER,
            model=MODEL,
            created_at=created_at,
        )
        db.session.add(meeting)
        meetings.append(meeting)

    db.session.flush()

    events = []
    counts = {"meetings": len(meetings), "risks": 0, "blockers": 0,
              "action_items": 0, "decisions": 0, "history_events": 0}

    # Risks: canonical_title = title, unique inside the project.
    for item in spec["risks"]:
        risk = Risk(
            project_id=project.id,
            title=item["title"],
            canonical_title=item["title"],
            description=item.get("description", ""),
            impact=item["impact"],
            mitigation=item.get("mitigation", ""),
            status=item["status"],
            created_in_meeting_id=meetings[item["created_in"]].id,
            updated_in_meeting_id=meetings[item["updated_in"]].id,
        )

        if item["status"] == "resolved":
            resolved_meeting = meetings[item["resolved_in"]]
            risk.resolved_at = resolved_meeting.created_at + timedelta(hours=1)
            risk.resolved_in_meeting_id = resolved_meeting.id

        db.session.add(risk)
        events.append(("risk", risk, f"Recorded risk: {item['title']}",
                       item["created_in"]))
        counts["risks"] += 1

    for item in spec["blockers"]:
        blocker = Blocker(
            project_id=project.id,
            title=item["title"],
            canonical_title=item["title"],
            description=item.get("description", ""),
            status=item["status"],
            created_in_meeting_id=meetings[item["created_in"]].id,
            updated_in_meeting_id=meetings[item["updated_in"]].id,
        )

        if item["status"] == "resolved":
            resolved_meeting = meetings[item["resolved_in"]]
            blocker.resolved_at = resolved_meeting.created_at + timedelta(hours=1)
            blocker.resolved_in_meeting_id = resolved_meeting.id

        db.session.add(blocker)
        events.append(("blocker", blocker, f"Recorded blocker: {item['title']}",
                       item["created_in"]))
        counts["blockers"] += 1

    for item in spec["actions"]:
        action = ActionItem(
            project_id=project.id,
            title=item["title"],
            canonical_title=item["title"],
            details=item.get("details", ""),
            owner=item.get("owner"),
            due_date=item.get("due_date"),
            status=item["status"],
            created_in_meeting_id=meetings[item["created_in"]].id,
            updated_in_meeting_id=meetings[item["updated_in"]].id,
        )

        if item["status"] == "completed":
            completed_meeting = meetings[item["completed_in"]]
            action.completed_at = completed_meeting.created_at + timedelta(hours=1)
            action.completed_in_meeting_id = completed_meeting.id

        db.session.add(action)
        events.append(("action_item", action,
                       f"Recorded action item: {item['title']}",
                       item["created_in"]))
        counts["action_items"] += 1

    for item in spec["decisions"]:
        decision = Decision(
            project_id=project.id,
            title=item["title"],
            canonical_title=item["title"],
            details=item.get("details", ""),
            created_in_meeting_id=meetings[item["created_in"]].id,
        )
        db.session.add(decision)
        events.append(("decision", decision,
                       f"Recorded decision: {item['title']}",
                       item["created_in"]))
        counts["decisions"] += 1

    db.session.flush()

    # Creation events, dated by the meeting that "recorded" each item -
    # the same event types and summaries project_memory.py writes.
    for entity_type, entity, summary, meeting_index in events:
        db.session.add(
            HistoryEvent(
                project_id=project.id,
                meeting_id=meetings[meeting_index].id,
                entity_type=entity_type,
                entity_id=entity.id,
                event_type="created",
                summary=summary,
                created_at=meetings[meeting_index].created_at,
            )
        )
        counts["history_events"] += 1

    state = ProjectState(
        project_id=project.id,
        delivery_status=spec["state"]["delivery_status"],
        progress_summary=spec["state"]["progress_summary"],
        completed_items=spec["state"]["completed_items"],
        in_progress_items=spec["state"]["in_progress_items"],
        updated_at=utcnow(),
    )
    db.session.add(state)

    return counts


def upsert_test_project_states():
    """Upsert the ProjectState of the five named smoke-test projects."""
    updated = 0

    for spec in TEST_PROJECT_STATES:
        project = Project.query.filter_by(name=spec["name"]).first()

        if project is None:
            project = Project(
                name=spec["name"],
                description="[demo-seed] Smoke-test project created by the demo seed.",
            )
            db.session.add(project)
            db.session.flush()

        state = ProjectState.query.filter_by(project_id=project.id).first()

        if state is None:
            state = ProjectState(project_id=project.id)
            db.session.add(state)

        state.delivery_status = spec["delivery_status"]
        state.progress_summary = spec["progress_summary"]
        state.completed_items = spec["completed_items"]
        state.in_progress_items = spec["in_progress_items"]
        state.updated_at = utcnow()
        updated += 1

    return updated


def main():
    configure_database()

    removed = purge_demo_projects()

    totals = {
        "projects": 0,
        "meetings": 0,
        "risks": 0,
        "blockers": 0,
        "action_items": 0,
        "decisions": 0,
        "history_events": 0,
    }

    for spec in DEMO_PROJECTS:
        counts = seed_demo_project(spec)
        totals["projects"] += 1

        for key, value in counts.items():
            totals[key] += value

    states = upsert_test_project_states()

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    print(f"Removed {removed} previous demo project(s); created:")
    print(f"  projects        {totals['projects']}")
    print(f"  meetings        {totals['meetings']}")
    print(f"  risks           {totals['risks']}")
    print(f"  blockers        {totals['blockers']}")
    print(f"  action items    {totals['action_items']}")
    print(f"  decisions       {totals['decisions']}")
    print(f"  history events  {totals['history_events']}")
    print(f"Upserted ProjectState for {states} smoke-test project(s):")
    for spec in TEST_PROJECT_STATES:
        print(f"  {spec['name']} -> {spec['delivery_status']}")
    print("Real projects (inventory-management-system, ai-delivery-assistant) untouched.")


if __name__ == "__main__":
    main()
