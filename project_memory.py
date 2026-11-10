import logging
from datetime import date

from database import db
from matching import normalize_title
from models import (
    ActionItem,
    Blocker,
    Decision,
    HistoryEvent,
    ProjectState,
    Risk,
    utcnow,
)

# varchar(n) widths from schema.sql, for the columns that LLM output can
# actually overflow. SQLite does not enforce these, so a too-long value
# is silently accepted locally and then fails on a real PostgreSQL.
# Anything not listed here goes to a column that is TEXT (unbounded) or
# is validated elsewhere.
COLUMN_LIMITS = {
    "delivery_status": 20,
    "status": 20,
    "impact": 20,
    "owner": 160,
    "title": 300,
    "canonical_title": 300,
    "provider": 30,
    "model": 120,
    "action": 30,
    "event_type": 40,
    "entity_type": 40,
    # The two columns an operator controls directly rather than through
    # the LLM: the project name on create, and the uploaded file's name.
    # Both reach the database without going through _value, so they were
    # unclamped while every LLM-sourced column was covered.
    "name": 200,
    "source_filename": 255,
}


def _bounded(value, key):
    """Clamp a value to the width of the column it is written into."""

    limit = COLUMN_LIMITS.get(key)

    if limit is None or not isinstance(value, str):
        return value

    return value[:limit]


# The statuses the reports and the resolution-rate metric understand.
# Anything outside this set is invisible to both: a stranded item then
# reads as "nothing outstanding" while it still sits in the database.
ITEM_STATUSES = {"open", "resolved", "completed"}

logger = logging.getLogger("ai-delivery-assistant.memory")


def _normalize_status(value, fallback="open"):
    """
    Map an LLM-supplied status onto the set the code understands.

    An unrecognized value becomes the fallback and is logged, so the
    drift is visible instead of silently excluded from the reports.
    """

    status = value.strip().lower() if isinstance(value, str) else ""

    if status in ITEM_STATUSES:
        return status

    if status:
        logger.warning(
            "Unrecognized item status %r; treating it as %r.", status, fallback
        )

    return fallback


def _value(item, key, default=""):
    value = item.get(key, default) if isinstance(item, dict) else default
    value = value.strip() if isinstance(value, str) else value
    return _bounded(value, key)


def _find_by_canonical_title(model, project_id, title):
    """Find the item whose canonical identity matches this title."""
    return model.query.filter_by(
        project_id=project_id,
        canonical_title=normalize_title(title),
    ).first()


def _plan_existing_item(project, model_class, item):
    """
    Resolve the AI-provided existing_item_id for a consolidation plan
    entry and validate that it is safe to apply.

    Returns an (existing, problem) tuple. When the id is valid, problem
    is None. Otherwise existing is None and problem describes why:
    "missing", "invalid", "not_found", or "foreign" (an item that
    belongs to a different project).
    """
    existing_item_id = (
        item.get("existing_item_id") if isinstance(item, dict) else None
    )

    if existing_item_id in (None, ""):
        return None, "missing"

    try:
        existing_item_id = int(existing_item_id)
    except (TypeError, ValueError):
        return None, "invalid"

    existing = db.session.get(model_class, existing_item_id)

    if existing is None:
        return None, "not_found"

    if existing.project_id != project.id:
        return None, "foreign"

    return existing, None


def _needs_review_event(project, meeting, entity_label, item, problem):
    """
    Record a consolidation plan entry that could not be applied safely.

    Guardrails route invalid or unsupported plan entries here instead
    of silently dropping them, so the finding stays visible in the
    history trail for manual review.
    """
    new_item = item.get("new_item", {}) if isinstance(item, dict) else {}
    title = _value(new_item, "title") or "(no title)"
    decision = item.get("decision") if isinstance(item, dict) else None
    reason = _value(item, "reason") or "(no reason given)"

    _event(
        project.id,
        meeting.id,
        entity_label,
        None,
        "needs_review",
        (
            f"Needs review: {entity_label} plan could not be applied "
            f"({problem}; decision: {decision}). "
            f"Finding: {title}. Reason: {reason}"
        ),
        None,
        {"plan_item": item},
    )


def _event(
    project_id,
    meeting_id,
    entity_type,
    entity_id,
    event_type,
    summary,
    before=None,
    after=None,
):
    db.session.add(
        HistoryEvent(
            project_id=project_id,
            meeting_id=meeting_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            summary=summary,
            before_data=before,
            after_data=after,
        )
    )


