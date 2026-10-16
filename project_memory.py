from datetime import date

from database import db
from matching import normalize_title
from models import (
    ActionItem,
    Blocker,
    Decision,
    HistoryEvent,
    Meeting,
    ProjectState,
    Risk,
    utcnow,
)


def _value(item, key, default=""):
    value = item.get(key, default) if isinstance(item, dict) else default
    return value.strip() if isinstance(value, str) else value


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


def _apply_risks(project, meeting, risks):
    for item in risks or []:
        title = _value(item, "title")

        if not title:
            continue

        risk = _find_by_canonical_title(Risk, project.id, title)
        is_resolved = _value(item, "status", "open") == "resolved"

        if risk is None:
            risk = Risk(
                project_id=project.id,
                title=title,
                canonical_title=normalize_title(title),
                description=_value(item, "description"),
                impact=_value(item, "impact", "unknown"),
                mitigation=_value(item, "mitigation"),
                status="resolved" if is_resolved else "open",
                created_in_meeting_id=meeting.id,
                updated_in_meeting_id=meeting.id,
            )

            if is_resolved:
                risk.resolved_at = utcnow()
                risk.resolved_in_meeting_id = meeting.id

            db.session.add(risk)
            db.session.flush()

            _event(
                project.id,
                meeting.id,
                "risk",
                risk.id,
                "created",
                f"Recorded risk: {title}",
                after={"status": risk.status},
            )

        else:
            before = {
                "status": risk.status,
                "impact": risk.impact,
                "mitigation": risk.mitigation,
            }

            risk.description = _value(item, "description")
            risk.impact = _value(item, "impact", "unknown")
            risk.mitigation = _value(item, "mitigation")
            risk.updated_in_meeting_id = meeting.id

            if is_resolved:
                risk.status = "resolved"
                risk.resolved_at = utcnow()
                risk.resolved_in_meeting_id = meeting.id

                action = "resolved"
                summary = f"Resolved risk: {title}"
            else:
                action = "updated"
                summary = f"Updated risk: {title}"

            _event(
                project.id,
                meeting.id,
                "risk",
                risk.id,
                action,
                summary,
                before,
                {
                    "status": risk.status,
                    "impact": risk.impact,
                    "mitigation": risk.mitigation,
                },
            )


def _apply_blockers(project, meeting, blockers):
    for item in blockers or []:
        title = _value(item, "title")

        if not title:
            continue

        blocker = _find_by_canonical_title(Blocker, project.id, title)
        resolved = _value(item, "status", "open") == "resolved"

        if blocker is None:
            blocker = Blocker(
                project_id=project.id,
                title=title,
                canonical_title=normalize_title(title),
                description=_value(item, "description"),
                status="resolved" if resolved else "open",
                created_in_meeting_id=meeting.id,
                updated_in_meeting_id=meeting.id,
            )

            if resolved:
                blocker.resolved_at = utcnow()
                blocker.resolved_in_meeting_id = meeting.id

            db.session.add(blocker)
            db.session.flush()

            _event(
                project.id,
                meeting.id,
                "blocker",
                blocker.id,
                "created",
                f"Recorded blocker: {title}",
            )

        else:
            before = {
                "status": blocker.status,
            }

            blocker.description = _value(item, "description")
            blocker.updated_in_meeting_id = meeting.id

            if resolved:
                blocker.status = "resolved"
                blocker.resolved_at = utcnow()
                blocker.resolved_in_meeting_id = meeting.id

                action = "resolved"
                summary = f"Resolved blocker: {title}"
            else:
                action = "updated"
                summary = f"Updated blocker: {title}"

            _event(
                project.id,
                meeting.id,
                "blocker",
                blocker.id,
                action,
                summary,
                before,
                {
                    "status": blocker.status,
                },
            )


def _apply_actions(project, meeting, actions):
    for item in actions or []:
        title = _value(item, "title")

        if not title:
            continue

        action_item = _find_by_canonical_title(ActionItem, project.id, title)
        completed = _value(item, "status", "open") == "completed"

        due_date = _value(item, "due_date", None)

        try:
            due_date = date.fromisoformat(due_date) if due_date else None
        except (ValueError, TypeError):
            due_date = None

        if action_item is None:
            action_item = ActionItem(
                project_id=project.id,
                title=title,
                canonical_title=normalize_title(title),
                details=_value(item, "details"),
                owner=_value(item, "owner", None),
                due_date=due_date,
                status="completed" if completed else "open",
                created_in_meeting_id=meeting.id,
                updated_in_meeting_id=meeting.id,
            )

            if completed:
                action_item.completed_at = utcnow()
                action_item.completed_in_meeting_id = meeting.id

            db.session.add(action_item)
            db.session.flush()

            _event(
                project.id,
                meeting.id,
                "action_item",
                action_item.id,
                "created",
                f"Recorded action item: {title}",
            )

        else:
            before = {
                "status": action_item.status,
                "owner": action_item.owner,
                "due_date": (
                    str(action_item.due_date)
                    if action_item.due_date
                    else None
                ),
            }

            action_item.details = _value(item, "details")
            action_item.owner = _value(item, "owner", None)
            action_item.due_date = due_date
            action_item.updated_in_meeting_id = meeting.id

            if completed:
                action_item.status = "completed"
                action_item.completed_at = utcnow()
                action_item.completed_in_meeting_id = meeting.id

                action = "completed"
                summary = f"Completed action item: {title}"
            else:
                action = "updated"
                summary = f"Updated action item: {title}"

            _event(
                project.id,
                meeting.id,
                "action_item",
                action_item.id,
                action,
                summary,
                before,
                {
                    "status": action_item.status,
                    "owner": action_item.owner,
                    "due_date": (
                        str(action_item.due_date)
                        if action_item.due_date
                        else None
                    ),
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
                status=_value(new_item, "status", "open"),
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
                status=_value(new_item, "status", "open"),
                created_in_meeting_id=meeting.id,
                updated_in_meeting_id=meeting.id,
            )

        elif model_class == Blocker:
            obj = Blocker(
                project_id=project.id,
                title=title,
                canonical_title=normalize_title(title),
                description=_value(new_item, "description"),
                status=_value(new_item, "status", "open"),
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

                    existing.details = _value(
                        new_item,
                        "details",
                    )

                    existing.owner = _value(
                        new_item,
                        "owner",
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
                    )

                    existing.impact = _value(
                        new_item,
                        "impact",
                        existing.impact,
                    )

                    existing.mitigation = _value(
                        new_item,
                        "mitigation",
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

    for item in analysis.get(
        "decisions",
        [],
    ):
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