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


# The consolidation path has its own field maps, separate from the
# meeting-analysis ones above, because the two paths treat the same fields
# differently: here a new item's status goes through _normalize_status,
# an updated item's status does not, and the update snapshot carries the
# title while the analysis snapshot does not. Reusing one map for both
# would quietly change one of the two behaviours.
_PLAN_ITEM_SPECS = {
    ActionItem: {
        "label": "action item",
        "create_fields": ("details", "owner"),
        "create_due_date": True,
        "create_defaults": {"details": "", "owner": ""},
        "update_fields": ("details", "owner", "status"),
        "update_due_date": True,
        "snapshot_fields": ("title", "details", "owner", "status"),
        "done_status": "completed",
        "at_field": "completed_at",
        "in_meeting_field": "completed_in_meeting_id",
    },
    Risk: {
        "label": "risk",
        "create_fields": ("description", "impact", "mitigation"),
        "create_due_date": False,
        "create_defaults": {
            "description": "",
            "impact": "unknown",
            "mitigation": "",
        },
        "update_fields": ("description", "impact", "mitigation", "status"),
        "update_due_date": False,
        "snapshot_fields": ("description", "impact", "mitigation", "status"),
        "done_status": "resolved",
        "at_field": "resolved_at",
        "in_meeting_field": "resolved_in_meeting_id",
    },
    Blocker: {
        "label": "blocker",
        "create_fields": ("description",),
        "create_due_date": False,
        "create_defaults": {"description": ""},
        "update_fields": ("description", "status"),
        "update_due_date": False,
        "snapshot_fields": ("description", "status"),
        "done_status": "resolved",
        "at_field": "resolved_at",
        "in_meeting_field": "resolved_in_meeting_id",
    },
}


def _entity_label(model_class):
    """Human-readable label for history messages, kept separate from entity_type."""

    spec = _PLAN_ITEM_SPECS.get(model_class)
    return spec["label"] if spec else None


def _build_plan_item(project, meeting, model_class, new_item, title):
    """A new record for a CREATE decision, with the type's own fields."""

    spec = _PLAN_ITEM_SPECS[model_class]

    fields = {}
    for field in spec["create_fields"]:
        fields[field] = _value(new_item, field)
    fields.update(spec["create_defaults"])

    if spec["create_due_date"]:
        raw = _value(new_item, "due_date")
        try:
            fields["due_date"] = date.fromisoformat(raw) if raw else None
        except (ValueError, TypeError):
            fields["due_date"] = None

    obj = model_class(
        project_id=project.id,
        title=title,
        canonical_title=normalize_title(title),
        status=_normalize_status(_value(new_item, "status", "open")),
        created_in_meeting_id=meeting.id,
        updated_in_meeting_id=meeting.id,
        **fields,
    )
    return obj


def _stamp_done(obj, spec, meeting, done):
    """
    Set or clear the completion/resolution stamp so it matches the status.

    The stamp and the status used to drift: a status could become
    "resolved" while resolved_at stayed None, and reopening an item left
    the old stamp in place claiming it was still resolved.
    """

    if done:
        setattr(obj, spec["at_field"], utcnow())
        setattr(obj, spec["in_meeting_field"], meeting.id)
    elif getattr(obj, spec["at_field"], None) is not None:
        # Reopened: clear the stale stamp.
        setattr(obj, spec["at_field"], None)
        setattr(obj, spec["in_meeting_field"], None)


def _apply_plan_update(existing, model_class, new_item, meeting):
    """The UPDATE branch's per-type field write, plus the stamp correction."""

    spec = _PLAN_ITEM_SPECS[model_class]

    for field in spec["update_fields"]:
        # A field the plan does not mention must keep its current value:
        # _value defaults to "", which would silently erase data that was
        # never updated.
        setattr(
            existing,
            field,
            _value(new_item, field, getattr(existing, field, None)),
        )

    if spec["update_due_date"]:
        raw = _value(new_item, "due_date")
        if raw:
            try:
                existing.due_date = date.fromisoformat(raw)
            except (ValueError, TypeError):
                pass

    existing.updated_in_meeting_id = meeting.id

    done = existing.status == spec["done_status"]
    _stamp_done(existing, spec, meeting, done)

    return existing