def _apply_state(project, meeting, analysis):
    state = project.state or ProjectState(project=project)

    before = {
        "delivery_status": state.delivery_status,
        "progress_summary": state.progress_summary,
    }

    state.delivery_status = (
        _value(analysis, "project_status", "unknown") or "unknown"
    )
    state.progress_summary = _value(analysis, "progress_summary")
    state.completed_items = analysis.get("completed_items", [])
    state.in_progress_items = analysis.get("in_progress_items", [])
    state.updated_in_meeting_id = meeting.id

    db.session.add(state)
    db.session.flush()

    _event(
        project.id,
        meeting.id,
        "project_state",
        state.id,
        "updated",
        "Updated current project status.",
        before,
        {
            "delivery_status": state.delivery_status,
            "progress_summary": state.progress_summary,
        },
    )


# One create-or-update cycle, driven by a spec, because the three cycles
# below used to be three copies of the same skeleton. They were not
# identical: each item type has its own detail fields, its own vocabulary
# for "done", and only action items parse a due date. Those differences
# live in the specs, where they can be read side by side, rather than
# being buried in three near-identical blocks where a change to one is
# silently not made to the other two.
#
# The subtleties that the specs have to carry, each of which was a real
# behaviour of the code it replaced:
#
# - A field the finding does not mention keeps its current value on
#   update. _value defaults to "" (or "unknown"), which would erase
#   stored detail that was never updated.
# - On create the defaults are the empty ones the old code used:
#   description "", impact "unknown", owner None. They are not the update
#   defaults, so they are stated separately.
# - A finding with no due date must not clear the stored one, and an
#   unparseable date falls back to the stored value rather than to None.
# - The history event snapshot differs per type, because the fields each
#   type has differ.
# Sentinels for the fields a "done" mark sets, so a literal value and a
# computed one cannot be confused. Marking an item done sets three fields
# at once: the status (a literal string), the timestamp (computed), and
# the meeting it happened in (the current meeting). Writing that as
# (field, value) pairs alone cannot tell "completed" the literal from
# "completed" a marker, and getting it wrong sets status to the meeting id.
_NOW = object()
_THIS_MEETING = object()

_ITEM_SPECS = {
    "risk": {
        "model": Risk,
        "entity": "risk",
        "label": "risk",
        "done_status": "resolved",
        "done_action": "resolved",
        "done_label": "Resolved",
        "update_label": "Updated",
        "detail_fields": ("description", "impact", "mitigation"),
        "create_defaults": {"description": "", "impact": "unknown", "mitigation": ""},
        "due_date": False,
        "snapshot_fields": ("status", "impact", "mitigation"),
        "done_marks": (
            ("status", "resolved"),
            ("resolved_at", _NOW),
            ("resolved_in_meeting_id", _THIS_MEETING),
        ),
    },
    "blocker": {
        "model": Blocker,
        "entity": "blocker",
        "label": "blocker",
        "done_status": "resolved",
        "done_action": "resolved",
        "done_label": "Resolved",
        "update_label": "Updated",
        "detail_fields": ("description",),
        "create_defaults": {"description": ""},
        "due_date": False,
        "snapshot_fields": ("status",),
        "done_marks": (
            ("status", "resolved"),
            ("resolved_at", _NOW),
            ("resolved_in_meeting_id", _THIS_MEETING),
        ),
    },
    "action_item": {
        "model": ActionItem,
        "entity": "action_item",
        "label": "action item",
        "done_status": "completed",
        "done_action": "completed",
        "done_label": "Completed",
        "update_label": "Updated",
        "detail_fields": ("details", "owner", "due_date"),
        "create_defaults": {"details": "", "owner": None},
        "due_date": True,
        "snapshot_fields": ("status", "owner", "due_date"),
        "done_marks": (
            ("status", "completed"),
            ("completed_at", _NOW),
            ("completed_in_meeting_id", _THIS_MEETING),
        ),
    },
}


def _snapshot(record, fields):
    """The before/after dict for a history event, for the fields a type has."""

    data = {}
    for field in fields:
        value = getattr(record, field, None)
        data[field] = str(value) if isinstance(value, date) else value
    return data


