from datetime import date

from database import db
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


def _find_open(model, project_id, title):
    return model.query.filter_by(
        project_id=project_id,
        title=title,
        status="open",
    ).first()


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

        risk = _find_open(Risk, project.id, title)
        is_resolved = _value(item, "status", "open") == "resolved"

        if risk is None:
            risk = Risk(
                project_id=project.id,
                title=title,
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

        blocker = _find_open(Blocker, project.id, title)
        resolved = _value(item, "status", "open") == "resolved"

        if blocker is None:
            blocker = Blocker(
                project_id=project.id,
                title=title,
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

        action_item = _find_open(ActionItem, project.id, title)
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
        return

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------
    if decision_type == "CREATE":

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
            obj.status = (
                "completed"
                if model_class == ActionItem
                else "resolved"
            )
            obj.completed_at = utcnow()
            obj.completed_in_meeting_id = meeting.id

        db.session.add(obj)
        db.session.flush()

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

        # Existing item already represents this information.
        # Do not create a duplicate.
        if existing_item_id:
            existing = db.session.get(
                model_class,
                existing_item_id,
            )

            if existing:
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

        if existing_item_id:
            existing = db.session.get(
                model_class,
                existing_item_id,
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

        # Preserve the existing item and record the conflict.
        if existing_item_id:
            existing = db.session.get(
                model_class,
                existing_item_id,
            )

            if existing:
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
        )

    # Process decisions
    for item in consolidation_plan.get(
        "decisions",
        [],
    ):
        decision = item.get("decision")

        if decision == "CREATE":
            new_item = item.get("new_item", {})
            title = _value(new_item, "title")

            if title:
                decision_record = Decision(
                    project_id=project.id,
                    title=title,
                    details=_value(
                        new_item,
                        "details",
                    ),
                    created_in_meeting_id=meeting.id,
                )

                db.session.add(decision_record)
                db.session.flush()

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
            decision = Decision(
                project_id=project.id,
                title=title,
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