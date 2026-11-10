"""
Serializers: model rows to the plain dicts the API returns.

These are pure functions over rows and carry no state of their own, which
is why they were the first part of api.py to move out. The frontend owns
its own types, so this is the whole contract between the database shape
and the JSON shape, and it is worth being able to read it in one file
without scrolling past 60 route handlers.

`history_changes` and `error_response` moved here with them: one is the
filter the history table's diff column used in the Flask templates, the
other is the one place an error body is produced.
"""

from fastapi.responses import JSONResponse


def history_changes(event):
    """
    Extract scalar field changes (field, old, new) from an event's
    before/after snapshots. Nested structures (plan items, new
    items) are skipped: their content is already reflected in the
    event summary. Ported verbatim from the Flask template filter.
    """
    before = event.before_data if isinstance(event.before_data, dict) else {}
    after = event.after_data if isinstance(event.after_data, dict) else {}
    changes = []

    for key, new_value in after.items():
        if key not in before or before[key] == new_value:
            continue

        if isinstance(new_value, (dict, list)) or isinstance(before[key], (dict, list)):
            continue

        changes.append((key, before[key], new_value))

    return changes


def _dt(value):
    return value.isoformat() if value else None


def serialize_risk(risk):
    return {
        "id": risk.id,
        "title": risk.title,
        "description": risk.description,
        "impact": risk.impact,
        "mitigation": risk.mitigation,
        "status": risk.status,
        "resolved_at": _dt(risk.resolved_at),
    }


def serialize_blocker(blocker):
    return {
        "id": blocker.id,
        "title": blocker.title,
        "description": blocker.description,
        "status": blocker.status,
        "resolved_at": _dt(blocker.resolved_at),
    }


def serialize_action(action):
    return {
        "id": action.id,
        "title": action.title,
        "details": action.details,
        "owner": action.owner,
        "due_date": action.due_date.isoformat() if action.due_date else None,
        "status": action.status,
        "completed_at": _dt(action.completed_at),
    }


def serialize_meeting(meeting, detail=False):
    data = {
        "id": meeting.id,
        "project_id": meeting.project_id,
        "title": meeting.title,
        "source_filename": meeting.source_filename,
        "provider": meeting.provider,
        "model": meeting.model,
        "created_at": _dt(meeting.created_at),
    }

    if detail:
        data["original_text"] = meeting.original_text
        data["analysis_text"] = meeting.analysis_text
        data["analysis_json"] = meeting.analysis_json
        data["project_name"] = meeting.project.name

    return data


def serialize_event(event):
    return {
        "id": event.id,
        "project_id": event.project_id,
        "meeting_id": event.meeting_id,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "event_type": event.event_type,
        "summary": event.summary,
        "before_data": event.before_data,
        "after_data": event.after_data,
        "created_at": _dt(event.created_at),
        "changes": [
            {"field": field, "old": old, "new": new}
            for field, old, new in history_changes(event)
        ],
    }


def serialize_project_summary(project):
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "updated_at": _dt(project.updated_at),
    }


def serialize_state(state):
    if state is None:
        return {
            "delivery_status": "unknown",
            "progress_summary": "No meeting analysis yet.",
            "completed_items": [],
            "in_progress_items": [],
        }

    return {
        "delivery_status": state.delivery_status,
        "progress_summary": state.progress_summary or "No meeting analysis yet.",
        "completed_items": state.completed_items or [],
        "in_progress_items": state.in_progress_items or [],
    }


def error_response(message, status_code=400):
    return JSONResponse(status_code=status_code, content={"error": message})