def _parse_due_date(item, existing):
    """
    The due date a finding implies, or the stored one.

    A finding that gives no date must not clear a stored one, and a date
    that will not parse falls back to the stored value rather than to
    None. Both were explicit behaviours of the code this replaces.
    """

    source = _value(item, "due_date", None)
    stored = getattr(existing, "due_date", None)

    if not source:
        return stored

    try:
        return date.fromisoformat(source)
    except (ValueError, TypeError):
        return stored


def _mark_done(record, spec, meeting):
    """Set the fields that mean this item is done, per the type's vocabulary."""

    for field, value in spec["done_marks"]:
        if value is _NOW:
            setattr(record, field, utcnow())
        elif value is _THIS_MEETING:
            setattr(record, field, meeting.id)
        else:
            setattr(record, field, value)


def _apply_item_group(project, meeting, findings, spec):
    """
    Apply every finding of one item type: create what is new, update what
    already exists, and record a history event either way.
    """

    model = spec["model"]

    for item in findings or []:
        title = _value(item, "title")

        if not title:
            continue

        existing = _find_by_canonical_title(model, project.id, title)
        done = _value(item, "status", "open") == spec["done_status"]
        due_date = (
            _parse_due_date(item, existing) if spec["due_date"] else None
        )

        if existing is None:
            record = model(
                project_id=project.id,
                title=title,
                canonical_title=normalize_title(title),
                status=spec["done_status"] if done else "open",
                created_in_meeting_id=meeting.id,
                updated_in_meeting_id=meeting.id,
                **spec["create_defaults"],
            )
            model_fields = spec["detail_fields"]
            for field in model_fields:
                if field == "due_date" and spec["due_date"]:
                    setattr(record, field, due_date)
                else:
                    setattr(record, field, _value(item, field))

            if done:
                _mark_done(record, spec, meeting)

            db.session.add(record)
            db.session.flush()

            _event(
                project.id,
                meeting.id,
                spec["entity"],
                record.id,
                "created",
                f"Recorded {spec['label']}: {title}",
                after=_snapshot(record, spec["snapshot_fields"]),
            )
            continue

        before = _snapshot(existing, spec["snapshot_fields"])

        for field in spec["detail_fields"]:
            if field == "due_date" and spec["due_date"]:
                if due_date is not None:
                    existing.due_date = due_date
            else:
                setattr(
                    existing,
                    field,
                    _value(item, field, getattr(existing, field, None)),
                )

        existing.updated_in_meeting_id = meeting.id

        if done:
            _mark_done(existing, spec, meeting)
            action = spec["done_action"]
            summary = f"{spec['done_label']} {spec['label']}: {title}"
        else:
            action = "updated"
            summary = f"{spec['update_label']} {spec['label']}: {title}"

        _event(
            project.id,
            meeting.id,
            spec["entity"],
            existing.id,
            action,
            summary,
            before,
            _snapshot(existing, spec["snapshot_fields"]),
        )


def _apply_risks(project, meeting, risks):
    _apply_item_group(project, meeting, risks, _ITEM_SPECS["risk"])


def _apply_blockers(project, meeting, blockers):
    _apply_item_group(project, meeting, blockers, _ITEM_SPECS["blocker"])


def _apply_actions(project, meeting, actions):
    _apply_item_group(project, meeting, actions, _ITEM_SPECS["action_item"])