def _apply_create(project, meeting, item, model_class, title, reason, created):
    """CREATE: make the record, recording a merge if this plan already did."""

    created_titles = created.setdefault(model_class, {})
    duplicate_id = created_titles.get(normalize_title(title))

    if duplicate_id is not None:
        # The same plan already created this title in this meeting:
        # merge into it instead of creating a duplicate.
        _event(
            project.id,
            meeting.id,
            _entity_label(model_class),
            duplicate_id,
            "merged",
            (
                f"Merged duplicate {_entity_label(model_class)}: {title} "
                f"(duplicate CREATE within the same plan). "
                f"Reason: {reason}"
            ),
        )
        return

    obj = _build_plan_item(project, meeting, model_class, item.get("new_item", {}), title)
    spec = _PLAN_ITEM_SPECS[model_class]

    if _value(item.get("new_item", {}), "status") in ("completed", "resolved"):
        _stamp_done(obj, spec, meeting, done=True)
        obj.status = spec["done_status"]

    db.session.add(obj)
    db.session.flush()

    created_titles[normalize_title(title)] = obj.id

    _event(
        project.id,
        meeting.id,
        spec["label"],
        obj.id,
        "created",
        f"Created {spec['label']}: {title} (via consolidation)",
    )


def _apply_merge(project, meeting, item, model_class, title, reason):
    """MERGE: the existing item already represents this, so do not duplicate."""

    if not item.get("existing_item_id"):
        _needs_review_event(project, meeting, _entity_label(model_class), item, "missing")
        return

    existing, problem = _plan_existing_item(project, model_class, item)

    if problem:
        _needs_review_event(project, meeting, _entity_label(model_class), item, problem)
        return

    _event(
        project.id,
        meeting.id,
        _entity_label(model_class),
        existing.id,
        "merged",
        f"Merged duplicate {_entity_label(model_class)}: {title}. Reason: {reason}",
    )


def _apply_update(project, meeting, item, model_class, title, reason):
    """UPDATE: write the plan's fields, keeping resolution stamps consistent."""

    if not item.get("existing_item_id"):
        _needs_review_event(project, meeting, _entity_label(model_class), item, "missing")
        return

    existing, problem = _plan_existing_item(project, model_class, item)

    if problem:
        _needs_review_event(project, meeting, _entity_label(model_class), item, problem)
        return

    if not existing:
        return

    before = _snapshot(existing, _PLAN_ITEM_SPECS[model_class]["snapshot_fields"])

    _apply_plan_update(existing, model_class, item.get("new_item", {}), meeting)

    after = _snapshot(existing, _PLAN_ITEM_SPECS[model_class]["snapshot_fields"])

    _event(
        project.id,
        meeting.id,
        _entity_label(model_class),
        existing.id,
        "updated",
        f"Updated {_entity_label(model_class)}: {title}. Reason: {reason}",
        before,
        after,
    )


def _apply_conflict(project, meeting, item, model_class, title, reason):
    """CONFLICT: preserve the existing item and record what contradicted it."""

    if not item.get("existing_item_id"):
        _needs_review_event(project, meeting, _entity_label(model_class), item, "missing")
        return

    existing, problem = _plan_existing_item(project, model_class, item)

    if problem:
        _needs_review_event(project, meeting, _entity_label(model_class), item, problem)
        return

    _event(
        project.id,
        meeting.id,
        _entity_label(model_class),
        existing.id,
        "conflict",
        (
            f"Conflict detected for {_entity_label(model_class)}: "
            f"{title}. Existing preserved. Reason: {reason}"
        ),
        {
            "title": existing.title,
            "status": existing.status,
        },
        {
            "conflicting_title": title,
            "conflicting_status": _value(item.get("new_item", {}), "status"),
        },
    )


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

    Each decision is a named branch, and the per-type field differences
    live in _PLAN_ITEM_SPECS. This dispatcher decides which branch runs;
    it no longer contains the branch bodies.
    """

    new_item = item.get("new_item", {})
    item.get("existing_item_id")

    title = _value(new_item, "title")
    reason = _value(item, "reason")

    # Normalize the AI-provided decision value (for example "create").
    if isinstance(decision_type, str):
        decision_type = decision_type.strip().upper()

    entity_label = _entity_label(model_class)

    if entity_label is None:
        return

    if not title:
        # A plan entry without a title cannot be applied; preserve it
        # for review instead of dropping it silently.
        _needs_review_event(project, meeting, entity_label, item, "missing_title")
        return

    if decision_type == "CREATE":
        _apply_create(project, meeting, item, model_class, title, reason, created)
    elif decision_type == "MERGE":
        _apply_merge(project, meeting, item, model_class, title, reason)
    elif decision_type == "UPDATE":
        _apply_update(project, meeting, item, model_class, title, reason)
    elif decision_type == "CONFLICT":
        _apply_conflict(project, meeting, item, model_class, title, reason)
    else:
        # Unknown decision type from the AI plan: preserve the entry
        # for review instead of dropping it silently.
        _needs_review_event(project, meeting, entity_label, item, "unknown_decision")


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