def _apply_consolidation_item(
    project,
    meeting,
    item,
    decision_type,
    model_class,
    created,
):
    """
    Apply a single consolidation decision to the database.

    decision_type:
        "CREATE", "MERGE", "UPDATE", or "CONFLICT"

    model_class:
        Risk, Blocker, or ActionItem
    """

    new_item = item.get("new_item", {})
    existing_item_id = item.get("existing_item_id")

    title = _value(new_item, "title")
    reason = _value(item, "reason")

    # Normalize the AI-provided decision value (for example "create").
    if isinstance(decision_type, str):
        decision_type = decision_type.strip().upper()

    # Human-readable label used in history messages.
    # Keep database entity_type values separate from UI wording.
    if model_class == ActionItem:
        entity_label = "action item"
    elif model_class == Risk:
        entity_label = "risk"
    elif model_class == Blocker:
        entity_label = "blocker"
    else:
        return

    if not title:
        # A plan entry without a title cannot be applied; preserve it
        # for review instead of dropping it silently.
        _needs_review_event(project, meeting, entity_label, item, "missing_title")
        return

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------
    if decision_type == "CREATE":
        created_titles = created.setdefault(model_class, {})
        duplicate_id = created_titles.get(normalize_title(title))

        if duplicate_id is not None:
            # The same plan already created this title in this meeting:
            # merge into it instead of creating a duplicate.
            _event(
                project.id,
                meeting.id,
                entity_label,
                duplicate_id,
                "merged",
                (
                    f"Merged duplicate {entity_label}: {title} "
                    f"(duplicate CREATE within the same plan). "
                    f"Reason: {reason}"
                ),
            )
            return

        if model_class == ActionItem:
            due_date = _value(new_item, "due_date")

            try:
                due_date = (
                    date.fromisoformat(due_date)
                    if due_date
                    else None
                )
            except (ValueError, TypeError):
                due_date = None

            obj = ActionItem(
                project_id=project.id,
                title=title,
                canonical_title=normalize_title(title),
                details=_value(new_item, "details"),
                owner=_value(new_item, "owner"),
                due_date=due_date,
                status=_normalize_status(_value(new_item, "status", "open")),
                created_in_meeting_id=meeting.id,
                updated_in_meeting_id=meeting.id,
            )

        elif model_class == Risk:
            obj = Risk(
                project_id=project.id,
                title=title,
                canonical_title=normalize_title(title),
                description=_value(new_item, "description"),
                impact=_value(new_item, "impact", "unknown"),
                mitigation=_value(new_item, "mitigation"),
                status=_normalize_status(_value(new_item, "status", "open")),
                created_in_meeting_id=meeting.id,
                updated_in_meeting_id=meeting.id,
            )

        elif model_class == Blocker:
            obj = Blocker(
                project_id=project.id,
                title=title,
                canonical_title=normalize_title(title),
                description=_value(new_item, "description"),
                status=_normalize_status(_value(new_item, "status", "open")),
                created_in_meeting_id=meeting.id,
                updated_in_meeting_id=meeting.id,
            )

        else:
            return

        if _value(new_item, "status") in (
            "completed",
            "resolved",
        ):
            if model_class == ActionItem:
                obj.status = "completed"
                obj.completed_at = utcnow()
                obj.completed_in_meeting_id = meeting.id
            else:
                obj.status = "resolved"
                obj.resolved_at = utcnow()
                obj.resolved_in_meeting_id = meeting.id

        db.session.add(obj)
        db.session.flush()

        created_titles[normalize_title(title)] = obj.id

        _event(
            project.id,
            meeting.id,
            entity_label,
            obj.id,
            "created",
            f"Created {entity_label}: {title} (via consolidation)",
        )

    # ---------------------------------------------------------
    # MERGE
    # ---------------------------------------------------------
    elif decision_type == "MERGE":

        if not existing_item_id:
            _needs_review_event(
                project,
                meeting,
                entity_label,
                item,
                "missing",
            )

        else:
            existing, problem = _plan_existing_item(
                project,
                model_class,
                item,
            )

            if problem:
                _needs_review_event(
                    project,
                    meeting,
                    entity_label,
                    item,
                    problem,
                )

            else:
                # Existing item already represents this information.
                # Do not create a duplicate.
                _event(
                    project.id,
                    meeting.id,
                    entity_label,
                    existing.id,
                    "merged",
                    (
                        f"Merged duplicate {entity_label}: "
                        f"{title}. Reason: {reason}"
                    ),
                )

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------
    elif decision_type == "UPDATE":

        if not existing_item_id:
            _needs_review_event(
                project,
                meeting,
                entity_label,
                item,
                "missing",
            )

        else:
            existing, problem = _plan_existing_item(
                project,
                model_class,
                item,
            )

            if problem:
                _needs_review_event(
                    project,
                    meeting,
                    entity_label,
                    item,
                    problem,
                )

            if existing:
                before = None
                after = None

                if model_class == ActionItem:
                    before = {
                        "title": existing.title,
                        "details": existing.details,
                        "owner": existing.owner,
                        "status": existing.status,
                    }

                    # A field the plan does not mention must keep its
                    # current value: _value defaults to "", which would
                    # silently erase meeting data that was never updated.
                    existing.details = _value(
                        new_item,
                        "details",
                        existing.details,
                    )

                    existing.owner = _value(
                        new_item,
                        "owner",
                        existing.owner,
                    )

                    existing.status = _value(
                        new_item,
                        "status",
                        existing.status,
                    )

                    due_date = _value(
                        new_item,
                        "due_date",
                    )

                    try:
                        existing.due_date = (
                            date.fromisoformat(due_date)
                            if due_date
                            else existing.due_date
                        )
                    except (ValueError, TypeError):
                        pass

                    after = {
                        "title": existing.title,
                        "details": existing.details,
                        "owner": existing.owner,
                        "status": existing.status,
                    }

                elif model_class == Risk:
                    before = {
                        "description": existing.description,
                        "impact": existing.impact,
                        "mitigation": existing.mitigation,
                        "status": existing.status,
                    }

                    existing.description = _value(
                        new_item,
                        "description",
                        existing.description,
                    )

                    existing.impact = _value(
                        new_item,
                        "impact",
                        existing.impact,
                    )

                    existing.mitigation = _value(
                        new_item,
                        "mitigation",
                        existing.mitigation,
                    )

                    existing.status = _value(
                        new_item,
                        "status",
                        existing.status,
                    )

                    after = {
                        "description": existing.description,
                        "impact": existing.impact,
                        "mitigation": existing.mitigation,
                        "status": existing.status,
                    }

                elif model_class == Blocker:
                    before = {
                        "description": existing.description,
                        "status": existing.status,
                    }

                    existing.description = _value(
                        new_item,
                        "description",
                        existing.description,
                    )

                    existing.status = _value(
                        new_item,
                        "status",
                        existing.status,
                    )

                    after = {
                        "description": existing.description,
                        "status": existing.status,
                    }

                existing.updated_in_meeting_id = meeting.id

                # Keep resolution/completion stamps consistent with the
                # new status (previously the status changed but the
                # stamps did not, leaving resolved items without
                # resolved_at and completed ones without completed_at).
                if model_class == ActionItem:
                    if existing.status == "completed":
                        existing.completed_at = utcnow()
                        existing.completed_in_meeting_id = meeting.id
                    elif existing.completed_at is not None:
                        # Reopened: clear the stale completion stamp.
                        existing.completed_at = None
                        existing.completed_in_meeting_id = None
                else:
                    if existing.status == "resolved":
                        existing.resolved_at = utcnow()
                        existing.resolved_in_meeting_id = meeting.id
                    elif existing.resolved_at is not None:
                        # Reopened: clear the stale resolution stamp.
                        existing.resolved_at = None
                        existing.resolved_in_meeting_id = None

                _event(
                    project.id,
                    meeting.id,
                    entity_label,
                    existing.id,
                    "updated",
                    (
                        f"Updated {entity_label}: "
                        f"{title}. Reason: {reason}"
                    ),
                    before,
                    after,
                )

    # ---------------------------------------------------------
    # CONFLICT
    # ---------------------------------------------------------
    elif decision_type == "CONFLICT":

        if not existing_item_id:
            _needs_review_event(
                project,
                meeting,
                entity_label,
                item,
                "missing",
            )

        else:
            existing, problem = _plan_existing_item(
                project,
                model_class,
                item,
            )

            if problem:
                _needs_review_event(
                    project,
                    meeting,
                    entity_label,
                    item,
                    problem,
                )

            else:
                # Preserve the existing item and record the conflict.
                _event(
                    project.id,
                    meeting.id,
                    entity_label,
                    existing.id,
                    "conflict",
                    (
                        f"Conflict detected for {entity_label}: "
                        f"{title}. Existing preserved. "
                        f"Reason: {reason}"
                    ),
                    {
                        "title": existing.title,
                        "status": existing.status,
                    },
                    {
                        "conflicting_title": title,
                        "conflicting_status": _value(
                            new_item,
                            "status",
                        ),
                    },
                )

    else:
        # Unknown decision type from the AI plan: preserve the entry
        # for review instead of dropping it silently.
        _needs_review_event(
            project,
            meeting,
            entity_label,
            item,
            "unknown_decision",
        )


def apply_consolidation_plan(
    project,
    meeting,
    consolidation_plan,
):
    """
    Apply the AI consolidation plan to the database.

    Decision types:

    CREATE:
        Insert a new item.

    MERGE:
        Do not create a duplicate. Record that the new item
        was recognized as an existing item.

    UPDATE:
        Update the existing item with new information.

    CONFLICT:
        Preserve the existing item and record the conflict.
    """

    # Titles already created by this plan, for intra-plan deduplication.
    created = {}
    created_decisions = {}

    # Process action items
    for item in consolidation_plan.get(
        "action_items",
        [],
    ):
        decision = item.get("decision")

        _apply_consolidation_item(
            project,
            meeting,
            item,
            decision,
            ActionItem,
            created,
        )

    # Process risks
    for item in consolidation_plan.get(
        "risks",
        [],
    ):
        decision = item.get("decision")

        _apply_consolidation_item(
            project,
            meeting,
            item,
            decision,
            Risk,
            created,
        )

    # Process blockers
    for item in consolidation_plan.get(
        "blockers",
        [],
    ):
        decision = item.get("decision")

        _apply_consolidation_item(
            project,
            meeting,
            item,
            decision,
            Blocker,
            created,
        )

    # Process decisions
    for item in consolidation_plan.get(
        "decisions",
        [],
    ):
        decision = item.get("decision")

        if isinstance(decision, str):
            decision = decision.strip().upper()

        new_item = item.get("new_item", {})
        title = _value(new_item, "title")

        if decision == "MERGE":
            # A decision record is append-only: a duplicate title
            # merges into the existing record instead of creating one.
            existing, problem = _plan_existing_item(
                project,
                Decision,
                item,
            )

            if problem:
                _needs_review_event(
                    project,
                    meeting,
                    "decision",
                    item,
                    problem,
                )
            else:
                _event(
                    project.id,
                    meeting.id,
                    "decision",
                    existing.id,
                    "merged",
                    (
                        f"Merged duplicate decision: {existing.title}. "
                        f"Reason: {_value(item, 'reason') or '(no reason given)'}"
                    ),
                )

            continue

        if decision != "CREATE":
            # Decisions are append-only records: the plan can create
            # or merge them. Anything else is preserved for review.
            _needs_review_event(
                project,
                meeting,
                "decision",
                item,
                "unsupported_decision",
            )

            continue

        if not title:
            _needs_review_event(
                project,
                meeting,
                "decision",
                item,
                "missing_title",
            )

            continue

        duplicate_decision_id = created_decisions.get(normalize_title(title))

        if duplicate_decision_id is not None:
            _event(
                project.id,
                meeting.id,
                "decision",
                duplicate_decision_id,
                "merged",
                (
                    f"Merged duplicate decision: {title} "
                    f"(duplicate CREATE within the same plan)."
                ),
            )

            continue

        decision_record = Decision(
            project_id=project.id,
            title=title,
            canonical_title=normalize_title(title),
            details=_value(
                new_item,
                "details",
            ),
            created_in_meeting_id=meeting.id,
        )

        db.session.add(decision_record)
        db.session.flush()

        created_decisions[normalize_title(title)] = decision_record.id

        _event(
            project.id,
            meeting.id,
            "decision",
            decision_record.id,
            "created",
            (
                f"Recorded decision: "
                f"{title} (via consolidation)"
            ),
        )


REVIEW_ENTITY_MODELS = {
    "risk": Risk,
    "risks": Risk,
    "blocker": Blocker,
    "blockers": Blocker,
    "action item": ActionItem,
    "action_item": ActionItem,
    "action items": ActionItem,
    "decision": Decision,
    "decisions": Decision,
}


def review_model_class(entity_type):
    """The model class a needs-review event refers to, if any."""
    if not isinstance(entity_type, str):
        return None

    return REVIEW_ENTITY_MODELS.get(entity_type.strip().casefold())


def apply_review_create(project, meeting, entity_type, plan_item):
    """
    Apply a needs-review plan item as a CREATE from the review queue.

    Returns the created record. Raises ValueError when the item cannot
    be created safely, so the route can surface the reason.
    """
    model_class = review_model_class(entity_type)

    if model_class is None:
        raise ValueError(f"Unknown entity type: {entity_type}")

    new_item = plan_item.get("new_item") if isinstance(plan_item, dict) else {}
    title = _value(new_item, "title")

    if not title:
        raise ValueError("The plan item has no title to create.")

    canonical = normalize_title(title)

    # One row per canonical title per project: point the reviewer at
    # the existing item instead of creating a duplicate.
    existing = model_class.query.filter_by(
        project_id=project.id,
        canonical_title=canonical,
    ).first()

    if existing is not None:
        raise ValueError(
            f"An item with this title already exists ({existing.title}); "
            f"link the finding to it instead."
        )

    if model_class == Decision:
        record = Decision(
            project_id=project.id,
            title=title,
            canonical_title=canonical,
            details=_value(new_item, "details"),
            created_in_meeting_id=meeting.id,
        )

        db.session.add(record)
        db.session.flush()

        _event(
            project.id,
            meeting.id,
            entity_type,
            record.id,
            "created",
            f"Created decision: {title} (from review queue)",
        )

        return record

    if model_class == ActionItem:
        due_date = _value(new_item, "due_date")

        try:
            due_date = date.fromisoformat(due_date) if due_date else None
        except (ValueError, TypeError):
            due_date = None

        record = ActionItem(
            project_id=project.id,
            title=title,
            canonical_title=canonical,
            details=_value(new_item, "details"),
            owner=_value(new_item, "owner"),
            due_date=due_date,
            status=_normalize_status(_value(new_item, "status", "open")),
            created_in_meeting_id=meeting.id,
            updated_in_meeting_id=meeting.id,
        )
    else:
        record = model_class(
            project_id=project.id,
            title=title,
            canonical_title=canonical,
            description=_value(new_item, "description"),
            status=_normalize_status(_value(new_item, "status", "open")),
            created_in_meeting_id=meeting.id,
            updated_in_meeting_id=meeting.id,
        )

        if model_class == Risk:
            record.impact = _value(new_item, "impact", "unknown")
            record.mitigation = _value(new_item, "mitigation")

    if record.status in ("resolved", "completed"):
        if model_class == ActionItem:
            record.completed_at = utcnow()
            record.completed_in_meeting_id = meeting.id
        else:
            record.resolved_at = utcnow()
            record.resolved_in_meeting_id = meeting.id

    db.session.add(record)
    db.session.flush()

    _event(
        project.id,
        meeting.id,
        entity_type,
        record.id,
        "created",
        f"Created {entity_type}: {title} (from review queue)",
    )

    return record


def apply_review_merge(project, meeting, entity_type, plan_item, target):
    """
    Record a merge of a needs-review finding into an existing item.

    The existing item keeps its data; the merge is recorded in the
    history trail.
    """
    new_item = plan_item.get("new_item") if isinstance(plan_item, dict) else {}
    title = _value(new_item, "title") or "(no title)"
    reason = _value(plan_item, "reason") or "(no reason given)"

    _event(
        project.id,
        meeting.id,
        entity_type,
        target.id,
        "merged",
        (
            f"Merged duplicate {entity_type}: {title} -> {target.title} "
            f"(from review queue). Reason: {reason}"
        ),
    )

    return target


def apply_state(project, meeting, analysis):
    """
    Apply the meeting analysis to the current project state.

    Used by the consolidation path, which otherwise only reconciles
    individual memory items and would silently drop the meeting's
    status and progress summary.
    """
    _apply_state(project, meeting, analysis)


def apply_meeting_analysis(
    project,
    meeting,
    analysis,
):
    """
    Mutate current state while retaining an immutable
    meeting and event trail.
    """

    _apply_state(
        project,
        meeting,
        analysis,
    )

    _apply_risks(
        project,
        meeting,
        analysis.get("risks"),
    )

    _apply_blockers(
        project,
        meeting,
        analysis.get("blockers"),
    )

    _apply_actions(
        project,
        meeting,
        analysis.get("action_items"),
    )

    # A null section must behave like an absent one. The sibling loops
    # above use "or []"; this one did not, so an explicit
    # "decisions": null reached iteration as None and raised TypeError,
    # which api.py's except tuple does not catch.
    for item in analysis.get(
        "decisions",
        [],
    ) or []:
        title = _value(item, "title")

        if title:
            # Idempotency for the fallback path: a decision whose
            # canonical title already exists is merged, not duplicated.
            existing_decision = Decision.query.filter_by(
                project_id=project.id,
                canonical_title=normalize_title(title),
            ).first()

            if existing_decision is not None:
                _event(
                    project.id,
                    meeting.id,
                    "decision",
                    existing_decision.id,
                    "merged",
                    f"Merged duplicate decision: {existing_decision.title}",
                )
                continue

            decision = Decision(
                project_id=project.id,
                title=title,
                canonical_title=normalize_title(title),
                details=_value(
                    item,
                    "details",
                ),
                created_in_meeting_id=meeting.id,
            )

            db.session.add(decision)
            db.session.flush()

            _event(
                project.id,
                meeting.id,
                "decision",
                decision.id,
                "created",
                f"Recorded decision: {title}",
            )